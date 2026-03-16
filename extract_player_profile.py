"""
Extracts full player profile data from svtf.tournamentsoftware.com.
Output: player_profile_lucas_jin.json with name, club, license, all tournament match history,
opponent names, scores, win/loss, and opponent player-profile URLs.
"""
import requests
import re
import json
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

PLAYER_ID = "1c94d946-461c-4cac-8553-a95dda62d4ce"
BASE_URL = "https://svtf.tournamentsoftware.com"

# --- Requests session (for player lookup) ---
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
    time.sleep(0.1)
    return result


def parse_match_div(match_div):
    """Parse a single .match div into a structured dict."""
    m = {}

    # Round name from header
    header = match_div.find("ul", class_="match__header-title")
    if header:
        m["round"] = header.get_text(" ", strip=True)

    # Duration
    dur = match_div.find(class_=re.compile(r"\bduration\b"))
    if dur:
        m["duration"] = dur.get_text(strip=True)

    # Players
    players = []
    for row in match_div.find_all("div", class_="match__row"):
        classes = row.get("class", [])
        won = "has-won" in classes
        # Player name & tournament link
        title = row.find("div", class_="match__row-title")
        name = ""
        t_href = None
        if title:
            a = title.find("a")
            if a:
                name = a.get_text(strip=True)
                t_href = a.get("href")
            else:
                name = title.get_text(strip=True)
        # Win/Loss tag
        status = ""
        stag = row.find("span", class_="match__status")
        if stag:
            status = stag.get_text(strip=True)
        players.append({"name": name, "won": won, "result": status, "tournament_player_href": t_href})
    m["players"] = players

    # Scores — each `ul.points` is one set; two `li` inside: [p1_score, p2_score]
    result_div = match_div.find("div", class_="match__result")
    if result_div:
        set_scores = []
        for ul in result_div.find_all("ul", class_="points"):
            cells = [li.get_text(strip=True) for li in ul.find_all("li", class_="points__cell")]
            if len(cells) == 2:
                set_scores.append({"p1": cells[0], "p2": cells[1]})
        m["scores"] = set_scores

    # Footer: date + venue
    footer = match_div.find("div", class_="match__footer")
    if footer:
        footer_text = footer.get_text(" ", strip=True)
        m["footer"] = footer_text
        # Extract date like "lör 2026-02-07" or "tor 2026-01-29"
        date_m = re.search(r"\d{4}-\d{2}-\d{2}", footer_text)
        m["date"] = date_m.group(0) if date_m else ""
        # Venue: text after the date
        if date_m:
            m["venue"] = footer_text[date_m.end():].strip()

    return m


