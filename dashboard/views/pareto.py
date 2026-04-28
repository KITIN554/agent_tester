"""Вкладка «Парето» дашборда: scatter cost × RQS с выделенным фронтом."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import streamlit as st


def is_pareto_optimal(point: tuple[float, float], all_points: list[tuple[float, float]]) -> bool:
    """Точка (cost, rqs) на Парето-фронте, если её никто не доминирует.

    Доминирующая p1 имеет ≥ rqs И ≤ cost при минимум одном строгом неравенстве.
    """
    cost_x, rqs_x = point
    for p in all_points:
        if p == point:
            continue
        c, r = p
        if r >= rqs_x and c <= cost_x and (r > rqs_x or c < cost_x):
            return False
    return True


def render(basket: str, runs: list[dict[str, Any]]) -> None:
    points: list[tuple[str, float, float]] = []
    for r in runs[:30]:
        scen = max(r.get("total_scenarios", 0), 1)
        avg_cost = float(r["total_cost_usd"]) / scen
        rqs = float(r["rqs"])
        points.append((r["run_id"], avg_cost, rqs))

    if len(points) < 2:
        st.info("Для Парето-диаграммы нужно минимум 2 прогона.")
        return

    coords = [(c, r) for _, c, r in points]
    on_front = [is_pareto_optimal((c, r), coords) for _, c, r in points]

    st.subheader(f"Cost × RQS (точки на фронте: {sum(on_front)} из {len(on_front)})")

    fig = go.Figure()

    # Доминируемые — полые
    fig.add_trace(
        go.Scatter(
            x=[c for (rid, c, r), on in zip(points, on_front, strict=False) if not on],
            y=[r for (rid, c, r), on in zip(points, on_front, strict=False) if not on],
            mode="markers+text",
            marker=dict(
                size=10,
                color="white",
                line=dict(color="#888", width=2),
            ),
            text=[rid for (rid, c, r), on in zip(points, on_front, strict=False) if not on],
            textposition="top center",
            textfont=dict(size=9),
            name="Доминируемые",
            hovertemplate=("run=%{text}<br>cost=%{x:.4f} $<br>RQS=%{y:.3f}<extra></extra>"),
        )
    )
    # На Парето-фронте — закрашенные
    fig.add_trace(
        go.Scatter(
            x=[c for (rid, c, r), on in zip(points, on_front, strict=False) if on],
            y=[r for (rid, c, r), on in zip(points, on_front, strict=False) if on],
            mode="markers+text",
            marker=dict(size=12, color="#2e7d32"),
            text=[rid for (rid, c, r), on in zip(points, on_front, strict=False) if on],
            textposition="top center",
            textfont=dict(size=9),
            name="На Парето-фронте",
            hovertemplate=("run=%{text}<br>cost=%{x:.4f} $<br>RQS=%{y:.3f}<extra></extra>"),
        )
    )

    fig.update_layout(
        xaxis_title="Средняя стоимость на сценарий, $",
        yaxis_title="RQS",
        yaxis_range=[0, 1.05],
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Прогон Парето-оптимален, если нет другого с одновременно бо́льшим "
        "RQS и меньшей стоимостью на сценарий."
    )
