"""Юнит-тесты Pydantic-моделей tester/models.py."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from tester.models import (
    AggregateMetrics,
    GateDecision,
    ProcessMetrics,
    RubricEvaluation,
    RubricVerdict,
    RunReport,
    SafetyMetrics,
    Scenario,
    ScenarioOutcome,
    ScenarioTrace,
)


def _multi_turn_scenario_dict() -> dict[str, Any]:
    return {
        "id": "SCN-TRV-001",
        "category": "functional",
        "type": "multi_turn",
        "description": "Бронирование тура в Европу",
        "system": "travel_agent",
        "input": {
            "conversation_turns": [
                {"role": "user", "content": "Хочу куда-нибудь в Европу"},
                {"role": "user", "content": "Бюджет 150 тысяч"},
            ],
            "available_tools": ["search_destinations", "create_booking"],
            "limits": {"max_steps": 30, "max_turns": 15},
        },
        "expectations": {
            "terminal_state": "confirmed",
        },
        "rubrics": ["intent_coverage", "tone_compliance"],
    }


def test_valid_single_turn_scenario(sample_scenario: dict[str, Any]) -> None:
    scenario = Scenario.model_validate(sample_scenario)
    assert scenario.id == "SCN-FIN-001"
    assert scenario.system == "finance_agent"
    assert scenario.input.user_message == "Сколько я потратил в прошлом месяце?"
    assert scenario.input.conversation_turns is None
    assert len(scenario.expectations.required_tool_calls) == 1


def test_valid_multi_turn_scenario() -> None:
    scenario = Scenario.model_validate(_multi_turn_scenario_dict())
    assert scenario.id == "SCN-TRV-001"
    assert scenario.system == "travel_agent"
    assert scenario.input.user_message is None
    assert scenario.input.conversation_turns is not None
    assert len(scenario.input.conversation_turns) == 2


def test_invalid_id_regex_rejected(sample_scenario: dict[str, Any]) -> None:
    bad = deepcopy(sample_scenario)
    bad["id"] = "FIN-001"  # без префикса SCN-
    with pytest.raises(ValidationError, match="id должен соответствовать"):
        Scenario.model_validate(bad)


def test_system_must_match_id_prefix(sample_scenario: dict[str, Any]) -> None:
    bad = deepcopy(sample_scenario)
    bad["id"] = "SCN-TRV-001"
    bad["system"] = "finance_agent"  # рассогласование TRV ↔ finance_agent
    with pytest.raises(ValidationError, match="не соответствует префиксу"):
        Scenario.model_validate(bad)


def test_single_turn_without_user_message_rejected(
    sample_scenario: dict[str, Any],
) -> None:
    bad = deepcopy(sample_scenario)
    bad["input"].pop("user_message")
    with pytest.raises(
        ValidationError, match="single_turn сценарий должен иметь input.user_message"
    ):
        Scenario.model_validate(bad)


def test_multi_turn_without_conversation_turns_rejected() -> None:
    bad = _multi_turn_scenario_dict()
    bad["input"].pop("conversation_turns")
    with pytest.raises(
        ValidationError,
        match="multi_turn сценарий должен иметь input.conversation_turns",
    ):
        Scenario.model_validate(bad)


def test_aggregate_metrics_rejects_out_of_range() -> None:
    """AggregateMetrics — все пять компонент строго в [0, 1]."""
    AggregateMetrics(rqs=0.0, pqs=0.5, rs=1.0, ss=0.9, es=0.4)  # ok
    with pytest.raises(ValidationError):
        AggregateMetrics(rqs=1.2, pqs=0.5, rs=0.5, ss=0.5, es=0.5)
    with pytest.raises(ValidationError):
        AggregateMetrics(rqs=-0.1, pqs=0.5, rs=0.5, ss=0.5, es=0.5)


def test_run_report_assembled_from_outcomes(sample_scenario: dict[str, Any]) -> None:
    """RunReport.from_outcomes считает счётчики и техники корректно."""
    scenario = Scenario.model_validate(sample_scenario)
    trace_passed = ScenarioTrace(
        scenario_id=scenario.id,
        system="finance_agent",
        final_answer="ок",
        tokens_in=100,
        tokens_out=50,
        latency_s=1.2,
        cost_usd=0.001,
    )
    trace_failed = trace_passed.model_copy(update={"latency_s": 3.4, "cost_usd": 0.003})

    outcomes = [
        ScenarioOutcome(
            scenario=scenario,
            trace=trace_passed,
            rubric_evaluations=[
                RubricEvaluation(
                    rubric="factual_correctness",
                    verdict=RubricVerdict.PASS,
                    rationale="всё совпадает",
                ),
            ],
            process_metrics=ProcessMetrics(scenario_completion=True),
            safety_metrics=SafetyMetrics(),
            passed=True,
        ),
        ScenarioOutcome(
            scenario=scenario,
            trace=trace_failed,
            rubric_evaluations=[
                RubricEvaluation(
                    rubric="factual_correctness",
                    verdict=RubricVerdict.FAIL,
                    rationale="расхождение чисел",
                ),
            ],
            process_metrics=ProcessMetrics(scenario_completion=False),
            safety_metrics=SafetyMetrics(),
            passed=False,
        ),
    ]

    report = RunReport.from_outcomes(
        run_id="20260428-153012-finance_agent",
        basket="finance_agent",
        started_at=datetime(2026, 4, 28, 15, 30, 12),
        outcomes=outcomes,
        aggregate_metrics=AggregateMetrics(rqs=0.8, pqs=0.7, rs=0.5, ss=1.0, es=0.6),
        gate_decision=GateDecision.CONDITIONAL_ALLOW,
        gate_reasons=["tone_compliance просел"],
    )

    assert report.total_scenarios == 2
    assert report.passed_count == 1
    assert report.failed_count == 1
    assert report.total_tokens_in == 200
    assert report.total_tokens_out == 100
    assert report.total_cost_usd == pytest.approx(0.004, rel=1e-6)
    assert report.avg_latency_s == pytest.approx(2.3, rel=1e-3)
    assert report.gate_decision is GateDecision.CONDITIONAL_ALLOW
    assert report.gate_reasons == ["tone_compliance просел"]


def test_rubric_evaluation_score_range() -> None:
    """tone_compliance score должен быть в 1..5; остальные могут быть None."""
    RubricEvaluation(
        rubric="tone_compliance", verdict=RubricVerdict.PASS, score=4.5, rationale="ok"
    )
    RubricEvaluation(rubric="groundedness", verdict=RubricVerdict.PASS, score=None)
    with pytest.raises(ValidationError):
        RubricEvaluation(rubric="tone_compliance", verdict=RubricVerdict.PASS, score=6.0)
