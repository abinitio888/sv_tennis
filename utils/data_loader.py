"""
Cached data loaders for the Streamlit dashboard.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent.parent / "data"

DEFAULT_CLUB = "Danderyds TK"


@st.cache_data
def load_matches() -> pd.DataFrame:
    df = pd.read_parquet(DATA_DIR / "matches.parquet")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


@st.cache_data
def load_clubs() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "clubs.parquet")


@st.cache_data
def load_player_club_map() -> dict:
    df = pd.read_parquet(DATA_DIR / "player_club_map.parquet")
    return dict(zip(df["player_profile_url"].str.upper(), df["club"]))


def apply_filters(
    df: pd.DataFrame,
    date_range=None,
    event_categories=None,
    include_unaffiliated: bool = True,
) -> pd.DataFrame:
    if date_range:
        start, end = date_range
        if start:
            df = df[df["date"] >= pd.Timestamp(start)]
        if end:
            df = df[df["date"] <= pd.Timestamp(end)]
    if event_categories:
        df = df[df["event_category"].isin(event_categories)]
    if not include_unaffiliated:
        df = df[df["player_club"] != "Unaffiliated"]
    return df


ALL_CATEGORIES = [
    "mens_singles",
    "womens_singles",
    "mens_doubles",
    "womens_doubles",
    "mixed_doubles",
    "juniors",
    "senior_plus",
    "other",
]
