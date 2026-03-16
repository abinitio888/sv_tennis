"""
Parses all sample/*.json player profiles → outputs parquet files to data/.

Usage:
    python build_dataset.py [--profiles-dir ./sample] [--output-dir ./data]
                            [--force] [--workers N]
"""
import argparse
import hashlib
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from utils.event_classifier import classify_event, is_doubles


# ---------------------------------------------------------------------------
# Per-file processing (runs in worker processes)
# ---------------------------------------------------------------------------

def _process_file(path: str):
    """Parse one JSON file → list of match-row dicts + player_club entry."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], None

    profile = data.get("profile", {})
    player_id = profile.get("player_id", "")
    player_name = profile.get("name", "")
    player_club = profile.get("club") or "Unaffiliated"
    player_profile_url = profile.get("player_profile_url", "")

    rows = []
    seen_match_ids = set()

    for tournament in data.get("tournaments", []):
        tournament_id = tournament.get("tournament_id", "")
        tournament_name = tournament.get("tournament_name", "")

        for event in tournament.get("events", []):
            event_name = event.get("event_name", "")
            event_cat = classify_event(event_name)
            doubles = is_doubles(event_cat)

            for draw in event.get("draws", []):
                draw_name = draw.get("draw_name", "")

                for match in draw.get("matches", []):
                    players = match.get("players", [])
                    if len(players) < 2:
                        continue

                    # Identify this player vs opponent
                    our_player = None
                    opponent = None
                    for p in players:
                        if p.get("player_profile_url", "").upper() == player_profile_url.upper():
                            our_player = p
                        else:
                            opponent = p

                    if our_player is None:
                        # Fall back to name match
                        for p in players:
                            if p.get("name", "") == player_name:
                                our_player = p
                            else:
                                opponent = p

                    if our_player is None or opponent is None:
                        continue

                    won = bool(our_player.get("won", False))
                    date_str = match.get("date", "")
                    round_name = match.get("round", "")
                    opponent_name = opponent.get("name", "")
                    opponent_url = opponent.get("player_profile_url", "")

                    # Build a stable match_id to deduplicate
                    sorted_names = sorted([player_name, opponent_name])
                    raw_id = f"{tournament_id}|{draw_name}|{round_name}|{'|'.join(sorted_names)}"
                    match_id = hashlib.sha1(raw_id.encode()).hexdigest()

                    if match_id in seen_match_ids:
                        continue
                    seen_match_ids.add(match_id)

                    rows.append({
                        "player_id": player_id,
                        "player_name": player_name,
                        "player_club": player_club,
                        "opponent_name": opponent_name,
                        "opponent_profile_url": opponent_url,
                        "won": won,
                        "date": date_str,
                        "tournament_id": tournament_id,
                        "tournament_name": tournament_name,
                        "event_name": event_name,
                        "event_category": event_cat,
                        "is_doubles": doubles,
                        "round": round_name,
                        "match_id": match_id,
                    })

    club_entry = (player_profile_url, player_club) if player_profile_url else None
    return rows, club_entry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _needs_rebuild(output_dir: Path, profiles_dir: Path) -> bool:
    parquet_files = [
        output_dir / "matches.parquet",
        output_dir / "clubs.parquet",
        output_dir / "player_club_map.parquet",
    ]
    if not all(p.exists() for p in parquet_files):
        return True
    oldest_parquet = min(p.stat().st_mtime for p in parquet_files)
    newest_json = max(
        p.stat().st_mtime for p in profiles_dir.glob("*.json")
    )
    return newest_json > oldest_parquet


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build(profiles_dir: Path, output_dir: Path, workers: int):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_files = sorted(profiles_dir.glob("*.json"))
    print(f"Processing {len(json_files)} player files with {workers} workers...")

    all_rows = []
    club_map = {}  # profile_url → club

    with Pool(workers) as pool:
        for rows, club_entry in tqdm(
            pool.imap_unordered(_process_file, [str(p) for p in json_files]),
            total=len(json_files),
            desc="Parsing profiles",
        ):
            all_rows.extend(rows)
            if club_entry:
                url, club = club_entry
                club_map[url] = club

    print(f"Total raw match-rows: {len(all_rows)}")

    # --- matches.parquet ---
    df = pd.DataFrame(all_rows)

    # Parse dates
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["year"] = df["date"].dt.year.astype("Int64")
    df["year_month"] = df["date"].dt.to_period("M").astype(str).where(df["date"].notna(), other=pd.NA)
    df["quarter"] = df["date"].dt.to_period("Q").astype(str).where(df["date"].notna(), other=pd.NA)

    # Deduplicate by match_id — keep first occurrence
    n_before = len(df)
    df = df.drop_duplicates(subset=["match_id"])
    print(f"After deduplication: {len(df)} rows (removed {n_before - len(df)})")

    matches_path = output_dir / "matches.parquet"
    df.to_parquet(matches_path, index=False)
    print(f"Wrote {matches_path}")

    # --- clubs.parquet ---
    cutoff_12m = pd.Timestamp.now() - pd.DateOffset(months=12)

    club_groups = df.groupby("player_club")

    total_players = df.groupby("player_club")["player_id"].nunique()
    active_players = (
        df[df["date"] >= cutoff_12m]
        .groupby("player_club")["player_id"]
        .nunique()
    )
    total_matches = club_groups["match_id"].count()
    total_wins = club_groups["won"].sum()
    win_rate = total_wins / total_matches
    total_tournaments = club_groups["tournament_id"].nunique()
    earliest = club_groups["date"].min()
    latest = club_groups["date"].max()

    clubs_df = pd.DataFrame({
        "club": total_players.index,
        "total_players": total_players.values,
        "active_players_12m": active_players.reindex(total_players.index).fillna(0).astype(int).values,
        "total_matches": total_matches.reindex(total_players.index).values,
        "total_wins": total_wins.reindex(total_players.index).values,
        "win_rate": win_rate.reindex(total_players.index).values,
        "total_tournaments": total_tournaments.reindex(total_players.index).values,
        "earliest_date": earliest.reindex(total_players.index).values,
        "latest_date": latest.reindex(total_players.index).values,
    })

    clubs_path = output_dir / "clubs.parquet"
    clubs_df.to_parquet(clubs_path, index=False)
    print(f"Wrote {clubs_path} ({len(clubs_df)} clubs)")

    # --- player_club_map.parquet ---
    club_map_df = pd.DataFrame(
        list(club_map.items()), columns=["player_profile_url", "club"]
    )
    map_path = output_dir / "player_club_map.parquet"
    club_map_df.to_parquet(map_path, index=False)
    print(f"Wrote {map_path} ({len(club_map_df)} entries)")

    print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Build tennis dashboard datasets")
    parser.add_argument("--profiles-dir", default="./sample", type=Path)
    parser.add_argument("--output-dir", default="./data", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    args = parser.parse_args()

    if not args.force and not _needs_rebuild(args.output_dir, args.profiles_dir):
        print("Data files are up to date. Use --force to rebuild.")
        return

    build(args.profiles_dir, args.output_dir, args.workers)


if __name__ == "__main__":
    main()
