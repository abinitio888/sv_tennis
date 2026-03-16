"""Page 2 — Club Comparison"""
import plotly.express as px
import pandas as pd
import streamlit as st

from utils.data_loader import apply_filters, load_matches, DEFAULT_CLUB

st.set_page_config(page_title="Club Comparison", layout="wide")
st.title("Club Comparison")

# --- load & filter ---
df = load_matches()
date_range = st.session_state.get("date_range")
event_cats = st.session_state.get("event_categories")
incl_unaff = st.session_state.get("include_unaffiliated", True)
df = apply_filters(df, date_range=date_range, event_categories=event_cats, include_unaffiliated=incl_unaff)

# --- compute per-club stats ---
cutoff = pd.Timestamp.now() - pd.DateOffset(months=12)

total_players = df.groupby("player_club")["player_id"].nunique().rename("total_players")
active_players = (
    df[df["date"] >= cutoff].groupby("player_club")["player_id"].nunique().rename("active_players_12m")
)
total_matches = df.groupby("player_club")["match_id"].count().rename("total_matches")
total_wins = df.groupby("player_club")["won"].sum().rename("total_wins")
total_tournaments = df.groupby("player_club")["tournament_id"].nunique().rename("total_tournaments")

clubs = pd.concat([total_players, active_players, total_matches, total_wins, total_tournaments], axis=1).reset_index()
clubs.columns = ["club", "total_players", "active_players_12m", "total_matches", "total_wins", "total_tournaments"]
clubs["active_players_12m"] = clubs["active_players_12m"].fillna(0).astype(int)
clubs["win_rate"] = clubs["total_wins"] / clubs["total_matches"]

# --- controls ---
col1, col2, col3 = st.columns(3)
kpi_options = {
    "Win Rate": "win_rate",
    "Total Players": "total_players",
    "Active Players (12m)": "active_players_12m",
    "Total Matches": "total_matches",
    "Wins": "total_wins",
    "Tournaments": "total_tournaments",
}
kpi_label = col1.selectbox("KPI", list(kpi_options.keys()))
kpi_col = kpi_options[kpi_label]
top_n = col2.slider("Top N clubs", 10, 50, 20)
min_players = col3.slider("Min players", 1, 50, 5)

filtered = clubs[clubs["total_players"] >= min_players].nlargest(top_n, kpi_col)

# Assign color — Danderyds TK in orange, others in steelblue
filtered = filtered.copy()
filtered["color"] = filtered["club"].apply(
    lambda c: "#FF6B35" if c == DEFAULT_CLUB else "#4A90D9"
)
filtered = filtered.sort_values(kpi_col)

# --- horizontal bar chart ---
st.subheader(f"Top {top_n} Clubs by {kpi_label}")

bar_fig = px.bar(
    filtered,
    x=kpi_col,
    y="club",
    orientation="h",
    color="club",
    color_discrete_map={c: col for c, col in zip(filtered["club"], filtered["color"])},
    labels={kpi_col: kpi_label, "club": "Club"},
    text=kpi_col,
)
bar_fig.update_traces(texttemplate="%{text:.1%}" if kpi_col == "win_rate" else "%{text:,}", textposition="outside")
bar_fig.update_layout(showlegend=False, height=max(400, len(filtered) * 22))
st.plotly_chart(bar_fig, use_container_width=True)

# --- scatter: active players vs win rate ---
st.subheader("Active Players vs Win Rate")

scatter_data = clubs[clubs["total_players"] >= min_players].copy()
scatter_data["is_danderyds"] = scatter_data["club"] == DEFAULT_CLUB
scatter_data["color"] = scatter_data["is_danderyds"].map({True: "#FF6B35", False: "#4A90D9"})

scatter_fig = px.scatter(
    scatter_data,
    x="active_players_12m",
    y="win_rate",
    size="total_matches",
    color="club",
    color_discrete_map={c: col for c, col in zip(scatter_data["club"], scatter_data["color"])},
    hover_name="club",
    labels={"active_players_12m": "Active Players (12m)", "win_rate": "Win Rate", "total_matches": "Match Count"},
    text=scatter_data["club"].where(scatter_data["is_danderyds"], other=""),
)
scatter_fig.update_traces(textposition="top center")
scatter_fig.update_layout(showlegend=False, yaxis_tickformat=".0%")
st.plotly_chart(scatter_fig, use_container_width=True)
