"""Главное Streamlit-приложение дашборда (spec 07).

Запуск: `streamlit run dashboard/app.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit запускает этот файл как скрипт — sys.path[0] становится
# `dashboard/`, а не корень проекта, поэтому `from dashboard.…` не резолвится.
# Добавляем родительскую директорию (корень проекта) до импортов пакета.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st  # noqa: E402

from dashboard.data_loader import list_baskets, list_runs, load_report  # noqa: E402
from dashboard.views import (  # noqa: E402
    heatmap,
    pareto,
    scenario,
    summary,
    trends,
    versions,
)


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

    tabs = st.tabs(
        [
            "📋 Сводка",
            "📈 Версии",
            "📊 Heatmap",
            "📈 Динамика",
            "🎯 Парето",
            "🔍 Сценарий",
        ]
    )
    with tabs[0]:
        summary.render(current_report, baseline_report)
    with tabs[1]:
        versions.render(basket, runs)
    with tabs[2]:
        heatmap.render(basket, runs)
    with tabs[3]:
        trends.render(basket, runs)
    with tabs[4]:
        pareto.render(basket, runs)
    with tabs[5]:
        scenario.render(current_report)


if __name__ == "__main__":
    main()
