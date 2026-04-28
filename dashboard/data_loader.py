"""Загрузка отчётов из reports/runs/ для дашборда (spec 07)."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from tester.models import GateDecision, RunReport

REPORTS_ROOT: Path = Path("reports/runs")


@lru_cache(maxsize=128)
def load_report(run_id: str) -> RunReport:
    """Парсит report.json указанного прогона. Кэширует результат."""
    path = REPORTS_ROOT / run_id / "report.json"
    if not path.exists():
        raise FileNotFoundError(f"Отчёт не найден: {path}")
    return RunReport.model_validate_json(path.read_text(encoding="utf-8"))


def list_runs(basket: str | None = None) -> list[dict[str, Any]]:
    """Перечисляет прогоны (опц. для одной корзины), отсортированные новые → старые.

    Возвращает по одному словарю на прогон с метаданными для UI: run_id, basket,
    started_at, gate_decision, rqs.
    """
    if not REPORTS_ROOT.exists():
        return []

    runs: list[dict[str, Any]] = []
    # Сортируем по имени директории убыванием — run_id содержит таймстамп префиксом
    for run_dir in sorted(REPORTS_ROOT.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        report_path = run_dir / "report.json"
        if not report_path.exists():
            continue
        try:
            report = RunReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — мусорные файлы пропускаем
            continue
        if basket is not None and report.basket != basket:
            continue
        runs.append(
            {
                "run_id": report.run_id,
                "basket": report.basket,
                "started_at": report.started_at,
                "finished_at": report.finished_at,
                "gate_decision": report.gate_decision,
                "rqs": report.aggregate_metrics.rqs,
                "pqs": report.aggregate_metrics.pqs,
                "rs": report.aggregate_metrics.rs,
                "ss": report.aggregate_metrics.ss,
                "es": report.aggregate_metrics.es,
                "total_scenarios": report.total_scenarios,
                "passed_count": report.passed_count,
                "failed_count": report.failed_count,
                "total_cost_usd": report.total_cost_usd,
                "avg_latency_s": report.avg_latency_s,
                "p95_latency_s": report.p95_latency_s,
            }
        )
    return runs


def list_baskets() -> list[str]:
    """Уникальные имена корзин, для которых есть хотя бы один прогон."""
    return sorted({r["basket"] for r in list_runs()})


def clear_cache() -> None:
    """Сбрасывает lru_cache load_report. Для использования в тестах."""
    load_report.cache_clear()


__all__ = [
    "REPORTS_ROOT",
    "GateDecision",
    "load_report",
    "list_runs",
    "list_baskets",
    "clear_cache",
    "datetime",  # реэкспорт удобен для views
]
