"""Streamlit dashboard: single-vs-multi-agent headline comparison. Read-only, no export step."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.data import (
    HEADLINE_COLUMNS,
    DashboardError,
    fetch_headline,
    fetch_latest_headline,
    fetch_runs,
)
from dashboard.format import order_solvers, to_display_table

st.set_page_config(page_title="Single vs. Multi-Agent SWE Benchmark", layout="wide")
st.title("Single vs. Multi-Agent SWE Benchmark")


@st.cache_data(ttl=60)
def _cached_runs() -> pd.DataFrame:
    """`fetch_runs()`, cached 60s so the sidebar picker doesn't re-query on every rerun."""
    return fetch_runs()


@st.cache_data(ttl=60)
def _cached_latest_headline() -> pd.DataFrame:
    """`fetch_latest_headline()`, cached 60s (the default view, covers NFR-15 on reruns)."""
    return fetch_latest_headline()


@st.cache_data(ttl=60)
def _cached_headline(run_ids: tuple[str, ...]) -> pd.DataFrame:
    """`fetch_headline(run_ids)`, cached 60s per distinct `run_ids` selection."""
    return fetch_headline(run_ids)


try:
    runs = _cached_runs()
except DashboardError as exc:
    st.error(f"Could not reach Postgres: {exc}\n\nCheck that DATABASE_URL is set and reachable.")
    st.stop()

if runs.empty:
    st.info(
        "No benchmark runs found. Run `make benchmark TASKS=lite-5 SOLVER=single` "
        "then `SOLVER=multi`, then reload."
    )
    st.stop()

st.sidebar.header("Run selection")
run_labels = {
    f"{row.solver} · {str(row.run_id)[:8]} · {row.run_finished_at}": str(row.run_id)
    for row in runs.itertuples()
}
use_latest = st.sidebar.checkbox("Latest per solver", value=True)

if use_latest:
    headline = _cached_latest_headline()
else:
    selected = st.sidebar.multiselect("Pick run(s)", options=list(run_labels))
    run_ids = tuple(run_labels[label] for label in selected)
    headline = _cached_headline(run_ids) if run_ids else pd.DataFrame(columns=HEADLINE_COLUMNS)

headline = order_solvers(headline)

st.dataframe(to_display_table(headline), hide_index=True, use_container_width=True)

plot_frame = headline.dropna(subset=["mean_cost_per_solved_task"])
dropped = len(headline) - len(plot_frame)

if plot_frame.empty:
    st.info("No rows with a solved task yet — the cost/success plot needs at least one PASS.")
else:
    chart = (
        alt.Chart(plot_frame)
        .mark_point(size=200, filled=True)
        .encode(
            x=alt.X("mean_cost_per_solved_task:Q", title="Mean cost per solved task ($)"),
            y=alt.Y("pass_rate_pct:Q", title="Success rate (%)"),
            color=alt.Color("solver:N", title="Solver"),
            tooltip=list(headline.columns),
        )
    )
    labels = chart.mark_text(align="left", dx=8, dy=-8).encode(text="solver:N")
    st.altair_chart(chart + labels, use_container_width=True)
    st.caption("Up and to the left is better: higher success rate at lower cost per solved task.")

    if dropped:
        st.caption(
            f"{dropped} row(s) with no solved tasks (null cost) omitted from the plot "
            "but shown in the table above."
        )
