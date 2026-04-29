"""Вкладка «Heatmap» дашборда: scenario × run матрица passed/failed."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.data_loader import load_report


def render(basket: str, runs: list[dict[str, Any]]) -> None:
    if len(runs) < 2:
        st.info("Heatmap появится при ≥2 прогонах корзины.")
        return

    window = runs[:30]
    matrix, scenario_ids, run_ids = _build_matrix(window)

    if not scenario_ids:
        st.info("В выбранных прогонах нет сценариев.")
        return

    st.subheader(f"Сценарии × прогоны (последние {len(run_ids)} прогонов корзины {basket})")

    fig = go.Figure(
        go.Heatmap(
            z=matrix,
            x=run_ids,
            y=scenario_ids,
            colorscale=[
                [0.0, "#c62828"],  # failed
                [0.5, "#bdbdbd"],  # not present in run
                [1.0, "#2e7d32"],  # passed
            ],
            zmin=-1,
            zmax=1,
            showscale=False,
            hovertemplate=("scenario=%{y}<br>run=%{x}<br>state=%{customdata}<extra></extra>"),
            customdata=_state_labels(matrix),
        )
    )
    fig.update_layout(
        height=max(300, 18 * len(scenario_ids)),
        xaxis=dict(side="top", tickangle=-45),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=120, t=80, b=20, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Зелёный = passed, красный = failed, серый = сценарий ещё/уже "
        "не входил в корзину этого прогона."
    )


def _build_matrix(
    runs: list[dict[str, Any]],
) -> tuple[list[list[float]], list[str], list[str]]:
    """Строит матрицу значений {-1=failed, 0=missing, +1=passed}."""
    per_run_passed: dict[str, dict[str, bool]] = {}
    all_ids: set[str] = set()
    for r in runs:
        try:
            report = load_report(r["run_id"])
        except Exception:  # noqa: BLE001
            continue
        run_map: dict[str, bool] = {}
        for outcome in report.outcomes:
            run_map[outcome.scenario.id] = bool(outcome.passed)
            all_ids.add(outcome.scenario.id)
        per_run_passed[r["run_id"]] = run_map

    if not per_run_passed:
        return [], [], []

    scenario_ids = sorted(all_ids)
    run_ids = list(per_run_passed.keys())
    # Hot ↔ cold: новые run-id (по убыванию) — слева
    matrix: list[list[float]] = []
    for sid in scenario_ids:
        row: list[float] = []
        for rid in run_ids:
            run_map = per_run_passed[rid]
            if sid not in run_map:
                row.append(0.0)
            elif run_map[sid]:
                row.append(1.0)
            else:
                row.append(-1.0)
        matrix.append(row)
    return matrix, scenario_ids, run_ids


def _state_labels(matrix: list[list[float]]) -> list[list[str]]:
    return [
        ["passed" if v > 0 else "failed" if v < 0 else "missing" for v in row] for row in matrix
    ]


# Подавление impossible-import предупреждения для pandas (нет прямого
# использования здесь, но импорт удобен для виджета в будущем).
_ = pd
