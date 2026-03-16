"""Page 3 — Performance Over Time"""
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from utils.data_loader import apply_filters, load_matches, DEFAULT_CLUB

st.set_page_config(page_title="Performance Over Time", layout="wide")
st.title("Performance Over Time")

# --- load & filter ---
df = load_matches()
date_range = st.session_state.get("date_range")
event_cats = st.session_state.get("event_categories")
incl_unaff = st.session_state.get("include_unaffiliated", True)
df = apply_filters(df, date_range=date_range, event_categories=event_cats, include_unaffiliated=incl_unaff)
df = df[df["date"].notna()]

# --- controls ---
all_clubs = sorted(df["player_club"].dropna().unique().tolist())

# Default: Danderyds TK + 2 clubs with most matches after filtering
top_by_matches = (
    df[df["player_club"] != DEFAULT_CLUB]
    .groupby("player_club")["match_id"].count()
    .nlargest(2)
    .index.tolist()
)
default_clubs = [DEFAULT_CLUB] + top_by_matches if DEFAULT_CLUB in all_clubs else all_clubs[:3]

selected_clubs = st.multiselect("Select clubs to compare", all_clubs, default=default_clubs)
if not selected_clubs:
    st.warning("Select at least one club.")
    st.stop()

col1, col2 = st.columns(2)
metric = col1.radio("Metric", ["Win Rate", "Match Count", "Win Count"], horizontal=True)
granularity = col2.radio("Granularity", ["Monthly", "Quarterly"], horizontal=True)

period_col = "year_month" if granularity == "Monthly" else "quarter"

# --- aggregate ---
dff = df[df["player_club"].isin(selected_clubs) & df[period_col].notna()].copy()

if metric == "Win Rate":
    agg = (
        dff.groupby(["player_club", period_col])
        .agg(wins=("won", "sum"), matches=("match_id", "count"))
        .reset_index()
    )
    agg["value"] = agg["wins"] / agg["matches"]
    y_label = "Win Rate"
elif metric == "Match Count":
    agg = dff.groupby(["player_club", period_col])["match_id"].count().reset_index()
    agg.columns = ["player_club", period_col, "value"]
    y_label = "Matches"
else:
    agg = dff[dff["won"]].groupby(["player_club", period_col])["match_id"].count().reset_index()
    agg.columns = ["player_club", period_col, "value"]
    y_label = "Wins"

agg = agg.sort_values(period_col)

# --- chart ---
fig = go.Figure()

colors = ["#FF6B35", "#4A90D9", "#2ECC71", "#9B59B6", "#E74C3C", "#1ABC9C"]
for i, club in enumerate(selected_clubs):
    club_data = agg[agg["player_club"] == club]
    is_danderyds = club == DEFAULT_CLUB
    fig.add_trace(
        go.Scatter(
            x=club_data[period_col].astype(str),
            y=club_data["value"],
            mode="lines+markers",
            name=club,
            line=dict(
                color=colors[i % len(colors)],
                width=4 if is_danderyds else 1.5,
            ),
            marker=dict(size=6 if is_danderyds else 4),
        )
    )

yaxis_fmt = ".0%" if metric == "Win Rate" else None
fig.update_layout(
    xaxis_title=granularity,
    yaxis_title=y_label,
    yaxis_tickformat=yaxis_fmt,
    legend_title="Club",
    height=500,
)
st.plotly_chart(fig, use_container_width=True)
