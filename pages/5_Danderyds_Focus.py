"""Page 5 — Danderyds TK Focus"""
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from utils.data_loader import apply_filters, load_matches, load_player_club_map, DEFAULT_CLUB

st.set_page_config(page_title="Danderyds Focus", layout="wide")
st.title(f"🟠 {DEFAULT_CLUB} — Deep Dive")

# --- load & filter ---
df_all = load_matches()
club_map = load_player_club_map()

date_range = st.session_state.get("date_range")
event_cats = st.session_state.get("event_categories")
incl_unaff = st.session_state.get("include_unaffiliated", True)
df_all = apply_filters(df_all, date_range=date_range, event_categories=event_cats, include_unaffiliated=incl_unaff)

dtk = df_all[df_all["player_club"] == DEFAULT_CLUB].copy()

if dtk.empty:
    st.warning("No Danderyds TK data with current filters.")
    st.stop()

# =========================================================================
# Summary scorecards
# =========================================================================
st.subheader("Summary")

cutoff_12m = pd.Timestamp.now() - pd.DateOffset(months=12)
total_players = dtk["player_id"].nunique()
active_players = dtk[dtk["date"] >= cutoff_12m]["player_id"].nunique()
total_matches = len(dtk)
total_wins = int(dtk["won"].sum())
win_rate = total_wins / total_matches if total_matches else 0
total_tournaments = dtk["tournament_id"].nunique()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Players", total_players)
c2.metric("Active (12m)", active_players)
c3.metric("Win Rate", f"{win_rate:.1%}")
c4.metric("Total Matches", total_matches)
c5.metric("Wins", total_wins)
c6.metric("Tournaments", total_tournaments)

st.divider()

# =========================================================================
# Head-to-Head vs other clubs
# =========================================================================
st.subheader("Head-to-Head vs Other Clubs")

# Resolve opponent club via player_club_map
dtk = dtk.copy()
dtk["opponent_club"] = dtk["opponent_profile_url"].str.upper().map(club_map).fillna("Unknown")

h2h = (
    dtk[dtk["opponent_club"] != "Unknown"]
    .groupby("opponent_club")
    .agg(matches=("match_id", "count"), wins=("won", "sum"))
    .reset_index()
)
h2h["win_rate"] = h2h["wins"] / h2h["matches"]
h2h = h2h[h2h["opponent_club"] != DEFAULT_CLUB]  # exclude self-matches
h2h = h2h[h2h["matches"] >= 3].sort_values("win_rate")

if h2h.empty:
    st.info("Not enough H2H data with current filters (min 3 matches per opponent club).")
else:
    h2h["color"] = h2h["win_rate"].apply(lambda r: "#2ECC71" if r >= 0.5 else "#E74C3C")

    h2h_fig = px.bar(
        h2h,
        x="win_rate",
        y="opponent_club",
        orientation="h",
        color="opponent_club",
        color_discrete_map={c: col for c, col in zip(h2h["opponent_club"], h2h["color"])},
        text="win_rate",
        labels={"win_rate": "Win Rate vs Club", "opponent_club": "Opponent Club"},
        hover_data={"matches": True, "wins": True},
    )
    h2h_fig.update_traces(texttemplate="%{text:.1%}", textposition="outside")
    h2h_fig.add_vline(x=0.5, line_dash="dash", line_color="gray")
    h2h_fig.update_layout(showlegend=False, xaxis_tickformat=".0%", height=max(400, len(h2h) * 22))
    st.plotly_chart(h2h_fig, use_container_width=True)

st.divider()

# =========================================================================
# Top Players
# =========================================================================
st.subheader("Top Players (min 5 matches)")

player_stats = (
    dtk.groupby(["player_id", "player_name"])
    .agg(matches=("match_id", "count"), wins=("won", "sum"), last_match=("date", "max"))
    .reset_index()
)
player_stats["win_rate"] = player_stats["wins"] / player_stats["matches"]
top_players = (
    player_stats[player_stats["matches"] >= 5]
    .nlargest(10, "win_rate")
    .reset_index(drop=True)
)

for _, row in top_players.iterrows():
    with st.expander(
        f"{row['player_name']} — {row['win_rate']:.1%} win rate ({int(row['matches'])} matches)"
    ):
        player_matches = dtk[dtk["player_id"] == row["player_id"]].sort_values("date", ascending=False)
        display = player_matches[["date", "opponent_name", "won", "tournament_name", "event_category", "round"]].copy()
        display["date"] = display["date"].dt.date
        display["won"] = display["won"].map({True: "✅ Win", False: "❌ Loss"})
        display.columns = ["Date", "Opponent", "Result", "Tournament", "Event", "Round"]
        st.dataframe(display, use_container_width=True, hide_index=True)

st.divider()

# =========================================================================
# Tournament Activity Heatmap (month × year)
# =========================================================================
st.subheader("Tournament Activity Heatmap")

heat_df = dtk[dtk["date"].notna()].copy()
heat_df["year"] = heat_df["date"].dt.year
heat_df["month"] = heat_df["date"].dt.month

pivot = (
    heat_df.groupby(["year", "month"])["tournament_id"]
    .nunique()
    .reset_index()
    .pivot(index="month", columns="year", values="tournament_id")
    .fillna(0)
    .astype(int)
)

month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
pivot.index = [month_labels[m - 1] for m in pivot.index]

heatmap_fig = px.imshow(
    pivot,
    labels=dict(x="Year", y="Month", color="Tournaments"),
    color_continuous_scale="YlOrRd",
    aspect="auto",
    text_auto=True,
)
heatmap_fig.update_layout(height=400)
st.plotly_chart(heatmap_fig, use_container_width=True)
