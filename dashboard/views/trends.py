"""Вкладка «Динамика» дашборда: 3 линейных графика по последним прогонам."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render(basket: str, runs: list[dict[str, Any]]) -> None:
    if len(runs) < 2:
        st.info("Для построения динамики нужно минимум 2 прогона корзины.")
        return

    # Берём последние 30, разворачиваем по возрастанию времени для X-оси
    window = runs[:30][::-1]
    df = _to_dataframe(window)

    st.subheader("Сводные показатели по последним прогонам")
    _plot_aggregate_lines(df)

    st.subheader("Pass rate")
    _plot_pass_rate(df)

    st.subheader("Стоимость и латентность")
    _plot_cost_and_latency(df)


def _to_dataframe(runs: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(runs)
    df["pass_rate"] = df["passed_count"] / df["total_scenarios"].clip(lower=1)
    df["avg_cost_per_scenario"] = df["total_cost_usd"] / df["total_scenarios"].clip(lower=1)
    return df


def _plot_aggregate_lines(df: pd.DataFrame) -> None:
    long = df.melt(
        id_vars=["run_id", "started_at"],
        value_vars=["rqs", "pqs", "rs", "ss", "es"],
        var_name="метрика",
        value_name="значение",
    )
    long["метрика"] = long["метрика"].str.upper()
    fig = px.line(
        long,
        x="run_id",
        y="значение",
        color="метрика",
        hover_data=["started_at"],
        markers=True,
    )
    fig.update_layout(legend=dict(orientation="h", y=-0.2), yaxis_range=[0, 1.05])
    st.plotly_chart(fig, use_container_width=True)


def _plot_pass_rate(df: pd.DataFrame) -> None:
    fig = px.line(
        df,
        x="run_id",
        y="pass_rate",
        markers=True,
        hover_data=["started_at", "passed_count", "total_scenarios"],
    )
    fig.update_layout(yaxis_range=[0, 1.05], yaxis_tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)


def _plot_cost_and_latency(df: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["run_id"],
            y=df["avg_cost_per_scenario"],
            name="avg cost / сценарий ($)",
            mode="lines+markers",
            yaxis="y1",
            hovertemplate="run=%{x}<br>cost=%{y:.4f} $<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["run_id"],
            y=df["p95_latency_s"],
            name="p95 latency (s)",
            mode="lines+markers",
            yaxis="y2",
            hovertemplate="run=%{x}<br>p95=%{y:.2f}s<extra></extra>",
        )
    )
    fig.update_layout(
        yaxis=dict(title="Cost, $", side="left"),
        yaxis2=dict(title="Latency p95, s", overlaying="y", side="right"),
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig, use_container_width=True)
