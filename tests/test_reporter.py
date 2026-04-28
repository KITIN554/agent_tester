"""Тесты HTML-репортера (tester/reporter.py)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

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
from tester.reporter import (
    generate_html_report,
    generate_manifest,
    save_run_artifacts,
)


def _make_report(
    *,
    sample_scenario: dict[str, Any],
    run_id: str = "20260428-153012-finance_agent",
    gate_decision: GateDecision = GateDecision.ALLOW,
    aggregate: AggregateMetrics | None = None,
    failed: bool = False,
) -> RunReport:
    scenario = Scenario.model_validate(sample_scenario)
    rubric_verdict = RubricVerdict.FAIL if failed else RubricVerdict.PASS
    outcome = ScenarioOutcome(
        scenario=scenario,
        trace=ScenarioTrace(
            scenario_id=scenario.id,
            system="finance_agent",
            final_answer="Вы потратили 12 345 руб.",
            tokens_in=120,
            tokens_out=40,
            cost_usd=0.001,
            latency_s=0.5,
        ),
        rubric_evaluations=[
            RubricEvaluation(
                rubric="factual_correctness",
                verdict=rubric_verdict,
                rationale="детали проверки",
            ),
            RubricEvaluation(rubric="intent_coverage", verdict=rubric_verdict),
            RubricEvaluation(rubric="groundedness", verdict=rubric_verdict),
            RubricEvaluation(
                rubric="tone_compliance",
                verdict=RubricVerdict.PASS,
                score=4.5,
            ),
        ],
        process_metrics=ProcessMetrics(
            step_accuracy=1.0 if not failed else 0.5,
            tool_selection_accuracy=1.0,
            parameter_extraction_accuracy=1.0 if not failed else 0.5,
            tool_call_correctness=1.0,
            step_compliance=1.0,
            scenario_completion=not failed,
        ),
        safety_metrics=SafetyMetrics(),
        passed=not failed,
    )
    return RunReport(
        run_id=run_id,
        basket="finance_agent",
        started_at=datetime(2026, 4, 28, 15, 30, 12),
        finished_at=datetime(2026, 4, 28, 15, 35, 48),
        outcomes=[outcome],
        aggregate_metrics=aggregate
        or AggregateMetrics(rqs=0.93, pqs=0.95, rs=1.0, ss=1.0, es=0.92),
        gate_decision=gate_decision,
        gate_reasons=[] if gate_decision == GateDecision.ALLOW else ["test reason"],
        total_scenarios=1,
        passed_count=0 if failed else 1,
        failed_count=1 if failed else 0,
        total_tokens_in=120,
        total_tokens_out=40,
        total_cost_usd=0.001,
        avg_latency_s=0.5,
        p95_latency_s=0.5,
        model_agent="mistralai/mistral-medium-3.1",
        model_judge="mistralai/mistral-medium-3.1",
    )


def test_generate_html_report_starts_with_doctype(
    sample_scenario: dict[str, Any],
) -> None:
    report = _make_report(sample_scenario=sample_scenario)
    html = generate_html_report(report)
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert report.run_id in html


def test_generate_html_includes_gate_class_for_decision(
    sample_scenario: dict[str, Any],
) -> None:
    """Цветной класс gate-бирки соответствует решению."""
    for decision, css_class, label in (
        (GateDecision.ALLOW, "gate-allow", "ALLOW"),
        (GateDecision.CONDITIONAL_ALLOW, "gate-conditional", "CONDITIONAL ALLOW"),
        (GateDecision.BLOCK, "gate-block", "BLOCK"),
    ):
        report = _make_report(sample_scenario=sample_scenario, gate_decision=decision)
        html = generate_html_report(report)
        assert css_class in html
        assert label in html


def test_html_with_baseline_shows_deltas(sample_scenario: dict[str, Any]) -> None:
    base = _make_report(
        sample_scenario=sample_scenario,
        run_id="20260427-103012-finance_agent",
        aggregate=AggregateMetrics(rqs=0.85, pqs=0.90, rs=1.0, ss=1.0, es=0.85),
    )
    cur = _make_report(
        sample_scenario=sample_scenario,
        aggregate=AggregateMetrics(rqs=0.93, pqs=0.95, rs=1.0, ss=1.0, es=0.92),
    )

    html = generate_html_report(cur, baseline_report=base)
    assert "Δ vs baseline" in html
    # RQS вырос с 0.85 до 0.93 → положительная стрелка
    assert "↑" in html
    # Класс «положительной» дельты
    assert "delta-positive" in html


def test_html_without_baseline_omits_deltas(sample_scenario: dict[str, Any]) -> None:
    report = _make_report(sample_scenario=sample_scenario)
    html = generate_html_report(report)
    assert "Δ vs baseline" not in html
    assert "Эталонный прогон отсутствует" in html


def test_save_run_artifacts_creates_all_files(
    tmp_path: Path, sample_scenario: dict[str, Any]
) -> None:
    report = _make_report(sample_scenario=sample_scenario)

    index_path = save_run_artifacts(report, tmp_path)
    run_dir = tmp_path / report.run_id

    assert index_path == run_dir / "index.html"
    assert index_path.exists()
    assert (run_dir / "report.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "assets" / "style.css").exists()
    assert (run_dir / "traces" / "SCN-FIN-001.json").exists()


def test_saved_report_json_round_trips(tmp_path: Path, sample_scenario: dict[str, Any]) -> None:
    """report.json должен парситься обратно в RunReport."""
    report = _make_report(sample_scenario=sample_scenario)
    save_run_artifacts(report, tmp_path)

    raw = (tmp_path / report.run_id / "report.json").read_text(encoding="utf-8")
    parsed = RunReport.model_validate_json(raw)
    assert parsed.run_id == report.run_id
    assert parsed.basket == report.basket
    assert len(parsed.outcomes) == 1


def test_manifest_contains_git_info_or_null(
    sample_scenario: dict[str, Any],
) -> None:
    """manifest.git_commit либо строка (если в git-репо), либо None."""
    report = _make_report(sample_scenario=sample_scenario)
    manifest = generate_manifest(report)

    assert "git_commit" in manifest
    assert "git_branch" in manifest
    assert manifest["git_commit"] is None or isinstance(manifest["git_commit"], str)
    assert manifest["git_branch"] is None or isinstance(manifest["git_branch"], str)
    # обязательные поля для воспроизводимости
    assert manifest["run_id"] == report.run_id
    assert manifest["scenarios_count"] == report.total_scenarios
    assert manifest["model_agent"] == "mistralai/mistral-medium-3.1"


def test_manifest_json_is_serializable(tmp_path: Path, sample_scenario: dict[str, Any]) -> None:
    report = _make_report(sample_scenario=sample_scenario)
    save_run_artifacts(report, tmp_path)
    manifest_path = tmp_path / report.run_id / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["run_id"] == report.run_id


def test_failed_outcomes_rendered_open_passed_collapsed(
    sample_scenario: dict[str, Any],
) -> None:
    """Провалившиеся идут в outcome-fail (раскрыты), успешные — в <details>."""
    failed_report = _make_report(sample_scenario=sample_scenario, failed=True)
    html = generate_html_report(failed_report)
    assert 'class="outcome-fail"' in html
    assert "SCN-FIN-001" in html

    passed_report = _make_report(sample_scenario=sample_scenario)
    html_pass = generate_html_report(passed_report)
    assert 'class="outcome-pass"' in html_pass
    assert "<summary>" in html_pass
