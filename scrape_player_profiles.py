"""
Scrapes all hyperlinks containing 'player-profile' from svtf.tournamentsoftware.com.

Structure:
  /ranking -> list of ranking IDs (rid=XXX)
  /ranking/ranking.aspx?rid=XXX -> redirects to /ranking/ranking.aspx?id=YYY, shows categories
  /ranking/category.aspx?id=YYY&category=ZZZ -> paginated list of players in a category
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlencode, parse_qs
import re
import time

BASE_URL = "https://svtf.tournamentsoftware.com"
OUTPUT_FILE = "player_profile_links.txt"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
})

def accept_cookies():
    session.get(f"{BASE_URL}/ranking", timeout=15)
    session.post(f"{BASE_URL}/cookiewall/Save", data={
        "ReturnUrl": "/ranking",
        "SettingsOpen": "false",
        "CookiePurposes": ["1", "2", "4", "8", "16"],
    }, allow_redirects=True)
    print("Cookies accepted.")

def get_soup(url):
    r = session.get(url, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def get_ranking_pages():
    """Return list of ranking page URLs (ranking.aspx?rid=...)."""
    soup = get_soup(f"{BASE_URL}/ranking")
    rids = re.findall(r'ranking\.aspx\?rid=(\d+)', soup.decode() if hasattr(soup, 'decode') else str(soup))
    urls = [f"{BASE_URL}/ranking/ranking.aspx?rid={rid}" for rid in set(rids)]
    print(f"Found {len(urls)} rankings.")
    return urls

def get_category_urls(ranking_url):
    """From a ranking overview page, return all category page URLs."""
    soup = get_soup(ranking_url)
    category_urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "category.aspx" in href:
            full = urljoin(f"{BASE_URL}/ranking/", href)
            if full not in category_urls:
                category_urls.append(full)
    return category_urls

def get_player_links_from_category(category_url):
    """Paginate through a category page and collect all player-profile links."""
    player_links = set()
    url = category_url
    page = 1

    while url:
        soup = get_soup(url)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "player-profile" in href:
                full = urljoin(BASE_URL, href)
                player_links.add(full)

        # Find next page link
        next_url = None
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if text in ("Nästa", "Next", ">>"):
                next_url = urljoin(f"{BASE_URL}/ranking/", a["href"])
                break

        if next_url and next_url != url:
            url = next_url
            page += 1
            time.sleep(0.2)
        else:
            break

    return player_links

def main():
    accept_cookies()

    all_player_links = set()

    ranking_urls = get_ranking_pages()

    for i, ranking_url in enumerate(ranking_urls, 1):
        print(f"\n[{i}/{len(ranking_urls)}] {ranking_url}")
        try:
            category_urls = get_category_urls(ranking_url)
            print(f"  {len(category_urls)} categories")

            for cat_url in category_urls:
                try:
                    links = get_player_links_from_category(cat_url)
                    all_player_links.update(links)
                    print(f"  {cat_url.split('?')[1][:40]} -> {len(links)} links (total: {len(all_player_links)})")
                    time.sleep(0.1)
                except Exception as e:
                    print(f"  Error on category {cat_url}: {e}")
        except Exception as e:
            print(f"  Error on ranking {ranking_url}: {e}")

    print(f"\nTotal unique player-profile links: {len(all_player_links)}")
    with open(OUTPUT_FILE, "w") as f:
        for link in sorted(all_player_links):
            f.write(link + "\n")
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
