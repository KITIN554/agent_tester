"""Вкладка «Versions» дашборда: сравнительная таблица v0/v1/v2 + миниграф."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render(basket: str, runs: list[dict[str, Any]]) -> None:
    if len(runs) < 2:
        st.info("Сравнение версий доступно при ≥2 прогонах корзины.")
        return

    run_ids = [r["run_id"] for r in runs]
    # Дефолты: v0 = первый по времени, v2 = последний, v1 — между ними.
    chronological = list(reversed(run_ids))  # старые → новые
    default_v1_idx = len(chronological) // 2 if len(chronological) >= 3 else len(chronological) - 1

    cols = st.columns(3)
    v0 = cols[0].selectbox("v0", chronological, index=0)
    v1 = cols[1].selectbox("v1", chronological, index=default_v1_idx)
    v2 = cols[2].selectbox("v2", chronological, index=len(chronological) - 1)

    versions = {"v0": v0, "v1": v1, "v2": v2}
    rows = _build_table(runs, versions)
    df = pd.DataFrame(rows)

    st.subheader(f"Сравнение версий: {basket}")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("RQS по версиям")
    rqs_values = [_lookup(runs, vid)["rqs"] for vid in versions.values()]
    fig = go.Figure(
        go.Bar(
            x=list(versions.keys()),
            y=rqs_values,
            text=[f"{v:.3f}" for v in rqs_values],
            textposition="outside",
            marker_color=["#1565c0", "#1565c0", "#1565c0"],
        )
    )
    fig.update_layout(
        yaxis_range=[0, max(rqs_values) * 1.1 if rqs_values else 1],
        height=300,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _build_table(runs: list[dict[str, Any]], versions: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric_key, label in (
        ("rqs", "RQS"),
        ("pqs", "PQS"),
        ("rs", "RS"),
        ("ss", "SS"),
        ("es", "ES"),
        ("total_cost_usd", "cost, $"),
        ("avg_latency_s", "avg latency, s"),
    ):
        vals = {v: float(_lookup(runs, vid).get(metric_key, 0.0)) for v, vid in versions.items()}
        rows.append(
            {
                "Метрика": label,
                "v0": _fmt(vals["v0"], metric_key),
                "v1": _fmt(vals["v1"], metric_key),
                "v2": _fmt(vals["v2"], metric_key),
                "Δ(v1-v0)": _fmt_delta(vals["v1"] - vals["v0"], metric_key),
                "Δ(v2-v1)": _fmt_delta(vals["v2"] - vals["v1"], metric_key),
            }
        )

    # Pass rate отдельной строкой
    def pr(vid: str) -> float:
        r = _lookup(runs, vid)
        total = r.get("total_scenarios", 0) or 1
        return r.get("passed_count", 0) / total

    pr_vals = {v: pr(vid) for v, vid in versions.items()}
    rows.append(
        {
            "Метрика": "pass rate",
            "v0": f"{pr_vals['v0']:.1%}",
            "v1": f"{pr_vals['v1']:.1%}",
            "v2": f"{pr_vals['v2']:.1%}",
            "Δ(v1-v0)": _fmt_delta(pr_vals["v1"] - pr_vals["v0"], "pct"),
            "Δ(v2-v1)": _fmt_delta(pr_vals["v2"] - pr_vals["v1"], "pct"),
        }
    )
    return rows


def _lookup(runs: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    for r in runs:
        if r["run_id"] == run_id:
            return r
    return {}


def _fmt(value: float, key: str) -> str:
    if key == "total_cost_usd":
        return f"{value:.4f}"
    if key == "avg_latency_s":
        return f"{value:.2f}"
    return f"{value:.3f}"


def _fmt_delta(delta: float, key: str) -> str:
    if abs(delta) < 1e-9:
        return "0"
    sign = "+" if delta > 0 else ""
    if key == "pct":
        return f"{sign}{delta * 100:.1f}pp"
    if key == "total_cost_usd":
        return f"{sign}{delta:.4f}"
    if key == "avg_latency_s":
        return f"{sign}{delta:.2f}"
    return f"{sign}{delta:.3f}"