def parse_year_html(html):
    """
    Parse the full tournament-year page HTML.
    Returns a list of tournament dicts, each with events containing matches.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find the main content area (skip nav/footer)
    main = soup.find("main") or soup.find("div", class_=re.compile(r"content|main"))
    if not main:
        main = soup

    # Walk through all top-level elements sequentially to track context
    # The structure is flat: h4(tournament) -> h4(class) -> h5(draw) -> ol.match-group
    tournaments = []
    cur_tournament = None
    cur_event = None  # "Klass: ..."
    cur_draw = None   # h5 draw name

    for tag in main.descendants:
        if not hasattr(tag, 'name') or tag.name is None:
            continue

        # Tournament heading: h4 with a tournament link
        if tag.name == "h4":
            a = tag.find("a", href=re.compile(r"/sport/tournament"))
            if a:
                tid_m = re.search(r"id=([A-F0-9-]{36})", a["href"], re.I)
                tid = tid_m.group(1).upper() if tid_m else ""

                # Get metadata from surrounding context
                parent = tag.parent
                club = ""
                dates = ""
                grade = ""
                venue_club = ""
                # Sibling small/span elements for club, dates
                if parent:
                    for sib in parent.children:
                        if not hasattr(sib, 'name'):
                            continue
                        txt = sib.get_text(strip=True)
                        if re.search(r"\d{4}-\d{2}-\d{2}", txt):
                            dates = txt
                        elif sib.name == "small" and txt and txt != tag.get_text(strip=True):
                            if not club:
                                club = txt

                cur_tournament = {
                    "tournament_id": tid,
                    "tournament_name": a.get_text(strip=True),
                    "tournament_url": f"{BASE_URL}{a['href']}",
                    "club": club,
                    "dates": dates,
                    "events": [],
                }
                cur_event = None
                cur_draw = None
                tournaments.append(cur_tournament)
                continue

            # h4 without tournament link — could be "Klass: ..." event name
            txt = tag.get_text(strip=True)
            if txt.startswith("Klass:") and cur_tournament is not None:
                cur_event = txt.replace("Klass:", "").strip()
                cur_draw = None
                continue

        # Draw heading: h5
        if tag.name == "h5" and cur_tournament is not None:
            cur_draw = tag.get_text(strip=True)
            continue

        # Match group: ol.match-group
        if tag.name == "ol" and "match-group" in " ".join(tag.get("class", [])):
            if cur_tournament is None:
                continue
            matches = [parse_match_div(m) for m in tag.find_all("div", class_="match")]
            if matches:
                # Find or create event entry
                ev_name = cur_event or "Unknown"
                draw_name = cur_draw or ev_name
                # Find existing event with same name
                ev = next((e for e in cur_tournament["events"] if e["event_name"] == ev_name), None)
                if not ev:
                    ev = {"event_name": ev_name, "draws": []}
                    cur_tournament["events"].append(ev)
                ev["draws"].append({"draw_name": draw_name, "matches": matches})

    return tournaments


def main():
    # --- Playwright: fetch rendered HTML pages ---
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        print("Accepting cookies...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle", timeout=10000)
        try:
            page.click("button.js-accept-basic", timeout=3000)
            page.wait_for_load_state("networkidle", timeout=5000)
        except:
            pass

        # --- Profile info ---
        print("Fetching profile page...")
        page.goto(f"{BASE_URL}/player-profile/{PLAYER_ID}")
        page.wait_for_load_state("networkidle", timeout=15000)
        profile_html = page.content()
        psoup = BeautifulSoup(profile_html, "html.parser")

        name_el = psoup.find("h2", class_="media__title")
        player_name = ""
        license_num = ""
        if name_el:
            player_name = name_el.find("span", class_="nav-link__value")
            player_name = player_name.get_text(strip=True) if player_name else ""
            aside = name_el.find("span", class_="media__title-aside")
            if aside:
                license_num = re.sub(r"[^\d]", "", aside.get_text(strip=True))

        club_a = psoup.find("a", href=re.compile(r"/association/group/"))
        club_name = club_a.get_text(strip=True) if club_a else ""

        profile_info = {
            "player_id": PLAYER_ID,
            "player_profile_url": f"{BASE_URL}/player-profile/{PLAYER_ID}",
            "name": player_name,
            "license": license_num,
            "club": club_name,
        }
        print(f"  Name: {player_name}, License: {license_num}, Club: {club_name}")

        # --- Get year links ---
        year_as = psoup.find_all("a", href=re.compile(r"/tournaments/\d{4}$"))
        # Also check current page for tabs
        page.goto(f"{BASE_URL}/player-profile/{PLAYER_ID}/tournaments")
        page.wait_for_load_state("networkidle", timeout=15000)
        thtml = page.content()
        tsoup = BeautifulSoup(thtml, "html.parser")
        year_as = tsoup.find_all("a", href=re.compile(r"/tournaments/\d{4}$"))
        years = sorted(set(re.search(r"/(\d{4})$", a["href"]).group(1) for a in year_as if re.search(r"/(\d{4})$", a["href"])))
        print(f"  Available years: {years}")

        # --- Fetch each year ---
        all_tournaments = []
        year_htmls = {}
        for year in years:
            print(f"Fetching {year} tournament history...")
            page.goto(f"{BASE_URL}/player-profile/{PLAYER_ID}/tournaments/{year}")
            page.wait_for_load_state("networkidle", timeout=15000)
            year_htmls[year] = page.content()

        browser.close()

    # --- Parse HTML ---
    print("Parsing tournament data...")
    for year, html in year_htmls.items():
        tournaments = parse_year_html(html)
        print(f"  {year}: {len(tournaments)} tournaments")
        all_tournaments.extend(tournaments)

    # --- Enrich with opponent profiles ---
    print("\nLooking up opponent player-profile URLs...")
    session.get(f"{BASE_URL}/", timeout=15)
    session.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/", "SettingsOpen": "false",
        "CookiePurposes": ["1", "2", "4", "8", "16"],
    })

    all_opponent_names = set()
    for t in all_tournaments:
        for ev in t["events"]:
            for draw in ev["draws"]:
                for m in draw["matches"]:
                    for pl in m["players"]:
                        n = pl["name"]
                        if n and n != player_name and n.lower() not in ("friplats", "bye"):
                            all_opponent_names.add(n)

    print(f"  {len(all_opponent_names)} unique opponents")
    opponent_profiles = {}
    for i, name in enumerate(sorted(all_opponent_names), 1):
        url = get_player_profile_url(name)
        if url:
            opponent_profiles[name] = url
        if i % 20 == 0:
            print(f"  [{i}/{len(all_opponent_names)}] found {len(opponent_profiles)}")

    # Inject profile URLs into matches
    for t in all_tournaments:
        for ev in t["events"]:
            for draw in ev["draws"]:
                for m in draw["matches"]:
                    for pl in m["players"]:
                        n = pl["name"]
                        if n == player_name:
                            pl["player_profile_url"] = f"{BASE_URL}/player-profile/{PLAYER_ID}"
                        else:
                            pl["player_profile_url"] = opponent_profiles.get(n, "")

    # --- Save ---
    output = {
        "profile": profile_info,
        "tournaments": all_tournaments,
    }
    with open("player_profile_lucas_jin.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # --- Print summary ---
    print(f"\nSaved to player_profile_lucas_jin.json")
    print(f"\n{'='*60}")
    print(f"PLAYER: {player_name} | License: {license_num} | Club: {club_name}")
    print(f"{'='*60}")
    for t in all_tournaments:
        print(f"\n[{t['tournament_name']}] {t.get('dates','')} {t.get('club','')}")
        print(f"  URL: {t['tournament_url']}")
        for ev in t["events"]:
            print(f"  Class: {ev['event_name']}")
            for draw in ev["draws"]:
                print(f"    Draw: {draw['draw_name']}")
                for m in draw["matches"]:
                    ps = m.get("players", [])
                    p1 = ps[0]["name"] if ps else ""
                    p2 = ps[1]["name"] if len(ps) > 1 else ""
                    res = ps[1].get("result", "") if len(ps) > 1 else ""
                    # Determine who won
                    winner = next((p["name"] for p in ps if p.get("won")), "")
                    sets = " ".join(f"{s['p1']}-{s['p2']}" for s in m.get("scores", []))
                    date = m.get("date", "")
                    venue = m.get("venue", "")[:40]
                    print(f"      {m.get('round','')}: {p1} vs {p2} | winner={winner} | {sets} | {date} {venue}")
                    for pl in ps:
                        prof = pl.get("player_profile_url", "")
                        if prof:
                            print(f"        -> {pl['name']}: {prof}")


if __name__ == "__main__":
    main()
