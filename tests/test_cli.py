"""Тесты CLI через click.testing.CliRunner."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from tester.cli import main
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


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_basket(basket_dir: Path, sample_scenario: dict[str, Any]) -> Path:
    basket_dir.mkdir(parents=True, exist_ok=True)
    (basket_dir / "SCN-FIN-001.yaml").write_text(
        yaml.safe_dump(sample_scenario, allow_unicode=True),
        encoding="utf-8",
    )
    return basket_dir


def _make_report_json(
    run_id: str,
    basket: str,
    aggregate: AggregateMetrics,
    gate_decision: GateDecision = GateDecision.ALLOW,
) -> str:
    """Сериализованный RunReport для baseline/compare-тестов."""
    scenario = Scenario.model_validate(
        {
            "id": "SCN-FIN-001",
            "category": "functional",
            "type": "single_turn",
            "description": "тест",
            "system": "finance_agent",
            "input": {"user_message": "test"},
            "expectations": {},
            "rubrics": ["intent_coverage"],
        }
    )
    outcome = ScenarioOutcome(
        scenario=scenario,
        trace=ScenarioTrace(scenario_id=scenario.id, system="finance_agent"),
        rubric_evaluations=[RubricEvaluation(rubric="intent_coverage", verdict=RubricVerdict.PASS)],
        process_metrics=ProcessMetrics(scenario_completion=True),
        safety_metrics=SafetyMetrics(),
        passed=True,
    )
    report = RunReport(
        run_id=run_id,
        basket=basket,
        started_at=datetime(2026, 4, 28, 15, 30, 12),
        outcomes=[outcome],
        aggregate_metrics=aggregate,
        gate_decision=gate_decision,
        total_scenarios=1,
        passed_count=1,
    )
    return report.model_dump_json()


# ---------------------------------------------------------------------------
# --help / список команд
# ---------------------------------------------------------------------------


def test_help_lists_all_commands(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("run", "validate", "baseline", "report", "compare"):
        assert cmd in result.output


def test_version_flag(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


# ---------------------------------------------------------------------------
# tester validate
# ---------------------------------------------------------------------------


def test_validate_on_valid_basket_exits_zero(
    runner: CliRunner, tmp_path: Path, sample_scenario: dict[str, Any]
) -> None:
    basket = _write_basket(tmp_path / "basket", sample_scenario)
    result = runner.invoke(main, ["validate", "--basket", str(basket)])
    assert result.exit_code == 0
    assert "Загружено сценариев: 1" in result.output


def test_validate_on_missing_basket_fails(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(main, ["validate", "--basket", str(tmp_path / "does_not_exist")])
    assert result.exit_code != 0


def test_validate_on_empty_basket_exits_one(runner: CliRunner, tmp_path: Path) -> None:
    empty = tmp_path / "empty_basket"
    empty.mkdir()
    result = runner.invoke(main, ["validate", "--basket", str(empty)])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# tester compare
# ---------------------------------------------------------------------------


def test_compare_outputs_table(runner: CliRunner, tmp_path: Path) -> None:
    reports_dir = tmp_path / "runs"
    run_a = "20260427-103045-finance_agent"
    run_b = "20260428-153012-finance_agent"

    (reports_dir / run_a).mkdir(parents=True)
    (reports_dir / run_b).mkdir(parents=True)
    (reports_dir / run_a / "report.json").write_text(
        _make_report_json(
            run_a,
            "finance_agent",
            AggregateMetrics(rqs=0.85, pqs=0.80, rs=0.90, ss=1.0, es=0.85),
        )
    )
    (reports_dir / run_b / "report.json").write_text(
        _make_report_json(
            run_b,
            "finance_agent",
            AggregateMetrics(rqs=0.93, pqs=0.87, rs=0.92, ss=1.0, es=0.78),
        )
    )

    result = runner.invoke(main, ["compare", run_a, run_b, "--reports-dir", str(reports_dir)])
    assert result.exit_code == 0
    # Заголовки таблицы
    assert "RQS" in result.output
    assert "PQS" in result.output
    # Числовые значения
    assert "0.850" in result.output
    assert "0.930" in result.output
    # Дельта со знаком
    assert "+0.080" in result.output  # rqs: 0.93 - 0.85


def test_compare_missing_run_returns_error(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(main, ["compare", "RUN_X", "RUN_Y", "--reports-dir", str(tmp_path)])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# tester baseline
# ---------------------------------------------------------------------------


def test_baseline_show_when_present(runner: CliRunner, tmp_path: Path) -> None:
    reports_dir = tmp_path / "runs"
    run_id = "20260428-150000-finance_agent"
    (reports_dir / run_id).mkdir(parents=True)
    (reports_dir / run_id / "report.json").write_text(
        _make_report_json(
            run_id,
            "finance_agent",
            AggregateMetrics(rqs=0.95, pqs=0.95, rs=1.0, ss=1.0, es=0.9),
        )
    )

    result = runner.invoke(
        main, ["baseline", "--basket", "finance_agent", "--reports-dir", str(reports_dir)]
    )
    assert result.exit_code == 0
    assert run_id in result.output
    assert "RQS=0.950" in result.output


def test_baseline_set_creates_symlink(runner: CliRunner, tmp_path: Path) -> None:
    reports_dir = tmp_path / "runs"
    run_id = "20260428-150000-finance_agent"
    (reports_dir / run_id).mkdir(parents=True)
    (reports_dir / run_id / "report.json").write_text(
        _make_report_json(run_id, "finance_agent", AggregateMetrics(rqs=1, pqs=1, rs=1, ss=1, es=1))
    )

    result = runner.invoke(
        main,
        [
            "baseline",
            "--basket",
            "finance_agent",
            "--set",
            run_id,
            "--reports-dir",
            str(reports_dir),
        ],
    )
    assert result.exit_code == 0
    link = reports_dir / "baseline_finance_agent"
    assert link.is_symlink()
    assert link.resolve() == (reports_dir / run_id).resolve()


# ---------------------------------------------------------------------------
# tester report
# ---------------------------------------------------------------------------


def test_report_latest_finds_newest_run(runner: CliRunner, tmp_path: Path) -> None:
    reports_dir = tmp_path / "runs"
    for run_id in (
        "20260101-100000-finance_agent",
        "20260201-110000-finance_agent",
    ):
        (reports_dir / run_id).mkdir(parents=True)
        (reports_dir / run_id / "index.html").write_text("<!DOCTYPE html><html></html>")

    result = runner.invoke(
        main,
        [
            "report",
            "--latest",
            "--basket",
            "finance_agent",
            "--reports-dir",
            str(reports_dir),
            "--no-browser",
        ],
    )
    assert result.exit_code == 0
    assert "20260201-110000-finance_agent" in result.output


def test_report_missing_run_fails(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        main,
        [
            "report",
            "MISSING-RUN",
            "--reports-dir",
            str(tmp_path),
            "--no-browser",
        ],
    )
    assert result.exit_code == 1
