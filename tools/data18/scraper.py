#!/usr/bin/env python3
"""
data18 performer scraper.

  python scraper.py kyler-quinn            # prints every video as JSON
  python scraper.py "Kyler Quinn" --max-pages 2

Needs the age-verification cookie saved by setup_session.py (run that once first).
Pages come from data18's own listing endpoint, one request per 30 videos, until a page comes back empty.
"""
import argparse
import json
import re
import sys
import threading
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.data18.com"
HERE = Path(__file__).parent
SESSION_FILE = HERE / "data" / "session.json"
DELAY = 0.3          # seconds between listing-page requests
MAX_PAGES = 200      # safety limit
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


class SessionError(Exception):
    """The age-verification cookie is missing or no longer accepted."""


def slugify(name):
    """'Kyler Quinn' -> 'kyler-quinn'. A slug or a full performer URL also works."""
    name = name.strip()
    m = re.search(r"/name/([^/?#]+)", name)
    if m:
        return m.group(1).lower()
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_session():
    if not SESSION_FILE.exists():
        raise SessionError("No saved session. Run:  .venv/bin/python setup_session.py")
    data = json.loads(SESSION_FILE.read_text())
    s = requests.Session()
    s.headers["User-Agent"] = data.get("user_agent") or DEFAULT_UA
    s.headers["Accept-Language"] = "en-GB,en;q=0.9"
    for c in data.get("cookies", []):
        s.cookies.set(c["name"], c["value"], domain=c.get("domain") or ".data18.com", path=c.get("path") or "/")
    return s


