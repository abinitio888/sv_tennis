"""
Scrapes all player-profile URLs for players in tournaments matching the search criteria:
  DateFilterType=0, StartDate=2025-04-02, EndDate=2026-02-28, PostalCode=17067, Distance=15

Steps:
  1. Get all tournament IDs via POST to find/tournament/DoSearch
  2. For each tournament, call GetPlayersContent to get player names
  3. For each unique player name, search find/player/DoSearch to get player-profile URL
  4. Save unique player-profile URLs to player_profile_tournament.txt
"""
import requests
import re
import time
from bs4 import BeautifulSoup

BASE_URL = "https://svtf.tournamentsoftware.com"
OUTPUT_FILE = "player_profile_tournament.txt"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
})


def accept_cookies():
    session.get(f"{BASE_URL}/", timeout=15)
    session.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/", "SettingsOpen": "false",
        "CookiePurposes": ["1", "2", "4", "8", "16"],
    }, allow_redirects=True)
    print("Cookies accepted.")


def get_all_tournament_ids():
    """Return all tournament IDs from the search results."""
    session.headers["X-Requested-With"] = "XMLHttpRequest"
    session.headers["Referer"] = f"{BASE_URL}/find"

    all_ids = set()
    for page_num in range(1, 20):
        r = session.post(f"{BASE_URL}/find/tournament/DoSearch", data={
            "Page": str(page_num),
            "TournamentExtendedFilter.SportID": "0",
            "TournamentFilter.Q": "",
            "TournamentFilter.DateFilterType": "0",
            "TournamentFilter.StartDate": "2025-04-02",
            "TournamentFilter.EndDate": "2026-02-28",
            "TournamentFilter.PostalCode": "17067",
            "TournamentFilter.Distance": "15",
            "TournamentExtendedFilter.StatusFilterID": "false",
            "TournamentExtendedFilter.EventGameTypeIDList[0]": "false",
            "TournamentExtendedFilter.EventGameTypeIDList[1]": "false",
            "TournamentExtendedFilter.EventGameTypeIDList[2]": "false",
            "TournamentExtendedFilter.EventGameTypeIDList[3]": "false",
            "TournamentExtendedFilter.EventGameTypeIDList[4]": "false",
            "X-Requested-With": "XMLHttpRequest",
        }, timeout=15)
        ids = set(i.upper() for i in re.findall(
            r'/sport/tournament\?id=([A-F0-9-]{36})', r.text, re.I))
        if not ids:
            break
        new = ids - all_ids
        all_ids.update(ids)
        print(f"  Page {page_num}: +{len(new)} tournaments (total: {len(all_ids)})")
        time.sleep(0.1)

    del session.headers["X-Requested-With"]
    del session.headers["Referer"]
    return all_ids


def get_player_names(tournament_id):
    """Return all unique player names (Lastname, Firstname) from a tournament."""
    session.headers["X-Requested-With"] = "XMLHttpRequest"
    tid = tournament_id.lower()
    try:
        r = session.post(
            f"{BASE_URL}/tournament/{tid}/Players/GetPlayersContent",
            data={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        names = set(
            a.get_text(strip=True)
            for a in soup.find_all("a", href=True)
            if f"player.aspx?id={tid}" in a["href"].lower() and a.get_text(strip=True)
        )
        return names
    except Exception as e:
        print(f"    Error fetching players for {tournament_id}: {e}")
        return set()
    finally:
        del session.headers["X-Requested-With"]


def get_player_profile_url(player_name):
    """Search for a player and return their player-profile URL (or None)."""
    session.headers["X-Requested-With"] = "XMLHttpRequest"
    try:
        r = session.get(f"{BASE_URL}/find/player/DoSearch", params={
            "Page": "1", "SportID": "1", "Query": player_name,
        }, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        links = list(dict.fromkeys(
            a["href"] for a in soup.find_all("a", href=True)
            if "player-profile" in a["href"]
        ))
        return links[0] if links else None
    except Exception as e:
        print(f"    Error searching for '{player_name}': {e}")
        return None
    finally:
        del session.headers["X-Requested-With"]


def main():
    accept_cookies()

    print("\n--- Step 1: Collecting tournament IDs ---")
    tournament_ids = get_all_tournament_ids()
    print(f"Total: {len(tournament_ids)} tournaments\n")

    print("--- Step 2: Collecting player names from tournaments ---")
    all_player_names = set()
    for i, tid in enumerate(sorted(tournament_ids), 1):
        names = get_player_names(tid)
        new = names - all_player_names
        all_player_names.update(names)
        print(f"  [{i}/{len(tournament_ids)}] {tid[:8]}... : {len(names)} players, {len(new)} new (total unique: {len(all_player_names)})")
        time.sleep(0.1)

    print(f"\nTotal unique players: {len(all_player_names)}\n")

    print("--- Step 3: Looking up player-profile URLs ---")
    player_profiles = set()
    names_list = sorted(all_player_names)
    for i, name in enumerate(names_list, 1):
        url = get_player_profile_url(name)
        if url:
            full_url = f"{BASE_URL}{url}" if url.startswith("/") else url
            player_profiles.add(full_url)
        if i % 50 == 0 or i == len(names_list):
            print(f"  [{i}/{len(names_list)}] profiles found: {len(player_profiles)}")
        time.sleep(0.15)

    print(f"\nTotal unique player-profile URLs: {len(player_profiles)}")
    with open(OUTPUT_FILE, "w") as f:
        for url in sorted(player_profiles):
            f.write(url + "\n")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
