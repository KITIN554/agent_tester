"""Тесты orchestrator.run_basket с моками executor и judge."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from tenacity import wait_none

from tester.judge import LLMJudge
from tester.models import (
    GateDecision,
    RunReport,
    Scenario,
    ScenarioTrace,
    StepType,
    TraceStep,
)
from tester.orchestrator import run_basket


@pytest.fixture(autouse=True)
def _no_retry_wait() -> None:
    """Отключаем экспоненциальную задержку tenacity внутри судьи."""
    LLMJudge._call_and_parse.retry.wait = wait_none()  # type: ignore[attr-defined]


def _write_basket(basket_dir: Path, sample_scenario: dict[str, Any], count: int = 2) -> Path:
    """Создаёт каталог корзины с N валидными single_turn сценариями."""
    basket_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        sc = deepcopy(sample_scenario)
        sc["id"] = f"SCN-FIN-{i:03d}"
        path = basket_dir / f"{sc['id']}.yaml"
        path.write_text(yaml.safe_dump(sc, allow_unicode=True), encoding="utf-8")
    return basket_dir


def _fake_executor(scenario: Scenario) -> ScenarioTrace:
    """Возвращает трассу, удовлетворяющую required_tool_calls сценария."""
    steps: list[TraceStep] = []
    for i, req in enumerate(scenario.expectations.required_tool_calls):
        steps.append(
            TraceStep(
                step_id=i * 2,
                step_type=StepType.TOOL_CALL,
                timestamp=datetime.now(),
                content={"name": req.name, "parameters": dict(req.parameters)},
            )
        )
        steps.append(
            TraceStep(
                step_id=i * 2 + 1,
                step_type=StepType.TOOL_RESULT,
                timestamp=datetime.now(),
                content={"result": {"total_rub": 12345}, "error": None},
            )
        )
    steps.append(
        TraceStep(
            step_id=len(steps),
            step_type=StepType.FINAL_ANSWER,
            timestamp=datetime.now(),
            content={"answer": "Вы потратили 12 345 руб."},
        )
    )
    return ScenarioTrace(
        scenario_id=scenario.id,
        system=scenario.system,
        final_answer="Вы потратили 12 345 руб.",
        steps=steps,
        tokens_in=120,
        tokens_out=40,
        cost_usd=0.001,
        latency_s=0.5,
    )


def _build_judge_with_mocked_passes(mock_proxy_client: Any, *, n_calls: int) -> LLMJudge:
    """Создаёт LLMJudge с замоканным клиентом, возвращающим N pass-ответов."""
    for _ in range(n_calls):
        mock_proxy_client.queue_response(
            content='{"verdict": "pass", "score": 4.5, "rationale": "ok"}'
        )
    return LLMJudge(model="test-model", client=mock_proxy_client)


# ---------------------------------------------------------------------------


def test_run_basket_end_to_end(
    tmp_path: Path, sample_scenario: dict[str, Any], mock_proxy_client: Any
) -> None:
    basket = _write_basket(tmp_path / "basket", sample_scenario, count=2)
    output = tmp_path / "out"

    # 2 сценария * 4 рубрики = 8 LLM-вызовов судьи
    judge = _build_judge_with_mocked_passes(mock_proxy_client, n_calls=8)

    report = run_basket(
        basket_dir=basket,
        output_dir=output,
        executor_fn=_fake_executor,
        judge=judge,
    )

    assert isinstance(report, RunReport)
    assert report.total_scenarios == 2
    assert report.passed_count == 2
    assert report.failed_count == 0
    assert report.gate_decision is GateDecision.ALLOW
    assert all(o.passed for o in report.outcomes)

    # Артефакты: index.html, report.json, manifest.json в <output>/<run_id>/
    run_dir = output / report.run_id
    assert (run_dir / "index.html").exists()
    assert (run_dir / "report.json").exists()
    assert (run_dir / "manifest.json").exists()
    for outcome in report.outcomes:
        assert (run_dir / "traces" / f"{outcome.scenario.id}.json").exists()


def test_run_basket_max_scenarios_limits_basket(
    tmp_path: Path, sample_scenario: dict[str, Any], mock_proxy_client: Any
) -> None:
    basket = _write_basket(tmp_path / "basket", sample_scenario, count=3)

    judge = _build_judge_with_mocked_passes(mock_proxy_client, n_calls=4)

    report = run_basket(
        basket_dir=basket,
        output_dir=tmp_path / "out",
        executor_fn=_fake_executor,
        judge=judge,
        max_scenarios=1,
    )

    assert report.total_scenarios == 1
    # При max_scenarios=1 должен прогнаться ровно один сценарий → 4 рубрики
    assert len(mock_proxy_client.calls) == 4


def test_run_basket_passed_count_reflects_failed_rubrics(
    tmp_path: Path, sample_scenario: dict[str, Any], mock_proxy_client: Any
) -> None:
    """Если судья возвращает FAIL по критической рубрике — outcome.passed=False."""
    basket = _write_basket(tmp_path / "basket", sample_scenario, count=1)

    # Все 4 рубрики FAIL
    for _ in range(4):
        mock_proxy_client.queue_response(
            content='{"verdict": "fail", "score": null, "rationale": "плохо"}'
        )
    judge = LLMJudge(model="test-model", client=mock_proxy_client)

    report = run_basket(
        basket_dir=basket,
        output_dir=tmp_path / "out",
        executor_fn=_fake_executor,
        judge=judge,
    )

    assert report.total_scenarios == 1
    assert report.passed_count == 0
    assert report.failed_count == 1
    # При провале factual_correctness gate → BLOCK
    assert report.gate_decision is GateDecision.BLOCK


def test_run_basket_run_id_has_basket_suffix(
    tmp_path: Path, sample_scenario: dict[str, Any], mock_proxy_client: Any
) -> None:
    basket = _write_basket(tmp_path / "finance_agent", sample_scenario, count=1)
    judge = _build_judge_with_mocked_passes(mock_proxy_client, n_calls=4)

    report = run_basket(
        basket_dir=basket,
        output_dir=tmp_path / "out",
        executor_fn=_fake_executor,
        judge=judge,
    )

    assert report.run_id.endswith("-finance_agent")
    assert report.basket == "finance_agent"


def test_run_basket_uses_baseline_for_gate_comparison(
    tmp_path: Path, sample_scenario: dict[str, Any], mock_proxy_client: Any
) -> None:
    """Если в output_dir уже есть прошлый отчёт — он подгружается как baseline."""
    output = tmp_path / "out"
    output.mkdir()
    # Заранее кладём «эталонный» прогон
    baseline_dir = output / "20260101-100000-finance_agent"
    baseline_dir.mkdir()
    fake_baseline = {
        "run_id": "20260101-100000-finance_agent",
        "basket": "finance_agent",
        "started_at": "2026-01-01T10:00:00",
        "outcomes": [],
        "aggregate_metrics": {"rqs": 1.0, "pqs": 1.0, "rs": 1.0, "ss": 1.0, "es": 1.0},
        "gate_decision": "allow",
    }
    import json

    (baseline_dir / "report.json").write_text(json.dumps(fake_baseline))

    basket = _write_basket(tmp_path / "basket", sample_scenario, count=1)
    judge = _build_judge_with_mocked_passes(mock_proxy_client, n_calls=4)

    report = run_basket(
        basket_dir=basket,
        output_dir=output,
        executor_fn=_fake_executor,
        judge=judge,
    )
    # Baseline RQS=1.0, current тоже 1.0 → ALLOW (никаких регрессий)
    assert report.gate_decision is GateDecision.ALLOW
