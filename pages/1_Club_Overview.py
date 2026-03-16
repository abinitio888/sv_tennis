"""Page 1 — Club Overview"""
import pandas as pd
import streamlit as st

from utils.data_loader import apply_filters, load_clubs, load_matches, DEFAULT_CLUB

st.set_page_config(page_title="Club Overview", layout="wide")
st.title("Club Overview")

# --- load & filter ---
df = load_matches()
clubs_df = load_clubs()

date_range = st.session_state.get("date_range")
event_cats = st.session_state.get("event_categories")
incl_unaff = st.session_state.get("include_unaffiliated", True)

df = apply_filters(df, date_range=date_range, event_categories=event_cats, include_unaffiliated=incl_unaff)

# --- club selector ---
all_clubs = sorted(df["player_club"].dropna().unique().tolist())
default_idx = all_clubs.index(DEFAULT_CLUB) if DEFAULT_CLUB in all_clubs else 0
club = st.selectbox("Select club", all_clubs, index=default_idx)

club_df = df[df["player_club"] == club]

if club_df.empty:
    st.warning("No data for this club with current filters.")
    st.stop()

# --- metric cards ---
total_players = club_df["player_id"].nunique()
cutoff = pd.Timestamp.now() - pd.DateOffset(months=12)
active_players = club_df[club_df["date"] >= cutoff]["player_id"].nunique()
total_matches = len(club_df)
total_wins = int(club_df["won"].sum())
win_rate = total_wins / total_matches if total_matches else 0
total_tournaments = club_df["tournament_id"].nunique()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Players", total_players)
c2.metric("Active (12m)", active_players)
c3.metric("Win Rate", f"{win_rate:.1%}")
c4.metric("Total Matches", total_matches)
c5.metric("Wins", total_wins)
c6.metric("Tournaments", total_tournaments)

st.divider()

# --- per-player stats table ---
st.subheader("Per-Player Stats")

player_stats = (
    club_df.groupby(["player_id", "player_name"])
    .agg(
        matches=("match_id", "count"),
        wins=("won", "sum"),
        last_match=("date", "max"),
    )
    .reset_index()
)
player_stats["win_rate"] = player_stats["wins"] / player_stats["matches"]
player_stats["last_match"] = player_stats["last_match"].dt.date
player_stats = player_stats.sort_values("matches", ascending=False)
player_stats = player_stats[["player_name", "matches", "wins", "win_rate", "last_match"]]
player_stats.columns = ["Player", "Matches", "Wins", "Win Rate", "Last Match"]
player_stats["Win Rate"] = player_stats["Win Rate"].map("{:.1%}".format)

st.dataframe(player_stats, use_container_width=True, hide_index=True)
