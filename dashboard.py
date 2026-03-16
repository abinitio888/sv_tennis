"""
Tennis Club Performance Dashboard — entry point.
Run with: streamlit run dashboard.py
"""
import subprocess
import sys
from pathlib import Path

import streamlit as st

DATA_DIR = Path(__file__).parent / "data"
PARQUET_FILES = [
    DATA_DIR / "matches.parquet",
    DATA_DIR / "clubs.parquet",
    DATA_DIR / "player_club_map.parquet",
]

# ---------------------------------------------------------------------------
# Auto-build data if missing
# ---------------------------------------------------------------------------
if not all(p.exists() for p in PARQUET_FILES):
    st.info("Building dataset for the first time — this may take a minute...")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "build_dataset.py")],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        st.error(f"build_dataset.py failed:\n{result.stderr}")
        st.stop()
    st.success("Dataset built successfully. Reloading...")
    st.rerun()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Tennis Club Dashboard",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar — global filters (stored in session_state for pages to read)
# ---------------------------------------------------------------------------
from utils.data_loader import load_matches, ALL_CATEGORIES  # noqa: E402

df_all = load_matches()

st.sidebar.title("🎾 Global Filters")

# Date range
min_date = df_all["date"].min().date()
max_date = df_all["date"].max().date()
date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    st.session_state["date_range"] = date_range
else:
    st.session_state["date_range"] = (min_date, max_date)

# Event categories
selected_cats = st.sidebar.multiselect(
    "Event categories",
    options=ALL_CATEGORIES,
    default=ALL_CATEGORIES,
)
st.session_state["event_categories"] = selected_cats if selected_cats else ALL_CATEGORIES

# Unaffiliated
include_unaffiliated = st.sidebar.checkbox("Include unaffiliated players", value=True)
st.session_state["include_unaffiliated"] = include_unaffiliated

# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------
st.title("🎾 Tennis Club Performance Dashboard")
st.markdown(
    """
    Welcome! Use the sidebar to set global filters, then navigate to a page:

    | Page | Description |
    |------|-------------|
    | **Club Overview** | KPIs and per-player stats for any club |
    | **Club Comparison** | Rank all clubs by KPI; scatter of active players vs win rate |
    | **Performance Over Time** | Multi-line trend: win rate / match count over time |
    | **Event Breakdown** | Win rate and volume by event category |
    | **Danderyds Focus** | H2H, top players, tournament heatmap for Danderyds TK |
    """
)

st.info("Select a page from the left sidebar to get started.")
