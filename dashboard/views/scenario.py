"""Вкладка «Сценарий» дашборда: детальный разбор одного сценария."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tester.models import RunReport, ScenarioOutcome


def render(report: RunReport) -> None:
    if not report.outcomes:
        st.info("В этом прогоне нет сценариев.")
        return

    options = [o.scenario.id for o in report.outcomes]
    selected_id = st.selectbox("Сценарий", options=options)
    outcome = next(o for o in report.outcomes if o.scenario.id == selected_id)

    _render_meta(outcome)
    _render_answer(outcome)
    _render_rubrics(outcome)
    _render_metrics(outcome)
    _render_trace(outcome)


def _render_meta(outcome: ScenarioOutcome) -> None:
    sc = outcome.scenario
    st.markdown(f"### {sc.id}  \n*{sc.description}*")
    cols = st.columns(4)
    cols[0].markdown(f"**Категория:** `{sc.category.value}`")
    cols[1].markdown(f"**Тип:** `{sc.type.value}`")
    cols[2].markdown(f"**Система:** `{sc.system}`")
    status = "✅ pass" if outcome.passed else "❌ fail"
    cols[3].markdown(f"**Результат:** {status}")


def _render_answer(outcome: ScenarioOutcome) -> None:
    st.subheader("Финальный ответ агента")
    st.code(outcome.trace.final_answer or "(пусто)", language="text")
    if outcome.trace.error:
        st.error(f"Ошибка прогона: {outcome.trace.error}")


def _render_rubrics(outcome: ScenarioOutcome) -> None:
    st.subheader("Рубрики (LLM-as-a-Judge)")
    if not outcome.rubric_evaluations:
        st.caption("Рубрики не оценивались.")
        return
    df = pd.DataFrame(
        [
            {
                "Рубрика": ev.rubric,
                "Вердикт": ev.verdict.value,
                "Score": ev.score if ev.score is not None else "—",
                "Обоснование": ev.rationale,
            }
            for ev in outcome.rubric_evaluations
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_metrics(outcome: ScenarioOutcome) -> None:
    pm = outcome.process_metrics
    sm = outcome.safety_metrics

    st.subheader("Метрики процесса")
    process_rows = [
        ("step_accuracy", pm.step_accuracy),
        ("tool_selection_accuracy", pm.tool_selection_accuracy),
        ("parameter_extraction_accuracy", pm.parameter_extraction_accuracy),
        ("tool_call_correctness", pm.tool_call_correctness),
        ("step_compliance", pm.step_compliance),
        ("scenario_completion", pm.scenario_completion),
    ]
    st.dataframe(
        pd.DataFrame(process_rows, columns=["Метрика", "Значение"]),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Метрики безопасности")
    safety_rows = [
        ("policy_violation", sm.policy_violation),
        ("pii_leakage", sm.pii_leakage),
        (
            "refusal_correct",
            sm.refusal_correct if sm.refusal_correct is not None else "—",
        ),
    ]
    st.dataframe(
        pd.DataFrame(safety_rows, columns=["Метрика", "Значение"]),
        use_container_width=True,
        hide_index=True,
    )


def _render_trace(outcome: ScenarioOutcome) -> None:
    with st.expander(f"Полная трасса ({len(outcome.trace.steps)} шагов)", expanded=False):
        if not outcome.trace.steps:
            st.caption("Трасса пуста.")
            return
        for step in outcome.trace.steps:
            st.markdown(f"**[{step.step_id}] {step.step_type.value}**")
            st.json(step.content)
