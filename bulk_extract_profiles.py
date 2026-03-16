"""
Bulk extract player profiles for all URLs in player_profile_tournament.txt.
Uses the same approach as extract_player_profile.py:
  - Playwright browser (reused, one instance) for profile pages and year pages
  - requests for opponent player-profile URL lookups
Saves one JSON per player to ./profiles/{player_id}.json (overwrites if exists).
"""
import requests
import re
import json
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from pathlib import Path

INPUT_FILE = "player_profile_tournament.txt"
OUTPUT_DIR = Path("profiles")
OUTPUT_DIR.mkdir(exist_ok=True)

BASE_URL = "https://svtf.tournamentsoftware.com"

# --- Requests session for opponent lookups ---
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
})
_profile_cache = {}


def get_player_profile_url(name):
    if name in _profile_cache:
        return _profile_cache[name]
    if not name or name.lower() in ("friplats", "bye", "walkover", ""):
        return None
    try:
        r = session.get(f"{BASE_URL}/find/player/DoSearch",
                        params={"Page": "1", "SportID": "1", "Query": name}, timeout=10)
        links = list(dict.fromkeys(
            a["href"] for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True)
            if "player-profile" in a["href"]
        ))
        result = f"{BASE_URL}{links[0]}" if links else None
    except Exception:
        result = None
    _profile_cache[name] = result
    time.sleep(0.05)
    return result


def parse_match_div(match_div):
    m = {}
    header = match_div.find("ul", class_="match__header-title")
    if header:
        m["round"] = header.get_text(" ", strip=True)

    dur = match_div.find(class_=re.compile(r"\bduration\b"))
    if dur:
        m["duration"] = dur.get_text(strip=True)

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


def process_player(page, player_url):
    player_id = player_url.rstrip("/").split("/")[-1].lower()
    out_file = OUTPUT_DIR / f"{player_id}.json"

    # Profile page
    page.goto(f"{BASE_URL}/player-profile/{player_id}")
    page.wait_for_load_state("networkidle", timeout=15000)
    profile_html = page.content()

    if "cookiewall" in page.url:
        return None, "cookiewall redirect"

    psoup = BeautifulSoup(profile_html, "html.parser")
    name_el = psoup.find("h2", class_="media__title")
    player_name = license_num = ""
    if name_el:
        nv = name_el.find("span", class_="nav-link__value")
        player_name = nv.get_text(strip=True) if nv else ""
        aside = name_el.find("span", class_="media__title-aside")
        if aside:
            license_num = re.sub(r"[^\d]", "", aside.get_text(strip=True))

    if not player_name:
        return None, "no name found"

    club_a = psoup.find("a", href=re.compile(r"/association/group/"))
    club_name = club_a.get_text(strip=True) if club_a else ""

    # Year links — fetch /tournaments subpage
    page.goto(f"{BASE_URL}/player-profile/{player_id}/tournaments")
    page.wait_for_load_state("networkidle", timeout=15000)
    thtml = page.content()
    tsoup = BeautifulSoup(thtml, "html.parser")
    year_as = tsoup.find_all("a", href=re.compile(r"/tournaments/\d{4}$"))
    years = sorted(set(
        re.search(r"/(\d{4})$", a["href"]).group(1)
        for a in year_as if re.search(r"/(\d{4})$", a["href"])
    ))

    # Fetch each year page
    all_tournaments = []
    for year in years:
        page.goto(f"{BASE_URL}/player-profile/{player_id}/tournaments/{year}")
        page.wait_for_load_state("networkidle", timeout=15000)
        all_tournaments.extend(parse_year_html(page.content()))

    # Collect opponent names
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
                            pl["player_profile_url"] = _profile_cache.get(n) or ""

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

    return player_name, None


def main():
    with open(INPUT_FILE) as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"Total players: {len(urls)}")

    done = errors = 0
    start = time.time()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        # Accept cookies once
        print("Accepting cookies...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle", timeout=10000)
        try:
            page.click("button.js-accept-basic", timeout=3000)
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        # Also bootstrap requests session
        session.get(f"{BASE_URL}/", timeout=15)
        session.post(f"{BASE_URL}/cookiewall/Save", data={
            "ReturnUrl": "/", "SettingsOpen": "false",
            "CookiePurposes": ["1", "2", "4", "8", "16"],
        })

        for i, url in enumerate(urls, 1):
            try:
                name, err = process_player(page, url)
                if name:
                    done += 1
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                err = str(e)

            if i % 10 == 0 or i == len(urls):
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (len(urls) - i) / rate if rate > 0 else 0
                print(f"  [{i}/{len(urls)}] done={done} errors={errors} | "
                      f"{rate:.1f}/s | ~{remaining/60:.0f}m left | cache={len(_profile_cache)}")

        browser.close()

    elapsed = time.time() - start
    print(f"\nFinished in {elapsed/60:.1f}m")
    print(f"  Saved: {done} profiles")
    print(f"  Errors/skipped: {errors}")
    print(f"  Opponent cache: {len(_profile_cache)}")


if __name__ == "__main__":
    main()
