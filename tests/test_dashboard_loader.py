"""Тесты dashboard/data_loader.py — без поднятия Streamlit."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from dashboard import data_loader
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


@pytest.fixture(autouse=True)
def _isolate_reports_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Каждый тест получает чистый reports_dir и сброшенный lru_cache."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    monkeypatch.setattr(data_loader, "REPORTS_ROOT", runs_dir)
    data_loader.clear_cache()
    yield runs_dir
    data_loader.clear_cache()


def _write_report(
    runs_dir: Path,
    *,
    run_id: str,
    basket: str = "finance_agent",
    rqs: float = 0.9,
    gate_decision: GateDecision = GateDecision.ALLOW,
) -> Path:
    scenario = Scenario.model_validate(
        {
            "id": "SCN-FIN-001",
            "category": "functional",
            "type": "single_turn",
            "description": "тест",
            "system": "finance_agent",
            "input": {"user_message": "сколько потратил"},
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
        aggregate_metrics=AggregateMetrics(rqs=rqs, pqs=0.9, rs=0.95, ss=1.0, es=0.9),
        gate_decision=gate_decision,
        total_scenarios=1,
        passed_count=1,
    )
    run_dir = runs_dir / run_id
    run_dir.mkdir()
    path = run_dir / "report.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------


def test_load_report_parses_run_report(_isolate_reports_root: Path) -> None:
    _write_report(_isolate_reports_root, run_id="20260428-150000-finance_agent")
    report = data_loader.load_report("20260428-150000-finance_agent")
    assert report.run_id == "20260428-150000-finance_agent"
    assert report.basket == "finance_agent"
    assert report.aggregate_metrics.rqs == 0.9


def test_load_report_missing_raises(_isolate_reports_root: Path) -> None:
    with pytest.raises(FileNotFoundError):
        data_loader.load_report("nonexistent-run")


def test_list_runs_returns_all_when_no_filter(_isolate_reports_root: Path) -> None:
    _write_report(
        _isolate_reports_root,
        run_id="20260428-150000-finance_agent",
        basket="finance_agent",
    )
    _write_report(
        _isolate_reports_root,
        run_id="20260428-160000-travel_agent",
        basket="travel_agent",
    )
    runs = data_loader.list_runs()
    assert {r["run_id"] for r in runs} == {
        "20260428-150000-finance_agent",
        "20260428-160000-travel_agent",
    }


def test_list_runs_filters_by_basket(_isolate_reports_root: Path) -> None:
    _write_report(
        _isolate_reports_root,
        run_id="20260428-150000-finance_agent",
        basket="finance_agent",
    )
    _write_report(
        _isolate_reports_root,
        run_id="20260428-160000-travel_agent",
        basket="travel_agent",
    )
    finance_runs = data_loader.list_runs(basket="finance_agent")
    assert {r["run_id"] for r in finance_runs} == {"20260428-150000-finance_agent"}


def test_list_runs_sorted_descending(_isolate_reports_root: Path) -> None:
    _write_report(_isolate_reports_root, run_id="20260101-100000-finance_agent")
    _write_report(_isolate_reports_root, run_id="20260301-120000-finance_agent")
    _write_report(_isolate_reports_root, run_id="20260201-110000-finance_agent")

    runs = data_loader.list_runs()
    assert [r["run_id"] for r in runs] == [
        "20260301-120000-finance_agent",
        "20260201-110000-finance_agent",
        "20260101-100000-finance_agent",
    ]


def test_list_runs_skips_garbage_files(_isolate_reports_root: Path) -> None:
    _write_report(_isolate_reports_root, run_id="20260428-150000-finance_agent")
    # Каталог без report.json — должен быть пропущен
    (_isolate_reports_root / "broken").mkdir()
    # Пустой report.json — должен быть пропущен
    bad_dir = _isolate_reports_root / "20260101-100000-bad"
    bad_dir.mkdir()
    (bad_dir / "report.json").write_text("not json", encoding="utf-8")

    runs = data_loader.list_runs()
    assert [r["run_id"] for r in runs] == ["20260428-150000-finance_agent"]


def test_list_baskets_returns_unique_sorted(_isolate_reports_root: Path) -> None:
    _write_report(
        _isolate_reports_root,
        run_id="20260428-150000-finance_agent",
        basket="finance_agent",
    )
    _write_report(
        _isolate_reports_root,
        run_id="20260428-151000-finance_agent",
        basket="finance_agent",
    )
    _write_report(
        _isolate_reports_root,
        run_id="20260428-160000-travel_agent",
        basket="travel_agent",
    )

    assert data_loader.list_baskets() == ["finance_agent", "travel_agent"]


def test_list_baskets_empty_when_no_runs(_isolate_reports_root: Path) -> None:
    assert data_loader.list_baskets() == []
