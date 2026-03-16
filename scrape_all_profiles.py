"""
Bulk extract player profiles for all URLs in player_profile_tournament.txt.
For each player: name, club, license, and all historical tournament match details
with opponent player-profile URLs.

Output: one JSON file per player in ./profiles/ directory.
Uses threaded requests (no Playwright) for speed.
"""
import requests
import re
import json
import time
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from pathlib import Path

INPUT_FILE = "player_profile_tournament_expanded.txt"
OUTPUT_DIR = Path("profiles")
OUTPUT_DIR.mkdir(exist_ok=True)

BASE_URL = "https://svtf.tournamentsoftware.com"
MAX_WORKERS = 20         # parallel player fetches
OPPONENT_WORKERS = 16    # parallel opponent profile lookups

# --- Shared session factory (one per thread) ---
_thread_local = threading.local()

def get_session():
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
        s.get(f"{BASE_URL}/", timeout=15)
        s.post(f"{BASE_URL}/cookiewall/Save", data={
            "ReturnUrl": "/", "SettingsOpen": "false",
            "CookiePurposes": ["1", "2", "4", "8", "16"],
        })
        _thread_local.session = s
    return _thread_local.session

# --- Global opponent profile cache ---
_opponent_cache = {}
_opponent_lock = threading.Lock()

def get_player_profile_url(name):
    if not name or name.lower() in ("friplats", "bye", "walkover", ""):
        return ""
    with _opponent_lock:
        if name in _opponent_cache:
            return _opponent_cache[name]
    try:
        s = get_session()
        r = s.get(f"{BASE_URL}/find/player/DoSearch",
                  params={"Page": "1", "SportID": "1", "Query": name},
                  headers={"X-Requested-With": "XMLHttpRequest"},
                  timeout=10)
        links = list(dict.fromkeys(
            a["href"] for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True)
            if "player-profile" in a["href"]
        ))
        result = f"{BASE_URL}{links[0]}" if links else ""
    except Exception:
        result = ""
    with _opponent_lock:
        _opponent_cache[name] = result
    return result


# --- HTML parsers ---

def parse_match_div(match_div):
    m = {}
    header = match_div.find("ul", class_="match__header-title")
    if header:
        m["round"] = header.get_text(" ", strip=True)

    players = []
    for row in match_div.find_all("div", class_="match__row"):
        won = "has-won" in row.get("class", [])
        title = row.find("div", class_="match__row-title")
        name, t_href = "", None
        if title:
            a = title.find("a")
            name = a.get_text(strip=True) if a else title.get_text(strip=True)
            t_href = a.get("href") if a else None
        stag = row.find("span", class_="match__status")
        status = stag.get_text(strip=True) if stag else ""
        players.append({"name": name, "won": won, "result": status,
                         "tournament_player_href": t_href, "player_profile_url": ""})
    m["players"] = players

    result_div = match_div.find("div", class_="match__result")
    if result_div:
        sets = []
        for ul in result_div.find_all("ul", class_="points"):
            cells = [li.get_text(strip=True) for li in ul.find_all("li", class_="points__cell")]
            if len(cells) == 2:
                sets.append({"p1": cells[0], "p2": cells[1]})
        m["scores"] = sets

    footer = match_div.find("div", class_="match__footer")
    if footer:
        ft = footer.get_text(" ", strip=True)
        m["footer"] = ft
        dm = re.search(r"\d{4}-\d{2}-\d{2}", ft)
        m["date"] = dm.group(0) if dm else ""
        m["venue"] = ft[dm.end():].strip() if dm else ""
    return m


def parse_year_html(html):
    soup = BeautifulSoup(html, "html.parser")
    tournaments = []
    cur_t = cur_event = cur_draw = None

    for tag in soup.descendants:
        if not hasattr(tag, "name") or not tag.name:
            continue

        if tag.name == "h4":
            a = tag.find("a", href=re.compile(r"/sport/tournament"))
            if a:
                tid_m = re.search(r"id=([A-F0-9-]{36})", a["href"], re.I)
                cur_t = {
                    "tournament_id": tid_m.group(1).upper() if tid_m else "",
                    "tournament_name": a.get_text(strip=True),
                    "tournament_url": f"{BASE_URL}{a['href']}",
                    "events": [],
                }
                cur_event = cur_draw = None
                tournaments.append(cur_t)
            elif cur_t is not None:
                txt = tag.get_text(strip=True)
                if txt.startswith("Klass:"):
                    cur_event = txt.replace("Klass:", "").strip()
                    cur_draw = None

        elif tag.name == "h5" and cur_t is not None:
            cur_draw = tag.get_text(strip=True)

        elif tag.name == "ol" and "match-group" in " ".join(tag.get("class", [])) and cur_t is not None:
            matches = [parse_match_div(m) for m in tag.find_all("div", class_="match")]
            if not matches:
                continue
            ev_name = cur_event or "Unknown"
            ev = next((e for e in cur_t["events"] if e["event_name"] == ev_name), None)
            if not ev:
                ev = {"event_name": ev_name, "draws": []}
                cur_t["events"].append(ev)
            ev["draws"].append({"draw_name": cur_draw or ev_name, "matches": matches})

    return tournaments