def get(session, url, referer):
    r = session.get(url, headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"}, timeout=25)
    if r.status_code in (403, 404) and "ADULTS ONLY" in r.text[:4000]:
        raise SessionError("data18 is showing the age gate. Run:  .venv/bin/python setup_session.py")
    return r


def parse_items(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for box in soup.select('div[id^="item"]'):
        link = next((a for a in box.select('a[href*="/scenes/"]')
                     if "#" not in a["href"] and a.get("title")), None)
        if not link:
            continue
        url = link["href"].split("?")[0]
        if url.startswith("/"):
            url = BASE + url
        m = re.search(r"/scenes/(\d+)", url)
        meta = box.select_one("div.genmed")
        number = date = ""
        if meta:
            b = meta.find("b")
            number = b.get_text(strip=True).lstrip("#") if b else ""
            date = meta.get_text(" ", strip=True).replace(b.get_text(strip=True), "", 1).strip() if b else ""
        img = link.find("img") or box.select_one("img.yborder") or box.select_one("img")
        thumb = ""
        if img:
            # Lazy-loaded images carry a 1x1 placeholder in src and the real address in data-src.
            for attr in ("data-src", "data-original", "src"):
                val = img.get(attr) or ""
                if val and "pixel.jpg" not in val:
                    thumb = val
                    break
        performers = [t for t in (a.get_text(strip=True) for a in box.select('a[href*="/name/"]'))
                      if t and not t.startswith("[+")]
        studio = next((a.get_text(strip=True) for a in box.select('a[href*="/studios/"], a[href*="/sites/"]')), "")
        out.append({
            "number": number,
            "date": date,
            "scene_id": m.group(1) if m else "",
            "title": link["title"].strip(),
            "url": url,
            "thumbnail": thumb,
            "performers": performers,
            "studio": studio,
        })
    return out


# ---------------------------------------------------------------- scene details (categories / ethnicity / galleries)
DETAILS_FILE = HERE / "data" / "scene_details.json"
_details_lock = threading.Lock()
_details = None


def _load_details():
    global _details
    if _details is None:
        try:
            _details = json.loads(DETAILS_FILE.read_text())
        except Exception:
            _details = {}
    return _details


def _save_details():
    DETAILS_FILE.parent.mkdir(exist_ok=True)
    tmp = DETAILS_FILE.with_suffix(".tmp")
    with _details_lock:
        tmp.write_text(json.dumps(_details, ensure_ascii=False))
    tmp.replace(DETAILS_FILE)


def _clean(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


ETHNICITY_RE = re.compile(r"\b(girls|men|women|guys)$", re.I)


def normalise_details(d):
    """Ethnicity tags look like 'White Girls' / 'Black Men'. An unlabelled tag that follows them (e.g. 'Body Oil')
    is a category, so move anything that doesn't fit that pattern."""
    cats, eths = list(d["categories"]), []
    for t in d["ethnicity"]:
        if ETHNICITY_RE.search(t):
            eths.append(t)
        elif t not in cats:
            cats.append(t)
    return {**d, "categories": cats, "ethnicity": eths}


def parse_scene_details(html):
    """Return {'categories': [...], 'ethnicity': [...]} from a scene page, or None if it has no such block."""
    soup = BeautifulSoup(html, "html.parser")
    for marker in soup.find_all(["b", "span"]):
        label = marker.get_text(strip=True)
        if label not in ("Categories:", "Ethnicity:"):
            continue
        box = marker.parent
        cats, eths, slugs = [], [], []
        bucket = cats
        for node in box.children:
            name = getattr(node, "name", None)
            label = node.get_text(strip=True) if name in ("b", "span") else ""
            if label.endswith(":"):
                # "Ethnicity:" tags are ethnicity; every other labelled group ("Hair:" etc.) counts as categories.
                bucket = eths if label == "Ethnicity:" else cats
            elif name == "a" and "/tags/" in (node.get("href") or ""):
                text = _clean(node.get_text())
                if text and text not in bucket:
                    bucket.append(text)
                slug = re.search(r"/tags/([^/?#]+)", node["href"]).group(1)
                if slug not in slugs:
                    slugs.append(slug)   # the slug identifies the tag; names differ between pages
        if cats or eths:
            return normalise_details({"categories": cats, "ethnicity": eths, "tag_slugs": slugs})
    return None


# ---- galleries: Primary / Photoset / Video Stills / Trailer ...
def split_scene_id(full):
    """'1307354' -> ('1', '307354'): data18's own endpoints want the type digit and the number separately."""
    return full[0], full[1:]


def parse_galleries(html):
    """[(gallery_id, label, count)] from a scene page. Repeated labels become 'Photoset 1', 'Photoset 2'."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for d in soup.select("div.changeimggallery"):
        gid = (d.get("id") or "").replace("gallery", "")
        span = d.select_one("span.gen11")
        if not gid or not span:
            continue
        label = re.sub(r"\s*\d+$", "", _clean(span.get_text(" ")))
        b = span.find("b")
        found.append([gid, label or "Gallery", int(b.get_text(strip=True)) if b and b.get_text(strip=True).isdigit() else 0])
    totals = {}
    for _, label, _ in found:
        totals[label] = totals.get(label, 0) + 1
    seen = {}
    for g in found:
        if totals[g[1]] > 1:
            seen[g[1]] = seen.get(g[1], 0) + 1
            g[1] = f"{g[1]} {seen[g[1]]}"
    return [tuple(g) for g in found]


def full_size_url(thumb):
    """Thumbnail -> full-size address (checked against what data18's own viewer loads):
         .../th8_2/01.jpg -> .../t01.jpg        .../th8/05.jpg -> .../05.jpg"""
    return re.sub(r"/th8_2/(\d+\.\w+)$", r"/t\1", re.sub(r"/th8/(\d+\.\w+)$", r"/\1", thumb))


def _img_urls(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for img in soup.find_all("img"):
        u = img.get("data-src") or img.get("src") or ""
        if u.startswith("http") and "/images/" not in u and u not in out:
            out.append(u)
    return out


# ---- polite-but-parallel fetching: several workers, one shared speed limit, automatic pause when the site pushes back
WORKERS = 4
MIN_INTERVAL = 0.08          # seconds between any two requests overall (~12 per second)
_rate_lock = threading.Lock()
_next_slot = 0.0
_pause_until = 0.0
_tls = threading.local()


def _rate():
    """Block until this thread may send a request."""
    global _next_slot
    with _rate_lock:
        now = time.monotonic()
        t = max(now, _next_slot, _pause_until)
        _next_slot = t + MIN_INTERVAL
    if t > now:
        time.sleep(t - now)


def _backoff(seconds):
    """Everyone waits: the site said slow down."""
    global _pause_until
    with _rate_lock:
        _pause_until = max(_pause_until, time.monotonic() + seconds)


def _worker_session():
    if not hasattr(_tls, "session"):
        _tls.session = load_session()
    return _tls.session


def _request(session, path_or_url, referer, ajax=False):
    """GET with rate limiting and retries. Returns the Response, or None if it can't be read right now."""
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    headers = {"Referer": referer}
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    for attempt in range(4):
        _rate()
        try:
            r = session.get(url, headers=headers, timeout=25)
        except requests.RequestException:
            _backoff(2 * (attempt + 1))
            continue
        if "ADULTS ONLY" in r.text[:4000]:
            raise SessionError("data18 is showing the age gate. Run:  .venv/bin/python setup_session.py")
        if r.status_code in (429, 503):
            _backoff(10 * (attempt + 1))
            continue
        return r
    return None


def load_gallery_images(session, full_id, gallery, referer):
    """Fill gallery['images'] = [{'t': thumb, 'f': full}] (two requests at most). Returns False if it failed."""
    kind, scene = split_scene_id(full_id)
    r = _request(session, f"/sys/media_thumbs.php?s={kind}&scene={scene}&pic={gallery['gid']}", referer, ajax=True)
    if r is None or r.status_code != 200:
        return False
    thumbs = [u for u in _img_urls(r.text) if "/th8" in u]
    if thumbs:
        gallery["images"] = [{"t": u, "f": full_size_url(u)} for u in thumbs]
        return True
    # e.g. Primary: a single big picture, no thumbnail strip
    r = _request(session, f"/sys/media_photos.php?s={kind}&scene={scene}&animate=1&pic={gallery['gid']}&mscene=&screen=900",
                 referer, ajax=True)
    if r is None or r.status_code != 200:
        return False
    big = BeautifulSoup(r.text, "html.parser").select_one("#primaryphoto img")
    url = big.get("src") if big else next(iter(_img_urls(r.text)), "")
    gallery["images"] = [{"t": url, "f": url}] if url and url.startswith("http") else []
    return True


def fetch_scene_details(session, scene_id, referer):
    """Categories, ethnicity and the gallery list (names + counts, no images) for one scene. Cached.
    Returns None when the page couldn't be read this time."""
    cache = _load_details()
    if scene_id in cache and "galleries" in cache[scene_id] and "tag_slugs" in cache[scene_id]:
        return cache[scene_id]
    r = _request(session, f"/scenes/{scene_id}", referer)
    if r is None:
        return None
    if r.status_code == 404:
        found = {"categories": [], "ethnicity": [], "tag_slugs": [], "galleries": []}
    elif r.status_code == 200:
        found = parse_scene_details(r.text) or {"categories": [], "ethnicity": [], "tag_slugs": []}
        found = {**found, "galleries": [{"gid": gid, "label": label, "count": count}
                                        for gid, label, count in parse_galleries(r.text)]}
    else:
        return None
    with _details_lock:
        cache[scene_id] = found
    return found


def scene_galleries(scene_id):
    """Galleries with image addresses for one scene, fetched on demand (and cached). None if the scene is unknown."""
    cache = _load_details()
    d = cache.get(scene_id)
    if not d or "galleries" not in d:
        return None
    todo = [g for g in d["galleries"] if "images" not in g]
    if todo:
        session = _worker_session()
        referer = f"{BASE}/scenes/{scene_id}"
        for g in todo:
            if not load_gallery_images(session, scene_id, g, referer):
                raise RuntimeError("data18 didn't answer for the photos, try again in a moment")
        _save_details()
    return d["galleries"]


def gallery_summary(galleries):
    return [{"label": g["label"], "count": len(g["images"]) if "images" in g else g["count"]} for g in galleries]


def _apply(v, d):
    v["categories"], v["ethnicity"] = d["categories"], d["ethnicity"]
    v["tags"] = d["tag_slugs"]
    v["galleries"] = gallery_summary(d["galleries"])


def enrich(result, session=None, progress=lambda done, total: None, should_stop=lambda: False):
    """Fill in categories, ethnicity and gallery names on every video that doesn't have them yet (in parallel)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    referer = f"{BASE}/name/{result['slug']}"
    todo = [v for v in result["videos"] if "categories" not in v or "galleries" not in v or "tags" not in v]
    total = len(result["videos"])
    done = total - len(todo)
    since_save = 0

    def work(v):
        if should_stop():
            return v, None
        return v, fetch_scene_details(_worker_session(), v["scene_id"], referer)

    ex = ThreadPoolExecutor(max_workers=WORKERS)
    futures = [ex.submit(work, v) for v in todo]
    try:
        for f in as_completed(futures):
            v, d = f.result()          # a SessionError raised in a worker surfaces here
            if d is not None:
                _apply(v, d)
            done += 1
            since_save += 1
            progress(done, total)
            if since_save >= 25:
                _save_details()
                since_save = 0
    except BaseException:
        for f in futures:
            f.cancel()
        raise
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
        _save_details()
    return result


def apply_cached_details(result):
    cache = _load_details()
    for v in result["videos"]:
        d = cache.get(v["scene_id"])
        if d and "galleries" in d and "tag_slugs" in d:
            _apply(v, d)
    return result


# ---------------------------------------------------------------- performer listing
def scrape_listing(name, max_pages=MAX_PAGES, progress=lambda page, n: None, session=None):
    """Return {'slug', 'total', 'videos'} for one performer (no categories yet)."""
    slug = slugify(name)
    if not slug:
        raise ValueError("empty name")
    session = session or load_session()
    profile_url = f"{BASE}/name/{slug}"

    # The performer page itself is only used to check the performer exists and the session works.
    first = get(session, profile_url, BASE + "/")
    if first.status_code == 404:
        raise LookupError(f"No performer page at {profile_url}")
    first.raise_for_status()

    videos, seen = [], set()
    for page in range(1, max_pages + 1):
        url = (f"{BASE}/sys/page.php?t=2&b=1&o=0&html={slug}&html2=&total=&doquery=1"
               f"&spage={page}&dopage=1")
        r = get(session, url, profile_url)
        if r.status_code == 404:
            raise SessionError("data18 rejected the saved session. Run:  .venv/bin/python setup_session.py")
        r.raise_for_status()
        items = [i for i in parse_items(r.text) if i["scene_id"] not in seen]
        if not items:
            break
        for i in items:
            seen.add(i["scene_id"])
        videos.extend(items)
        progress(page, len(videos))
        time.sleep(DELAY)
    return apply_cached_details({"slug": slug, "total": len(videos), "videos": videos})


def scrape(name, max_pages=MAX_PAGES, progress=lambda page, n: None, details=True, details_progress=lambda d, t: None):
    session = load_session()
    result = scrape_listing(name, max_pages, progress, session)
    if details:
        enrich(result, session, details_progress)
    return result


# ---------------------------------------------------------------- studios
STUDIOS_FILE = HERE / "data" / "studios.json"


def parse_studios(html):
    """Studio rows from one page of data18's studio listing."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"/studios/([^/?#]+(?:/[^/?#]+)?)/?$", a["href"])
        if not m:
            continue
        text = _clean(a.get_text(" "))
        row = re.match(r"#(\d+) - (.*?) -{2,} ([\d,]+) scenes?", text)
        if not row:
            continue
        slug = m.group(1)
        bold = a.find("b")
        name = _clean(bold.get_text()) if bold else (a.get("title") or row.group(2)).strip()
        out.append({
            "rank": int(row.group(1)),
            "name": name,
            "slug": slug,
            "url": f"{BASE}/studios/{slug}",
            "scenes": int(row.group(3).replace(",", "")),
            "parent": slug.split("/")[0] if "/" in slug else "",
        })
    return out


def scrape_studios(progress=lambda page, n: None):
    """Every studio and sub-channel on data18.com/studios. Saved to data/studios.json."""
    session = load_session()
    rows, seen = [], set()
    for page in range(1, 200):
        r = _request(session, f"/sys/page.php?t=1&b=6&o=0&html=index&html2=&total=0&doquery=1&spage={page}&dopage=1",
                     BASE + "/studios", ajax=True)
        if r is None or r.status_code != 200:
            raise RuntimeError(f"data18 didn't answer for studios page {page}")
        items = [i for i in parse_studios(r.text) if i["slug"] not in seen]
        if not items:
            break
        for i in items:
            seen.add(i["slug"])
        rows.extend(items)
        progress(page, len(rows))
        time.sleep(DELAY)
    if not rows:
        raise RuntimeError("no studios found")
    names = {r["slug"]: r["name"] for r in rows}
    for r in rows:   # a sub-channel's parent is itself a studio most of the time; otherwise show the address part
        r["parent_name"] = names.get(r["parent"], r["parent"].replace("-", " ").title()) if r["parent"] else ""
    rows.sort(key=lambda r: r["rank"], reverse=True)   # the site's own order (A-Z)
    data = {"scraped_at": time.strftime("%Y-%m-%d %H:%M"), "total": len(rows), "studios": rows}
    STUDIOS_FILE.parent.mkdir(exist_ok=True)
    tmp = STUDIOS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(STUDIOS_FILE)
    return data


def load_studios():
    try:
        return json.loads(STUDIOS_FILE.read_text())
    except Exception:
        return None


# ---------------------------------------------------------------- tags (= categories)
TAGS_FILE = HERE / "data" / "tags.json"


def parse_tags(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"/tags/([^/?#]+)/?$", a["href"])
        if not m:
            continue
        text = _clean(a.get_text(" "))
        row = re.match(r"#(\d+) - - (.*?) -{2,} ", text)
        if not row:
            continue
        out.append({"rank": int(row.group(1)), "name": _clean(a.get("title") or row.group(2)),
                    "slug": m.group(1), "url": f"{BASE}/tags/{m.group(1)}"})
    return out


def scrape_tags(progress=lambda page, n: None):
    """All tags on data18.com/tags (one-time: the list doesn't change). Saved to data/tags.json."""
    session = load_session()
    rows, seen = [], set()
    for page in range(1, 100):
        r = _request(session, f"/sys/page.php?t=1&b=7&o=0&html=index&html2=&total=0&doquery=1&spage={page}&dopage=1",
                     BASE + "/tags", ajax=True)
        if r is None or r.status_code != 200:
            raise RuntimeError(f"data18 didn't answer for tags page {page}")
        items = [i for i in parse_tags(r.text) if i["slug"] not in seen]
        if not items:
            break
        for i in items:
            seen.add(i["slug"])
        rows.extend(items)
        progress(page, len(rows))
        time.sleep(DELAY)
    if not rows:
        raise RuntimeError("no tags found")
    rows.sort(key=lambda r: r["name"].lower())
    data = {"scraped_at": time.strftime("%Y-%m-%d %H:%M"), "total": len(rows), "tags": rows}
    TAGS_FILE.parent.mkdir(exist_ok=True)
    tmp = TAGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(TAGS_FILE)
    return data


def load_tags():
    try:
        return json.loads(TAGS_FILE.read_text())
    except Exception:
        return None


# ---------------------------------------------------------------- pornstars (names + profile pictures)
STARS_FILE = HERE / "data" / "pornstars.json"


def parse_pornstars(html):
    """Performer cards from one page of data18's name listing."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"/name/([^/?#]+)/?$", a["href"])
        img = a.find("img")
        if not m or not img:
            continue
        card = a.parent
        pic = img.get("data-src") or img.get("src") or ""
        rank = re.search(r"#(\d+)", card.get_text(" ")) if card else None
        scenes = re.search(r"([\d,]+)\s+Scenes?", card.get_text(" ")) if card else None
        movies = re.search(r"Movies \[([\d,]+)\]", card.get_text(" ")) if card else None
        latest = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", card.get_text(" ")) if card else None
        out.append({
            "slug": m.group(1),
            "name": _clean(a.get("title") or img.get("alt") or m.group(1)),
            "picture": "" if ("no_prev" in pic or not pic.startswith("http")) else pic,   # no_prev_* = data18's "no photo" placeholder
            "scenes": int(scenes.group(1).replace(",", "")) if scenes else 0,
            "movies": int(movies.group(1).replace(",", "")) if movies else 0,
            "rank": int(rank.group(1)) if rank else 0,
            "latest": latest.group(1) if latest else "",
        })
    return out


def scrape_pornstars(progress=lambda page, n: None, should_stop=lambda: False):
    """Every performer on data18.com/names/pornstars (~560 pages of 40). Saved to data/pornstars.json."""
    session = load_session()
    rows, seen = [], set()
    for page in range(1, 2000):
        if should_stop():
            raise RuntimeError("stopped")
        r = _request(session, f"/sys/page.php?t=1&b=5&o=0&html=index&html2=&total=0&doquery=1&spage={page}&dopage=1",
                     BASE + "/names/pornstars", ajax=True)
        if r is None or r.status_code != 200:
            raise RuntimeError(f"data18 didn't answer for pornstars page {page}; nothing was saved")
        items = [i for i in parse_pornstars(r.text) if i["slug"] not in seen]
        if not items:
            break
        for i in items:
            seen.add(i["slug"])
        rows.extend(items)
        progress(page, len(rows))
    if not rows:
        raise RuntimeError("no performers found")
    data = {"scraped_at": time.strftime("%Y-%m-%d %H:%M"), "total": len(rows), "stars": rows}
    STARS_FILE.parent.mkdir(exist_ok=True)
    tmp = STARS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(STARS_FILE)          # only replaced once the whole list is in, so a failed run never leaves half a file
    return data


def load_pornstars():
    try:
        return json.loads(STARS_FILE.read_text())
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--max-pages", type=int, default=MAX_PAGES)
    args = ap.parse_args()
    try:
        result = scrape(args.name, args.max_pages,
                        progress=lambda p, n: print(f"page {p}: {n} videos so far", file=sys.stderr))
    except (SessionError, LookupError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
