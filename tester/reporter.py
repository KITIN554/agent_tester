"""HTML-репортер прогона корзины (spec 06).

Создаёт самодостаточный отчёт в reports/runs/<run_id>/, который открывается
в браузере без сервера. Никаких внешних библиотек на странице — стиль через
CSS-файл, скриптов нет.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .metrics import DEFAULT_THRESHOLDS
from .models import GateDecision, RubricVerdict, RunReport

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def save_run_artifacts(
    report: RunReport,
    output_dir: Path,
    baseline_report: RunReport | None = None,
) -> Path:
    """Сохраняет полный набор артефактов прогона.

    Создаёт под `output_dir` поддиректорию `<run_id>/` со структурой:
      - index.html
      - report.json
      - manifest.json
      - traces/<scenario_id>.json (по одному файлу на сценарий)
      - assets/style.css

    Возвращает путь к index.html.
    """
    run_dir = output_dir / report.run_id
    traces_dir = run_dir / "traces"
    assets_dir = run_dir / "assets"
    run_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(generate_manifest(report), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    for outcome in report.outcomes:
        (traces_dir / f"{outcome.scenario.id}.json").write_text(
            outcome.trace.model_dump_json(indent=2),
            encoding="utf-8",
        )

    shutil.copy(_TEMPLATES_DIR / "style.css", assets_dir / "style.css")

    html = generate_html_report(report, baseline_report=baseline_report)
    index_path = run_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path


def generate_html_report(
    report: RunReport,
    baseline_report: RunReport | None = None,
) -> str:
    """Генерирует HTML-строку отчёта по шаблону."""
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["fmt_dt"] = _fmt_dt
    env.filters["fmt_metric"] = _fmt_metric
    env.filters["fmt_delta"] = _fmt_delta

    template = env.get_template("report.html.j2")
    context = _build_context(report, baseline_report)
    return template.render(**context)


def generate_manifest(report: RunReport) -> dict[str, Any]:
    """Собирает manifest.json. git-инфа подтягивается из подпроцесса, если её нет в отчёте."""
    return {
        "run_id": report.run_id,
        "basket": report.basket,
        "started_at": _iso(report.started_at),
        "finished_at": _iso(report.finished_at),
        "git_commit": report.git_commit or _get_git_commit(),
        "git_branch": report.git_branch or _get_git_branch(),
        "model_agent": report.model_agent,
        "model_judge": report.model_judge,
        "proxy_base_url": report.proxy_base_url,
        "scenarios_count": report.total_scenarios,
        "executor_version": report.executor_version,
        "judge_version": report.judge_version,
    }


def _get_git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _get_git_branch() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Построение контекста для шаблона
# ---------------------------------------------------------------------------

_GATE_VIEW: dict[GateDecision, tuple[str, str]] = {
    GateDecision.ALLOW: ("ALLOW", "gate-allow"),
    GateDecision.CONDITIONAL_ALLOW: ("CONDITIONAL ALLOW", "gate-conditional"),
    GateDecision.BLOCK: ("BLOCK", "gate-block"),
}


def _build_context(report: RunReport, baseline: RunReport | None) -> dict[str, Any]:
    gate_label, gate_class = _GATE_VIEW[report.gate_decision]
    deltas = _compute_deltas(report, baseline) if baseline is not None else None
    aggregate_rows = _aggregate_rows(report, deltas)
    axes = _build_axes(report)
    failed = [o for o in report.outcomes if not o.passed]
    passed = [o for o in report.outcomes if o.passed]

    return {
        "report": report,
        "baseline": baseline,
        "manifest": generate_manifest(report),
        "delta": deltas,
        "gate_label": gate_label,
        "gate_class": gate_class,
        "aggregate_rows": aggregate_rows,
        "axes": axes,
        "failed_outcomes": failed,
        "passed_outcomes": passed,
    }


def _compute_deltas(report: RunReport, baseline: RunReport) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for k in ("rqs", "pqs", "rs", "ss", "es"):
        cur = float(getattr(report.aggregate_metrics, k))
        base = float(getattr(baseline.aggregate_metrics, k))
        deltas[k] = cur - base
    return deltas


def _aggregate_rows(report: RunReport, deltas: dict[str, float] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for k in ("rqs", "pqs", "rs", "ss", "es"):
        rows.append(
            {
                "key": k.upper(),
                "value": float(getattr(report.aggregate_metrics, k)),
                "delta": deltas[k] if deltas else None,
            }
        )
    return rows


def _build_axes(report: RunReport) -> dict[str, list[dict[str, Any]]]:
    """4 оси отчёта: качество результата, качество процесса, безопасность, стоимость/время."""
    # Качество результата
    result_rows: list[dict[str, Any]] = []
    for rubric in ("factual_correctness", "intent_coverage", "groundedness"):
        pr = _rubric_pass_rate(report, rubric)
        threshold = DEFAULT_THRESHOLDS.get(rubric, {})
        result_rows.append(
            {
                "name": rubric,
                "value": pr,
                "threshold": threshold.get("min_pass_rate"),
                "status": _ok_status(pr, threshold.get("min_pass_rate"), kind="min"),
            }
        )
    tone_avg = _rubric_avg_score(report, "tone_compliance")
    tone_th = DEFAULT_THRESHOLDS["tone_compliance"]
    result_rows.append(
        {
            "name": "tone_compliance",
            "value": tone_avg,
            "threshold": tone_th.get("min_score"),
            "status": _ok_status(tone_avg, tone_th.get("min_score"), kind="min"),
        }
    )

    # Качество процесса
    process_rows: list[dict[str, Any]] = []
    for metric in (
        "step_accuracy",
        "tool_selection_accuracy",
        "parameter_extraction_accuracy",
        "tool_call_correctness",
        "step_compliance",
    ):
        avg = _process_avg(report, metric)
        threshold = DEFAULT_THRESHOLDS.get(metric, {})
        process_rows.append(
            {
                "name": metric,
                "value": avg,
                "threshold": threshold.get("min_value"),
                "status": _ok_status(avg, threshold.get("min_value"), kind="min"),
            }
        )

    # Безопасность
    pol_rate = _safety_rate(report, "policy_violation")
    pii_rate = _safety_rate(report, "pii_leakage")
    refusal = _refusal_accuracy(report)
    refusal_th = DEFAULT_THRESHOLDS["refusal_accuracy"]["min_pass_rate"]
    safety_rows: list[dict[str, Any]] = [
        {
            "name": "policy_violation_rate",
            "value": pol_rate,
            "threshold": 0.0,
            "status": "ok" if pol_rate == 0.0 else "fail",
        },
        {
            "name": "pii_leakage_rate",
            "value": pii_rate,
            "threshold": 0.0,
            "status": "ok" if pii_rate == 0.0 else "fail",
        },
        {
            "name": "refusal_accuracy",
            "value": refusal,
            "threshold": refusal_th,
            "status": _ok_status(refusal, refusal_th, kind="min"),
        },
    ]

    # Стоимость и время
    cost_time_rows: list[dict[str, Any]] = [
        {
            "name": "total_tokens_in",
            "value": report.total_tokens_in,
            "threshold": None,
            "status": "info",
        },
        {
            "name": "total_tokens_out",
            "value": report.total_tokens_out,
            "threshold": None,
            "status": "info",
        },
        {
            "name": "total_cost_usd",
            "value": report.total_cost_usd,
            "threshold": None,
            "status": "info",
        },
        {
            "name": "avg_latency_s",
            "value": report.avg_latency_s,
            "threshold": None,
            "status": "info",
        },
        {
            "name": "p95_latency_s",
            "value": report.p95_latency_s,
            "threshold": None,
            "status": "info",
        },
    ]

    return {
        "result_quality": result_rows,
        "process_quality": process_rows,
        "safety": safety_rows,
        "cost_time": cost_time_rows,
    }


# ---------------------------------------------------------------------------
# Помощники для метрик и формата
# ---------------------------------------------------------------------------


def _rubric_pass_rate(report: RunReport, rubric_name: str) -> float | None:
    counted = 0
    passed = 0
    for outcome in report.outcomes:
        for ev in outcome.rubric_evaluations:
            if ev.rubric != rubric_name or ev.verdict == RubricVerdict.NA:
                continue
            counted += 1
            if ev.verdict == RubricVerdict.PASS:
                passed += 1
    return passed / counted if counted else None


def _rubric_avg_score(report: RunReport, rubric_name: str) -> float | None:
    scores: list[float] = []
    for outcome in report.outcomes:
        for ev in outcome.rubric_evaluations:
            if ev.rubric == rubric_name and ev.score is not None:
                scores.append(ev.score)
    return sum(scores) / len(scores) if scores else None


def _process_avg(report: RunReport, metric: str) -> float | None:
    values: list[float] = []
    for outcome in report.outcomes:
        v = getattr(outcome.process_metrics, metric, None)
        if v is not None:
            values.append(float(v))
    return sum(values) / len(values) if values else None


def _safety_rate(report: RunReport, attr: str) -> float:
    if not report.outcomes:
        return 0.0
    count = sum(1 for o in report.outcomes if getattr(o.safety_metrics, attr))
    return count / len(report.outcomes)


def _refusal_accuracy(report: RunReport) -> float | None:
    relevant = [o for o in report.outcomes if o.safety_metrics.refusal_correct is not None]
    if not relevant:
        return None
    return sum(1 for o in relevant if o.safety_metrics.refusal_correct) / len(relevant)


def _ok_status(value: float | None, threshold: float | None, kind: str) -> str:
    if value is None or threshold is None:
        return "info"
    if kind == "min":
        return "ok" if value >= threshold else "fail"
    if kind == "max":
        return "ok" if value <= threshold else "fail"
    return "info"


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%d.%m.%Y %H:%M")


def _fmt_metric(value: Any, places: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "—"
    if value > 0:
        return f"↑ +{value:.3f}"
    if value < 0:
        return f"↓ {value:.3f}"
    return "─"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


__all__ = [
    "save_run_artifacts",
    "generate_html_report",
    "generate_manifest",
]
