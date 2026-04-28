"""Вкладка «Сводка» дашборда (spec 07)."""

from __future__ import annotations

import streamlit as st

from tester.models import GateDecision, RunReport

_GATE_COLORS = {
    GateDecision.ALLOW: "#2e7d32",
    GateDecision.CONDITIONAL_ALLOW: "#f9a825",
    GateDecision.BLOCK: "#c62828",
}
_GATE_LABELS = {
    GateDecision.ALLOW: "ALLOW",
    GateDecision.CONDITIONAL_ALLOW: "CONDITIONAL ALLOW",
    GateDecision.BLOCK: "BLOCK",
}


def render(report: RunReport, baseline: RunReport | None) -> None:
    _render_gate_badge(report)
    st.divider()
    _render_aggregate_cards(report, baseline)
    st.divider()
    _render_quick_stats(report)
    st.divider()
    _render_failure_list(report)


def _render_gate_badge(report: RunReport) -> None:
    color = _GATE_COLORS[report.gate_decision]
    label = _GATE_LABELS[report.gate_decision]
    st.markdown(
        f"""
<div style="background:{color}; color:white; padding:24px; border-radius:8px;
            text-align:center; font-size:2em; font-weight:700;">
{label}
</div>
""",
        unsafe_allow_html=True,
    )
    if report.gate_reasons:
        st.markdown("**Обоснование:**")
        for reason in report.gate_reasons:
            st.markdown(f"- {reason}")
    else:
        st.caption("Все условия выполнены.")


def _render_aggregate_cards(report: RunReport, baseline: RunReport | None) -> None:
    cols = st.columns(5)
    for col, key in zip(cols, ("rqs", "pqs", "rs", "ss", "es"), strict=False):
        cur = float(getattr(report.aggregate_metrics, key))
        delta_str = None
        if baseline is not None:
            base = float(getattr(baseline.aggregate_metrics, key))
            delta_str = f"{cur - base:+.3f}"
        col.metric(
            label=key.upper(),
            value=f"{cur:.3f}",
            delta=delta_str,
        )


def _render_quick_stats(report: RunReport) -> None:
    pass_rate = report.passed_count / report.total_scenarios if report.total_scenarios else 0.0
    cols = st.columns(4)
    cols[0].metric("Сценариев", report.total_scenarios)
    cols[1].metric("Прошло", report.passed_count)
    cols[2].metric("Pass rate", f"{pass_rate:.1%}")
    cols[3].metric("Стоимость, $", f"{report.total_cost_usd:.4f}")


def _render_failure_list(report: RunReport) -> None:
    failed = [o for o in report.outcomes if not o.passed]
    st.subheader(f"Провалы: {len(failed)} из {report.total_scenarios}")
    if not failed:
        st.success("Провалов нет.")
        return
    for outcome in failed[:10]:
        with st.container(border=True):
            st.markdown(
                f"**{outcome.scenario.id}** — "
                f"`{outcome.scenario.category.value}` · "
                f"{outcome.scenario.description}"
            )
            st.markdown(f"Ответ агента: `{outcome.trace.final_answer or '(пусто)'}`")
            failed_rubrics = [
                f"{ev.rubric}={ev.verdict.value}"
                for ev in outcome.rubric_evaluations
                if ev.verdict.value in ("fail", "partial")
            ]
            if failed_rubrics:
                st.caption("Просевшие рубрики: " + ", ".join(failed_rubrics))
            if outcome.trace.error:
                st.caption(f"Ошибка: {outcome.trace.error}")
