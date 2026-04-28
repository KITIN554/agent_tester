"""Тесты LLMJudge с моками клиента OpenAI (без реальных LLM-вызовов)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from tenacity import wait_none

from tester.judge import RUBRIC_DEFINITIONS, LLMJudge
from tester.models import (
    RubricVerdict,
    Scenario,
    ScenarioTrace,
    StepType,
    TraceStep,
)


@pytest.fixture(autouse=True)
def _disable_retry_wait() -> None:
    """Отключаем экспоненциальную паузу tenacity, чтобы тесты не висели."""
    LLMJudge._call_and_parse.retry.wait = wait_none()  # type: ignore[attr-defined]


def _trace() -> ScenarioTrace:
    return ScenarioTrace(
        scenario_id="SCN-FIN-001",
        system="finance_agent",
        final_answer="Вы потратили 12 345 руб.",
        steps=[
            TraceStep(
                step_id=0,
                step_type=StepType.USER_MESSAGE,
                timestamp=datetime.now(),
                content={"message": "Сколько потратил?"},
            ),
            TraceStep(
                step_id=1,
                step_type=StepType.TOOL_CALL,
                timestamp=datetime.now(),
                content={
                    "name": "query_transactions",
                    "parameters": {"period": "previous_month", "aggregation": "sum"},
                },
            ),
            TraceStep(
                step_id=2,
                step_type=StepType.TOOL_RESULT,
                timestamp=datetime.now(),
                content={"result": {"total_rub": 12345}, "error": None},
            ),
            TraceStep(
                step_id=3,
                step_type=StepType.FINAL_ANSWER,
                timestamp=datetime.now(),
                content={"answer": "Вы потратили 12 345 руб."},
            ),
        ],
    )


@pytest.fixture
def judge(mock_proxy_client: Any) -> LLMJudge:
    return LLMJudge(model="test-model", client=mock_proxy_client)


@pytest.mark.parametrize("rubric", list(RUBRIC_DEFINITIONS.keys()))
def test_evaluate_rubric_returns_correct_eval(
    rubric: str,
    judge: LLMJudge,
    mock_proxy_client: Any,
    sample_scenario: dict[str, Any],
) -> None:
    """Каждая из 4 рубрик корректно парсится из JSON-ответа судьи."""
    if rubric == "tone_compliance":
        mock_proxy_client.queue_response(
            content='{"verdict": "pass", "score": 4.5, "rationale": "тон выдержан"}'
        )
    else:
        mock_proxy_client.queue_response(
            content='{"verdict": "pass", "score": null, "rationale": "ok"}'
        )

    scenario = Scenario.model_validate(sample_scenario)
    eval_ = judge.evaluate_rubric(rubric, scenario, _trace())

    assert eval_.rubric == rubric
    assert eval_.verdict is RubricVerdict.PASS
    if rubric == "tone_compliance":
        assert eval_.score == 4.5
    else:
        assert eval_.score is None


def test_evaluate_all_calls_each_rubric_in_scenario(
    judge: LLMJudge,
    mock_proxy_client: Any,
    sample_scenario: dict[str, Any],
) -> None:
    """evaluate_all вызывает evaluate_rubric ровно по числу рубрик в сценарии."""
    scenario = Scenario.model_validate(sample_scenario)
    for _ in scenario.rubrics:
        mock_proxy_client.queue_response(content='{"verdict": "pass", "rationale": "ok"}')

    results = judge.evaluate_all(scenario, _trace())

    assert [r.rubric for r in results] == scenario.rubrics
    assert all(r.verdict is RubricVerdict.PASS for r in results)
    assert len(mock_proxy_client.calls) == len(scenario.rubrics)


def test_invalid_json_returns_na(
    judge: LLMJudge,
    mock_proxy_client: Any,
    sample_scenario: dict[str, Any],
) -> None:
    """Все 3 retry вернули невалидный JSON → verdict=NA, парсер не падает."""
    for _ in range(3):
        mock_proxy_client.queue_response(content="not a json {{{")

    scenario = Scenario.model_validate(sample_scenario)
    eval_ = judge.evaluate_rubric("factual_correctness", scenario, _trace())

    assert eval_.verdict is RubricVerdict.NA
    assert "parse" in eval_.rationale.lower()
    assert len(mock_proxy_client.calls) == 3


def test_api_error_after_retries_returns_na(
    sample_scenario: dict[str, Any],
    mock_proxy_client: Any,
) -> None:
    """3 подряд сетевые ошибки → verdict=NA, исключение не пробрасывается."""
    judge = LLMJudge(model="test-model", client=mock_proxy_client)
    call_count = {"n": 0}

    def boom(**kwargs: Any) -> Any:
        call_count["n"] += 1
        raise ConnectionError("simulated network error")

    mock_proxy_client.chat.completions.create = boom

    scenario = Scenario.model_validate(sample_scenario)
    eval_ = judge.evaluate_rubric("factual_correctness", scenario, _trace())

    assert eval_.verdict is RubricVerdict.NA
    assert "API error" in eval_.rationale
    assert call_count["n"] == 3


def test_call_uses_json_mode_temperature_zero_max_tokens(
    judge: LLMJudge,
    mock_proxy_client: Any,
    sample_scenario: dict[str, Any],
) -> None:
    mock_proxy_client.queue_response(content='{"verdict": "pass", "rationale": "ok"}')
    scenario = Scenario.model_validate(sample_scenario)
    judge.evaluate_rubric("factual_correctness", scenario, _trace())

    assert len(mock_proxy_client.calls) == 1
    call = mock_proxy_client.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["temperature"] == 0.0
    assert call["max_tokens"] == 300
    assert call["model"] == "test-model"


def test_unknown_rubric_returns_na_without_llm_call(
    judge: LLMJudge,
    mock_proxy_client: Any,
    sample_scenario: dict[str, Any],
) -> None:
    """Запрос на неизвестную рубрику не уходит в LLM, сразу возвращает NA."""
    scenario = Scenario.model_validate(sample_scenario)
    eval_ = judge.evaluate_rubric("nonexistent_rubric", scenario, _trace())

    assert eval_.verdict is RubricVerdict.NA
    assert "Неизвестная рубрика" in eval_.rationale
    assert len(mock_proxy_client.calls) == 0


def test_tone_compliance_score_out_of_range_dropped_to_none(
    judge: LLMJudge,
    mock_proxy_client: Any,
    sample_scenario: dict[str, Any],
) -> None:
    """Если LLM вернул score=7.0 (вне 1..5), мы не падаем, а сбрасываем в None."""
    mock_proxy_client.queue_response(content='{"verdict": "pass", "score": 7.0, "rationale": "ok"}')

    scenario = Scenario.model_validate(sample_scenario)
    eval_ = judge.evaluate_rubric("tone_compliance", scenario, _trace())

    assert eval_.verdict is RubricVerdict.PASS
    assert eval_.score is None


def test_evaluate_multi_turn_includes_full_trace_in_prompt(
    judge: LLMJudge,
    mock_proxy_client: Any,
) -> None:
    """evaluate_multi_turn принудительно добавляет ПОЛНУЮ ТРАССУ в user-сообщение."""
    multi_turn_scenario = Scenario.model_validate(
        {
            "id": "SCN-TRV-099",
            "category": "functional",
            "type": "multi_turn",
            "description": "test",
            "system": "travel_agent",
            "input": {
                "conversation_turns": [
                    {"role": "user", "content": "хочу поехать"},
                ],
            },
            "expectations": {"terminal_state": "confirmed"},
            "rubrics": ["intent_coverage"],  # эта рубрика обычно НЕ включает trace
        }
    )
    mock_proxy_client.queue_response(content='{"verdict": "pass", "rationale": "ok"}')

    judge.evaluate_multi_turn(multi_turn_scenario, _trace())

    assert len(mock_proxy_client.calls) == 1
    user_msg = mock_proxy_client.calls[0]["messages"][1]["content"]
    assert "ПОЛНАЯ ТРАССА" in user_msg
