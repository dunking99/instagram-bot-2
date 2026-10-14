#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import sys
import re
from urllib.parse import urljoin, urlparse, parse_qs
from collections import defaultdict
from typing import Optional, List, Tuple
from pathlib import Path

# ────────────────────────────────────────────────
# KEYWORD CONFIG
# ────────────────────────────────────────────────
NEGATIVE_KEYWORDS = [
    "tease", "teasing", "joi", "instruction", "countdown", "preview",
    "trailer", "promo", "behind", "bts", "interview"
]

LESBIAN_KEYWORDS = [
    "lesbian", "lesbo", "girl-girl", "girls", "gg", "sapphic",
    "trib", "scissor", "scissoring", "pussy-eating", "pussy eating"
]

BJ_KEYWORDS = [
    "bj", "blowjob", "blow", "blowing", "head", "sucks", "sucked", "sucking",
    "mouth", "throat", "deep", "deepthroat", "deep-throat", "oral", "sloppy",
    "gag", "gagging", "cumshot", "facial", "swallow", "swallowing"
]

SEX_KEYWORDS = [
    "sex", "fuck", "fucked", "fucking", "dick", "cock", "ride", "riding",
    "doggy", "doggystyle", "missionary", "pound", "pounded", "pounding",
    "creampie", "anal", "cowgirl", "reverse", "hard", "raw", "plowed",
    "plough", "thrust", "thrusting", "penetrat", "screw", "screwing",
    "ffm", "mmf", "threesome", "foursome", "3some", "4some", "gangbang",
    "group", "orgy"
]

# ────────────────────────────────────────────────

def get_creator_slug(url: str) -> str:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if parts and parts[0] in ("es", "fr", "pt", "de", "it", "zh", "ja", "ru", "tr"):
        parts = parts[1:]
    for p in reversed(parts):
        if p and not p.isdigit() and "sort_by" not in p:
            slug = re.sub(r"-(leaked|exclusive-leaks|leaks)$", "", p)
            return slug.replace("-", "_")
    return "unknown"

def parse_url(url: str):
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    query = parse_qs(parsed.query)

    match = re.search(r"/(\d+)$", path)
    max_page = 1
    if match:
        max_page = int(match.group(1))
        path = path[:match.start()]

    sort_by = query.get("sort_by", [None])[0]
    return path, max_page, sort_by

def build_page_url(base_path: str, page: int, sort_by: Optional[str]) -> str:
    path = base_path + "/" if page == 1 else f"{base_path}/{page}/"
    if sort_by:
        return f"https://pimpbunny.com{path}?sort_by={sort_by}"
    return f"https://pimpbunny.com{path}"

def parse_duration(text: str) -> Optional[int]:
    text = text.strip()
    match = re.match(r"(?:(\d+):)?(\d+):(\d+)$", text)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    hours = int(hours) if hours else 0
    return hours * 3600 + int(minutes) * 60 + int(seconds)

def scrape_page(session: requests.Session, url: str) -> List[Tuple[str, Optional[int]]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = session.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠ Failed to fetch {url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/videos/" not in href or href.rstrip("/").endswith("/videos"):
            continue

        full = urljoin(url, href).split("?")[0].rstrip("/") + "/"
        if not re.search(r"/videos/[^/]+/$", full):
            continue

        duration_sec = None
        parent = a.find_parent(["div", "article", "li", "figure"])
        if parent:
            duration_text = parent.find(string=re.compile(r"\d+:\d{2}"))
            if duration_text:
                duration_sec = parse_duration(duration_text.strip())

        results.append((full, duration_sec))

    seen = set()
    unique = []
    for link, dur in results:
        if link not in seen:
            seen.add(link)
            unique.append((link, dur))
    return unique

def categorise(link: str) -> str:
    slug = link.lower()
    for neg in NEGATIVE_KEYWORDS:
        if neg in slug:
            return "Other"
    for kw in LESBIAN_KEYWORDS:
        if kw in slug:
            return "Lesbian"
    for kw in BJ_KEYWORDS:
        if kw in slug:
            return "BJ"
    for kw in SEX_KEYWORDS:
        if kw in slug:
            return "Sex"
    return "Other"

def main():
    if len(sys.argv) >= 2:
        input_url = sys.argv[1].strip()
    else:
        print("Paste the PimpBunny URL and press Enter:")
        input_url = input().strip()

    if not input_url:
        print("No URL provided.")
        sys.exit(1)

    base_path, max_page, sort_by = parse_url(input_url)
    creator = get_creator_slug(input_url)
    output_file = f"{creator}_links.txt"

    print(f"\nCreator   : {creator}")
    print(f"Base path : {base_path}")
    print(f"Pages     : 1 → {max_page}")
    if sort_by:
        print(f"Sort      : {sort_by}")
    print()

    session = requests.Session()
    all_items = []

    for page in range(1, max_page + 1):
        page_url = build_page_url(base_path, page, sort_by)
        print(f"Scraping page {page}/{max_page} → {page_url}")
        items = scrape_page(session, page_url)
        print(f"  Found {len(items)} videos")
        all_items.extend(items)

    # Deduplicate
    seen = set()
    unique_items = []
    for link, dur in all_items:
        if link not in seen:
            seen.add(link)
            unique_items.append((link, dur))

    print(f"\nTotal unique videos found: {len(unique_items)}")

    # === PROTECTION AGAINST OVERWRITING WITH EMPTY RESULTS ===
    if len(unique_items) == 0:
        print("\n⚠⚠⚠  WARNING: Found 0 videos (probably 503 or blocked).")
        print(f"    Existing file '{output_file}' will NOT be overwritten.")
        if Path(output_file).exists():
            print(f"    Keeping the previous version of {output_file}")
        else:
            print("    No previous file existed either.")
        return

    # Only reach here if we actually found videos
    cats = defaultdict(list)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"=== ALL LINKS ({len(unique_items)}) ===\n")
        for link, dur in unique_items:
            if dur is not None:
                mins = dur // 60
                secs = dur % 60
                f.write(f"{link}  |  {mins}:{secs:02d}\n")
            else:
                f.write(f"{link}  |  ??\n")
            cats[categorise(link)].append((link, dur))

        f.write("\n\n=== CATEGORISED ===\n")
        for cat in ("Sex", "BJ", "Lesbian", "Other"):
            f.write(f"\n--- {cat} ({len(cats[cat])}) ---\n")
            for link, dur in cats[cat]:
                if dur is not None:
                    mins = dur // 60
                    secs = dur % 60
                    f.write(f"{link}  |  {mins}:{secs:02d}\n")
                else:
                    f.write(f"{link}  |  ??\n")

    print(f"\nDone! Saved → {output_file}")
    print(f"  Sex     : {len(cats['Sex'])}")
    print(f"  BJ      : {len(cats['BJ'])}")
    print(f"  Lesbian : {len(cats['Lesbian'])}")
    print(f"  Other   : {len(cats['Other'])}")

if __name__ == "__main__":
    main()
