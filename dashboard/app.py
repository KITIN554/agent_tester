"""Главное Streamlit-приложение дашборда (spec 07).

Запуск: `streamlit run dashboard/app.py`
"""

from __future__ import annotations

import streamlit as st

from dashboard.data_loader import list_baskets, list_runs, load_report
from dashboard.views import pareto, scenario, summary, trends


def main() -> None:
    st.set_page_config(
        page_title="Agent Tester Dashboard",
        layout="wide",
    )
    st.title("Agent Tester — методология тестирования агентских систем")

    baskets = list_baskets()
    if not baskets:
        st.info(
            "В `reports/runs/` нет ни одного прогона. Запусти "
            "`tester run --basket baskets/finance_agent`, чтобы увидеть данные."
        )
        st.stop()

    with st.sidebar:
        st.header("🎛️ Фильтры")
        basket = st.selectbox("Корзина", options=baskets)
        runs = list_runs(basket=basket)
        if not runs:
            st.info(f"Для корзины {basket} пока нет прогонов.")
            st.stop()

        run_ids = [r["run_id"] for r in runs]
        current_run_id = st.selectbox("Текущий прогон", options=run_ids)
        baseline_options = ["—"] + [r for r in run_ids if r != current_run_id]
        baseline_run_id = st.selectbox("Сравнить с (baseline)", options=baseline_options)

    current_report = load_report(current_run_id)
    baseline_report = load_report(baseline_run_id) if baseline_run_id != "—" else None

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Сводка", "📈 Динамика", "🎯 Парето", "🔍 Сценарий"])
    with tab1:
        summary.render(current_report, baseline_report)
    with tab2:
        trends.render(basket, runs)
    with tab3:
        pareto.render(basket, runs)
    with tab4:
        scenario.render(current_report)


if __name__ == "__main__":
    main()