def fetch_player(player_url):
    """Fetch all data for one player. Returns dict or None on error."""
    player_id = player_url.rstrip("/").split("/")[-1].lower()
    out_file = OUTPUT_DIR / f"{player_id}.json"

    try:
        s = get_session()

        # Profile page
        r = s.get(player_url, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # Redirect to cookiewall = not found
        if "cookiewall" in r.url:
            return None

        name_el = soup.find("h2", class_="media__title")
        player_name = ""
        license_num = ""
        if name_el:
            nv = name_el.find("span", class_="nav-link__value")
            player_name = nv.get_text(strip=True) if nv else ""
            aside = name_el.find("span", class_="media__title-aside")
            if aside:
                license_num = re.sub(r"[^\d]", "", aside.get_text(strip=True))

        club_a = soup.find("a", href=re.compile(r"/association/group/"))
        club_name = club_a.get_text(strip=True) if club_a else ""

        if not player_name:
            return None  # skip if no name found

        # Available years — must fetch /tournaments subpage (year tabs not on main profile page)
        tr = s.get(f"{BASE_URL}/player-profile/{player_id}/tournaments", timeout=15)
        year_as = BeautifulSoup(tr.text, "html.parser").find_all("a", href=re.compile(r"/tournaments/\d{4}$"))
        years = sorted(set(
            re.search(r"/(\d{4})$", a["href"]).group(1)
            for a in year_as if re.search(r"/(\d{4})$", a["href"])
        ))

        # Fetch each year
        all_tournaments = []
        for year in years:
            yr = s.get(f"{BASE_URL}/player-profile/{player_id}/tournaments/{year}", timeout=15)
            if yr.status_code == 200:
                all_tournaments.extend(parse_year_html(yr.text))
            time.sleep(0.05)

        # Collect opponents
        opponent_names = set()
        for t in all_tournaments:
            for ev in t["events"]:
                for draw in ev["draws"]:
                    for m in draw["matches"]:
                        for pl in m["players"]:
                            n = pl["name"]
                            if n and n != player_name and n.lower() not in ("friplats", "bye"):
                                opponent_names.add(n)

        # Lookup opponent profiles
        for name in opponent_names:
            get_player_profile_url(name)

        # Inject profile URLs
        for t in all_tournaments:
            for ev in t["events"]:
                for draw in ev["draws"]:
                    for m in draw["matches"]:
                        for pl in m["players"]:
                            n = pl["name"]
                            if n == player_name:
                                pl["player_profile_url"] = player_url
                            else:
                                pl["player_profile_url"] = _opponent_cache.get(n, "")

        result = {
            "profile": {
                "player_id": player_id,
                "player_profile_url": player_url,
                "name": player_name,
                "license": license_num,
                "club": club_name,
            },
            "tournaments": all_tournaments,
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

        return player_name

    except Exception as e:
        return None


def main():
    with open(INPUT_FILE) as f:
        urls = [line.strip() for line in f if line.strip()]

    # Skip already processed
    already_done = sum(1 for u in urls if (OUTPUT_DIR / f"{u.rstrip('/').split('/')[-1].lower()}.json").exists())
    print(f"Total players: {len(urls)}, already done: {already_done}, remaining: {len(urls) - already_done}")

    done = 0
    errors = 0
    lock = threading.Lock()
    start = time.time()

    def process(url):
        nonlocal done, errors
        result = fetch_player(url)
        with lock:
            if result is not None:
                done += 1
                if done % 100 == 0:
                    elapsed = time.time() - start
                    rate = done / elapsed if elapsed > 0 else 0
                    remaining = (len(urls) - already_done - done) / rate if rate > 0 else 0
                    print(f"  [{done}/{len(urls) - already_done}] done | cache={len(_opponent_cache)} opponents | "
                          f"{rate:.1f}/s | ~{remaining/60:.0f}m left")
            else:
                errors += 1

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(process, url) for url in urls]
        for _ in as_completed(futures):
            pass

    elapsed = time.time() - start
    print(f"\nDone in {elapsed/60:.1f}m")
    print(f"  Processed: {done - already_done} new players")
    print(f"  Errors/skipped: {errors}")
    print(f"  Opponent profiles cached: {len(_opponent_cache)}")
    print(f"  Output: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
