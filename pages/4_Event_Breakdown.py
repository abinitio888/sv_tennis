"""Page 4 — Event Breakdown"""
import plotly.express as px
import pandas as pd
import streamlit as st

from utils.data_loader import apply_filters, load_matches, DEFAULT_CLUB, ALL_CATEGORIES

st.set_page_config(page_title="Event Breakdown", layout="wide")
st.title("Event Breakdown")

# --- load & filter ---
df = load_matches()
date_range = st.session_state.get("date_range")
event_cats = st.session_state.get("event_categories")
incl_unaff = st.session_state.get("include_unaffiliated", True)
df = apply_filters(df, date_range=date_range, event_categories=event_cats, include_unaffiliated=incl_unaff)

# --- controls ---
all_clubs = sorted(df["player_club"].dropna().unique().tolist())
default_clubs = [DEFAULT_CLUB] if DEFAULT_CLUB in all_clubs else all_clubs[:1]
selected_clubs = st.multiselect("Select clubs (up to 5)", all_clubs, default=default_clubs, max_selections=5)

if not selected_clubs:
    st.warning("Select at least one club.")
    st.stop()

metric = st.radio("Metric", ["Win Rate", "Match Count"], horizontal=True)

dff = df[df["player_club"].isin(selected_clubs)]

# --- grouped bar chart ---
st.subheader(f"{metric} by Event Category")

agg = (
    dff.groupby(["player_club", "event_category"])
    .agg(matches=("match_id", "count"), wins=("won", "sum"))
    .reset_index()
)
agg["win_rate"] = agg["wins"] / agg["matches"]
agg["value"] = agg["win_rate"] if metric == "Win Rate" else agg["matches"]

bar_fig = px.bar(
    agg,
    x="event_category",
    y="value",
    color="player_club",
    barmode="group",
    labels={"event_category": "Event Category", "value": metric, "player_club": "Club"},
    color_discrete_sequence=px.colors.qualitative.Set2,
)
if metric == "Win Rate":
    bar_fig.update_layout(yaxis_tickformat=".0%")
bar_fig.update_layout(xaxis_tickangle=-30)
st.plotly_chart(bar_fig, use_container_width=True)

# --- donut chart: Danderyds TK volume distribution ---
st.divider()
st.subheader("Danderyds TK — Match Volume by Event Category")

dtk = df[df["player_club"] == DEFAULT_CLUB]
if dtk.empty:
    st.info("No Danderyds TK data with current filters.")
else:
    vol = dtk.groupby("event_category")["match_id"].count().reset_index()
    vol.columns = ["event_category", "count"]
    donut = px.pie(
        vol,
        names="event_category",
        values="count",
        hole=0.45,
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    donut.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(donut, use_container_width=True)
