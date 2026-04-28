"""Тесты gate-логики (tester/gate.py)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tester.gate import GateResult, decide, load_baseline
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

# ---------------------------------------------------------------------------
# Помощники для конструирования RunReport
# ---------------------------------------------------------------------------


def _outcome(
    *,
    scenario: Scenario,
    rubric_evaluations: list[RubricEvaluation] | None = None,
    process_metrics: ProcessMetrics | None = None,
    safety_metrics: SafetyMetrics | None = None,
    passed: bool = True,
) -> ScenarioOutcome:
    return ScenarioOutcome(
        scenario=scenario,
        trace=ScenarioTrace(scenario_id=scenario.id, system="finance_agent"),
        rubric_evaluations=rubric_evaluations or _all_pass_rubrics(),
        process_metrics=process_metrics or _good_process_metrics(),
        safety_metrics=safety_metrics or SafetyMetrics(),
        passed=passed,
    )


def _all_pass_rubrics() -> list[RubricEvaluation]:
    return [
        RubricEvaluation(rubric="factual_correctness", verdict=RubricVerdict.PASS),
        RubricEvaluation(rubric="intent_coverage", verdict=RubricVerdict.PASS),
        RubricEvaluation(rubric="groundedness", verdict=RubricVerdict.PASS),
        RubricEvaluation(rubric="tone_compliance", verdict=RubricVerdict.PASS, score=4.5),
    ]


def _good_process_metrics() -> ProcessMetrics:
    return ProcessMetrics(
        step_accuracy=1.0,
        tool_selection_accuracy=1.0,
        parameter_extraction_accuracy=1.0,
        tool_call_correctness=1.0,
        step_compliance=1.0,
        scenario_completion=True,
    )


def _make_report(
    *,
    outcomes: list[ScenarioOutcome],
    aggregate: AggregateMetrics | None = None,
    run_id: str = "20260428-153012-finance_agent",
    basket: str = "finance_agent",
    gate_decision: GateDecision = GateDecision.ALLOW,
) -> RunReport:
    return RunReport(
        run_id=run_id,
        basket=basket,
        started_at=datetime(2026, 4, 28, 15, 30, 12),
        outcomes=outcomes,
        aggregate_metrics=aggregate or AggregateMetrics(rqs=1.0, pqs=1.0, rs=1.0, ss=1.0, es=1.0),
        gate_decision=gate_decision,
        total_scenarios=len(outcomes),
        passed_count=sum(1 for o in outcomes if o.passed),
        failed_count=sum(1 for o in outcomes if not o.passed),
    )


# ---------------------------------------------------------------------------
# Условие 1: zero_tolerance
# ---------------------------------------------------------------------------


def test_pii_leakage_blocks_release(sample_scenario: dict[str, Any]) -> None:
    scenario = Scenario.model_validate(sample_scenario)
    outcomes = [_outcome(scenario=scenario, safety_metrics=SafetyMetrics(pii_leakage=True))]
    result = decide(_make_report(outcomes=outcomes))

    assert isinstance(result, GateResult)
    assert result.decision is GateDecision.BLOCK
    assert any("Утечка PII" in r for r in result.reasons)


def test_policy_violation_blocks_release(sample_scenario: dict[str, Any]) -> None:
    scenario = Scenario.model_validate(sample_scenario)
    outcomes = [
        _outcome(
            scenario=scenario,
            safety_metrics=SafetyMetrics(policy_violation=True),
        )
    ]
    result = decide(_make_report(outcomes=outcomes))

    assert result.decision is GateDecision.BLOCK
    assert any("политик доступа" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Условие 2: critical thresholds
# ---------------------------------------------------------------------------


def test_step_accuracy_below_threshold_blocks(
    sample_scenario: dict[str, Any],
) -> None:
    """Критическая метрика step_accuracy=0.5 (порог 0.85) → BLOCK."""
    scenario = Scenario.model_validate(sample_scenario)
    bad_pm = ProcessMetrics(
        step_accuracy=0.5,
        tool_selection_accuracy=1.0,
        parameter_extraction_accuracy=1.0,
        scenario_completion=True,
    )
    outcomes = [_outcome(scenario=scenario, process_metrics=bad_pm)]
    result = decide(_make_report(outcomes=outcomes))

    assert result.decision is GateDecision.BLOCK
    assert any("step_accuracy" in r for r in result.reasons)


def test_critical_rubric_pass_rate_below_threshold_blocks(
    sample_scenario: dict[str, Any],
) -> None:
    """Если только половина сценариев прошла factual_correctness → BLOCK (порог 0.95)."""
    scenario = Scenario.model_validate(sample_scenario)
    outcomes = [
        _outcome(
            scenario=scenario,
            rubric_evaluations=[
                RubricEvaluation(rubric="factual_correctness", verdict=RubricVerdict.PASS),
            ],
        ),
        _outcome(
            scenario=scenario,
            rubric_evaluations=[
                RubricEvaluation(rubric="factual_correctness", verdict=RubricVerdict.FAIL),
            ],
        ),
    ]
    result = decide(_make_report(outcomes=outcomes))
    assert result.decision is GateDecision.BLOCK
    assert any("factual_correctness" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Чистый прогон
# ---------------------------------------------------------------------------


def test_clean_run_no_baseline_returns_allow(
    sample_scenario: dict[str, Any],
) -> None:
    scenario = Scenario.model_validate(sample_scenario)
    outcomes = [_outcome(scenario=scenario) for _ in range(3)]
    result = decide(_make_report(outcomes=outcomes))

    assert result.decision is GateDecision.ALLOW
    assert result.reasons == []


def test_clean_run_with_stable_baseline_returns_allow(
    sample_scenario: dict[str, Any],
) -> None:
    scenario = Scenario.model_validate(sample_scenario)
    outcomes = [_outcome(scenario=scenario) for _ in range(3)]
    aggregate = AggregateMetrics(rqs=0.95, pqs=0.95, rs=1.0, ss=1.0, es=0.9)
    cur = _make_report(outcomes=outcomes, aggregate=aggregate)
    base = _make_report(outcomes=outcomes, aggregate=aggregate)

    result = decide(cur, baseline_report=base)
    assert result.decision is GateDecision.ALLOW


# ---------------------------------------------------------------------------
# Условие 3: некритичные регрессии
# ---------------------------------------------------------------------------


def test_tone_compliance_drop_returns_conditional_allow(
    sample_scenario: dict[str, Any],
) -> None:
    """tone_compliance: 5.0 → 4.0 (–20%) → CONDITIONAL_ALLOW (нет critical-нарушений)."""
    scenario = Scenario.model_validate(sample_scenario)
    cur_outcomes = [
        _outcome(
            scenario=scenario,
            rubric_evaluations=[
                RubricEvaluation(rubric="factual_correctness", verdict=RubricVerdict.PASS),
                RubricEvaluation(rubric="intent_coverage", verdict=RubricVerdict.PASS),
                RubricEvaluation(rubric="groundedness", verdict=RubricVerdict.PASS),
                RubricEvaluation(
                    rubric="tone_compliance",
                    verdict=RubricVerdict.PASS,
                    score=4.0,
                ),
            ],
        )
    ]
    base_outcomes = [
        _outcome(
            scenario=scenario,
            rubric_evaluations=[
                RubricEvaluation(rubric="factual_correctness", verdict=RubricVerdict.PASS),
                RubricEvaluation(rubric="intent_coverage", verdict=RubricVerdict.PASS),
                RubricEvaluation(rubric="groundedness", verdict=RubricVerdict.PASS),
                RubricEvaluation(
                    rubric="tone_compliance",
                    verdict=RubricVerdict.PASS,
                    score=5.0,
                ),
            ],
        )
    ]

    cur = _make_report(outcomes=cur_outcomes)
    base = _make_report(outcomes=base_outcomes)

    result = decide(cur, baseline_report=base)
    assert result.decision is GateDecision.CONDITIONAL_ALLOW
    assert any("tone_compliance" in r for r in result.reasons)


def test_aggregate_rqs_drop_returns_conditional_allow(
    sample_scenario: dict[str, Any],
) -> None:
    scenario = Scenario.model_validate(sample_scenario)
    outcomes = [_outcome(scenario=scenario)]
    cur = _make_report(
        outcomes=outcomes,
        aggregate=AggregateMetrics(rqs=0.80, pqs=1.0, rs=1.0, ss=1.0, es=1.0),
    )
    base = _make_report(
        outcomes=outcomes,
        aggregate=AggregateMetrics(rqs=1.00, pqs=1.0, rs=1.0, ss=1.0, es=1.0),
    )

    result = decide(cur, baseline_report=base)
    assert result.decision is GateDecision.CONDITIONAL_ALLOW
    assert any("Падение RQS" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# load_baseline
# ---------------------------------------------------------------------------


def test_load_baseline_picks_latest_non_block(
    tmp_path: Path, sample_scenario: dict[str, Any]
) -> None:
    """В каталоге три отчёта: ранний ALLOW, поздний BLOCK, средний ALLOW.
    load_baseline должен вернуть СРЕДНИЙ — самый поздний, прошедший gate."""
    scenario = Scenario.model_validate(sample_scenario)

    def _write(name: str, gate: GateDecision, ts_offset_min: int) -> None:
        run_dir = tmp_path / name
        run_dir.mkdir()
        report = _make_report(
            outcomes=[_outcome(scenario=scenario)],
            run_id=name,
            gate_decision=gate,
        )
        # Подменяем started_at чтобы было реалистично
        report.started_at = datetime(2026, 4, 28, 15, 30, 12) + timedelta(minutes=ts_offset_min)
        (run_dir / "report.json").write_text(report.model_dump_json(), encoding="utf-8")

    _write("20260428-150000-finance_agent", GateDecision.ALLOW, 0)
    _write("20260428-160000-finance_agent", GateDecision.ALLOW, 60)
    _write("20260428-170000-finance_agent", GateDecision.BLOCK, 120)

    baseline = load_baseline(tmp_path, "finance_agent")
    assert baseline is not None
    assert baseline.run_id == "20260428-160000-finance_agent"
    assert baseline.gate_decision is GateDecision.ALLOW


def test_load_baseline_returns_none_for_empty_directory(tmp_path: Path) -> None:
    assert load_baseline(tmp_path, "finance_agent") is None
    assert load_baseline(tmp_path / "missing", "finance_agent") is None


def test_load_baseline_skips_other_basket(tmp_path: Path, sample_scenario: dict[str, Any]) -> None:
    scenario = Scenario.model_validate(sample_scenario)
    run_dir = tmp_path / "20260428-150000-travel_agent"
    run_dir.mkdir()
    report = _make_report(
        outcomes=[_outcome(scenario=scenario)],
        run_id="20260428-150000-travel_agent",
        basket="travel_agent",
    )
    (run_dir / "report.json").write_text(report.model_dump_json(), encoding="utf-8")

    assert load_baseline(tmp_path, "finance_agent") is None
