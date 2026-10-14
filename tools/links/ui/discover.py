"""Discover: collect the performer directory, keep the profile pictures, and hand out cards to swipe through.

Data lives in <data>/discover/:
    performers.json   every performer found: name, rank, video / view counts, picture address, directory page
    state.json        the shuffled order, your decisions (keep / skip), history for undo, settings
    img/<slug>.jpg    the profile pictures, saved so the cards do not depend on the site

Only /pornstar/ entries are collected. The site's robots.txt asks bots to stay off /model/ sub-pages, so those are skipped.
The collector is slow on purpose (a few seconds between pages) and stops as soon as the site says "too many requests".
"""
import html
import json
import random
import re
import threading
import time
from pathlib import Path

BASE = "https://www.pornhub.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
COOKIES = {"accessAgeDisclaimerPH": "1", "accessAgeDisclaimerUK": "1"}
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

_L = threading.RLock()
PROGRESS = {"running": False, "phase": "", "page": 0, "pages": 0, "found": 0, "images": 0, "images_total": 0,
            "message": "", "error": None}
DEFAULT_SETTINGS = {"scrape_pages": "10", "min_videos": 0, "max_videos": 0, "min_views": 0, "max_views": 0,
                    "verified_only": False, "max_rank": 0}
FILTER_KEYS = ("min_videos", "max_videos", "min_views", "max_views", "verified_only", "max_rank")


class Store:
    def __init__(self, data_dir):
        self.dir = Path(data_dir) / "discover"
        self.img = self.dir / "img"
        self.img.mkdir(parents=True, exist_ok=True)
        self.perf_file = self.dir / "performers.json"
        self.state_file = self.dir / "state.json"

    # --- files
    def _read(self, f, default):
        try:
            return json.loads(f.read_text())
        except Exception:
            return default

    def _write(self, f, obj):
        tmp = f.with_suffix(f.suffix + ".tmp")
        tmp.write_text(json.dumps(obj))
        tmp.replace(f)

    def performers(self):
        return self._read(self.perf_file, {})

    def state(self):
        s = self._read(self.state_file, {})
        s.setdefault("order", [])
        s.setdefault("decisions", {})
        s.setdefault("history", [])
        s.setdefault("settings", dict(DEFAULT_SETTINGS))
        for k, v in DEFAULT_SETTINGS.items():
            s["settings"].setdefault(k, v)
        return s

    def save_state(self, s):
        self._write(self.state_file, s)

    def image_path(self, slug):
        f = self.img / (re.sub(r"[^a-z0-9._-]", "", slug.lower()) + ".jpg")
        return f if f.is_file() and f.stat().st_size > 200 else None


# ───────────────────────── reading the directory ─────────────────────────

def parse_count(txt):
    if not txt:
        return 0
    t = txt.strip().replace(",", "").lower()
    m = re.match(r"([\d.]+)\s*([kmb]?)", t)
    if not m:
        return 0
    return int(float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2)])


def parse_directory(page_html, page_no):
    """The performers on one directory page. Entries under /model/ are skipped (see the module note)."""
    out = []
    for c in re.findall(r'<li[^>]*class="[^"]*(?:pornstarLi|performerCard)[^"]*"[^>]*>(.*?)</li>', page_html, re.S):
        m = re.search(r'href="/pornstar/([^"/?#]+)"', c)
        if not m:
            continue
        slug = html.unescape(m.group(1)).strip().lower()
        alt = re.search(r'<img[^>]*\balt="([^"]+)"', c)
        nm = re.search(r'class="performerName"[^>]*>\s*([^<]+?)\s*<', c)
        name = html.unescape((nm.group(1) if nm else alt.group(1) if alt else slug.replace("-", " ").title())).strip()
        img = re.search(r'data-image="([^"]+)"', c) or re.search(r'data-thumb_url="([^"]+)"', c) or \
            re.search(r'<img[^>]*\bsrc="(https://[^"]+)"', c)
        rank = re.search(r'(?:rankNumber|rank_number)">\s*(\d+)', c)
        vids = re.search(r'(?:videosCount|videosNumber)[^>]*>\s*([\d,.]+\s*[KkMm]?)\s*(?:<span>)?\s*Videos', c)
        views = re.search(r'(?:viewsCount|viewsNumber)[^>]*>\s*([\d,.]+\s*[KkMmBb]?)\s*(?:<span>)?\s*Views', c)
        out.append({"slug": slug, "name": name, "rank": int(rank.group(1)) if rank else None,
                    "videos": parse_count(vids.group(1)) if vids else 0,
                    "views": parse_count(views.group(1)) if views else 0,
                    "verified": "Verified Model" in c, "image_url": html.unescape(img.group(1)) if img else None,
                    "page": page_no})
    return out


def _get(session, url, tries=3):
    """-> (response or None, reason). Gives up at once on 429/403 (the site is telling us to stop)."""
    last = ""
    for i in range(tries):
        try:
            r = session.get(url, timeout=30)
        except Exception as e:
            last = str(e)[:120]
            time.sleep(2 + i * 2)
            continue
        if r.status_code in (403, 429):
            return None, "the site answered %d (too many requests). Stopped to stay polite." % r.status_code
        if r.status_code == 200:
            return r, ""
        last = "HTTP %d" % r.status_code
        time.sleep(2 + i * 2)
    return None, last or "no answer"


def collect(store, pages, say, should_stop, delay=(2.2, 3.8)):
    """Read directory pages 1..pages, save the performers, then download any missing profile pictures."""
    import requests
    s = requests.Session()
    s.headers.update(HEADERS)
    s.cookies.update(COOKIES)
    with _L:
        PROGRESS.update(running=True, phase="pages", page=0, pages=pages, found=len(store.performers()), images=0,
                        images_total=0, message="Reading the directory...", error=None)
    perf = store.performers()
    stopped_early = False
    for p in range(1, pages + 1):
        if should_stop():
            stopped_early = True
            break
        r, why = _get(s, "%s/pornstars?t=a&page=%d" % (BASE, p))
        if r is None:
            with _L:
                PROGRESS.update(error="Page %d: %s" % (p, why))
            say("Page %d: %s" % (p, why))
            stopped_early = True
            break
        got = parse_directory(r.text, p)
        for g in got:
            old = perf.get(g["slug"], {})
            perf[g["slug"]] = {**old, **{k: v for k, v in g.items() if v not in (None, "")}}
        store._write(store.perf_file, perf)
        with _L:
            PROGRESS.update(page=p, found=len(perf), message="Page %d of %d: %d performers so far" % (p, pages, len(perf)))
        say("page %d: %d performers (%d total)" % (p, len(got), len(perf)))
        if not got and p > 1:
            say("page %d had no performers: the end of the list" % p)
            break
        time.sleep(random.uniform(*delay))

    # new performers go into the shuffled deck
    with _L:
        st = store.state()
        known = set(st["order"]) | set(st["decisions"])
        fresh = [sl for sl in perf if sl not in known]
        rnd = random.Random()
        for _ in range(3):                                     # shuffled, then shuffled again, then again
            rnd.shuffle(fresh)
        st["order"] = fresh + st["order"] if not st["order"] else st["order"] + fresh
        undecided = [x for x in st["order"] if x not in st["decisions"]]
        for _ in range(3):
            rnd.shuffle(undecided)
        st["order"] = undecided + [x for x in st["order"] if x in st["decisions"]]
        st["collected_pages"] = max(st.get("collected_pages", 0), pages if not stopped_early else st.get("collected_pages", 0))
        st["collected_at"] = int(time.time())
        store.save_state(st)

    # profile pictures
    need = [(sl, d["image_url"]) for sl, d in perf.items() if d.get("image_url") and not store.image_path(sl)]
    with _L:
        PROGRESS.update(phase="images", images=0, images_total=len(need), message="Saving %d profile pictures..." % len(need))
    done = 0
    for sl, url in need:
        if should_stop():
            break
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 200 and len(r.content) > 200:
                (store.img / (sl + ".jpg")).write_bytes(r.content)
            elif r.status_code in (403, 429):
                say("pictures: the site answered %d. Stopped." % r.status_code)
                with _L:
                    PROGRESS.update(error="Pictures: the site answered %d. Stopped." % r.status_code)
                break
        except Exception:
            pass
        done += 1
        if done % 10 == 0 or done == len(need):
            with _L:
                PROGRESS.update(images=done)
        time.sleep(random.uniform(0.12, 0.3))
    with _L:
        PROGRESS.update(running=False, phase="done", images=done,
                        message="Done: %d performers, %d pictures." % (len(perf), sum(1 for sl in perf if store.image_path(sl))))
    say("finished: %d performers" % len(perf))


# ───────────────────────── the deck ─────────────────────────

def creator_slug(performer_slug):
    return performer_slug.replace("-", "_")


def card(p, store):
    return {"slug": p["slug"], "name": p["name"], "rank": p.get("rank"), "videos": p.get("videos", 0),
            "views": p.get("views", 0), "verified": bool(p.get("verified")), "page": p.get("page"),
            "image": ("/discover_img/%s.jpg" % p["slug"]) if store.image_path(p["slug"]) else None,
            "url": "%s/pornstar/%s" % (BASE, p["slug"])}


def visible(st, perf, existing, store):
    """The undecided performers, in deck order, after the filters."""
    S = st["settings"]
    min_v, max_v = int(S.get("min_videos") or 0), int(S.get("max_videos") or 0)
    min_w, max_w = int(S.get("min_views") or 0), int(S.get("max_views") or 0)
    ver, max_rank = bool(S.get("verified_only")), int(S.get("max_rank") or 0)
    for slug in st["order"]:
        if slug in st["decisions"]:
            continue
        p = perf.get(slug)
        if not p or creator_slug(slug) in existing:
            continue
        v, w = p.get("videos") or 0, p.get("views") or 0
        if (min_v and v < min_v) or (max_v and v > max_v) or (min_w and w < min_w) or (max_w and w > max_w):
            continue
        if ver and not p.get("verified"):
            continue
        if max_rank and (p.get("rank") is None or p["rank"] > max_rank):
            continue
        yield p


def deck(store, n, existing, offset_skip=()):
    with _L:
        st, perf = store.state(), store.performers()
        skip = set(offset_skip)
        cards, left = [], 0
        for p in visible(st, perf, existing, store):
            left += 1
            if p["slug"] in skip or len(cards) >= n:
                continue
            cards.append(card(p, store))
        return {"cards": cards, "left": left}


def summary(store, existing):
    with _L:
        st, perf = store.state(), store.performers()
        dec = st["decisions"]
        kept = sum(1 for v in dec.values() if v["d"] == "keep")
        skipped = sum(1 for v in dec.values() if v["d"] == "skip")
        left = sum(1 for _ in visible(st, perf, existing, store))
        return {"total": len(perf), "left": left, "kept": kept, "skipped": skipped, "has_data": bool(perf),
                "pictures": sum(1 for sl in perf if store.image_path(sl)), "settings": st["settings"],
                "collected_pages": st.get("collected_pages", 0), "collected_at": st.get("collected_at"),
                "filters_active": sum(1 for k in FILTER_KEYS if st["settings"].get(k)),
                "ranges": {"max_views": max((p.get("views") or 0 for p in perf.values()), default=0),
                           "max_videos": max((p.get("videos") or 0 for p in perf.values()), default=0),
                           "max_rank": max((p.get("rank") or 0 for p in perf.values()), default=0)},
                "hidden_existing": sum(1 for sl in perf if creator_slug(sl) in existing and sl not in dec),
                "progress": dict(PROGRESS), "can_undo": bool(st["history"])}


def decide(store, slug, keep):
    with _L:
        st, perf = store.state(), store.performers()
        if slug not in perf:
            raise ValueError("unknown performer")
        st["decisions"][slug] = {"d": "keep" if keep else "skip", "t": int(time.time())}
        st["history"] = (st["history"] + [slug])[-200:]
        store.save_state(st)
        return perf[slug]


def undo(store):
    """Take back the last decision. Returns (card, was_keep) or None."""
    with _L:
        st, perf = store.state(), store.performers()
        while st["history"]:
            slug = st["history"].pop()
            d = st["decisions"].pop(slug, None)
            if d is None or slug not in perf:
                continue
            st["order"] = [slug] + [x for x in st["order"] if x != slug]
            store.save_state(st)
            return card(perf[slug], store), d["d"] == "keep"
        store.save_state(st)
        return None


def reshuffle(store):
    with _L:
        st = store.state()
        undecided = [x for x in st["order"] if x not in st["decisions"]]
        rnd = random.Random()
        for _ in range(3):
            rnd.shuffle(undecided)
        st["order"] = undecided + [x for x in st["order"] if x in st["decisions"]]
        store.save_state(st)
        return len(undecided)


def reset_skipped(store):
    with _L:
        st = store.state()
        back = [s for s, v in st["decisions"].items() if v["d"] == "skip"]
        for s in back:
            st["decisions"].pop(s, None)
        st["history"] = [h for h in st["history"] if h not in back]
        rnd = random.Random()
        undecided = [x for x in st["order"] if x not in st["decisions"]] + [b for b in back if b not in st["order"]]
        undecided = list(dict.fromkeys(undecided))
        rnd.shuffle(undecided)
        st["order"] = undecided + [x for x in st["order"] if x in st["decisions"]]
        store.save_state(st)
        return len(back)


def _num(v, hi=10**13):
    try:
        return max(0, min(int(float(v)), hi))
    except (TypeError, ValueError):
        return 0


def set_settings(store, body):
    with _L:
        st = store.state()
        S = st["settings"]
        if body.get("reset_filters"):
            for k in FILTER_KEYS:
                S[k] = DEFAULT_SETTINGS[k]
        if "scrape_pages" in body:
            sp = str(body.get("scrape_pages")).strip().lower()
            S["scrape_pages"] = "all" if sp == "all" else str(max(1, min(_num(sp) or 10, 200)))
        for k in ("min_videos", "max_videos", "min_views", "max_views", "max_rank"):
            if k in body:
                S[k] = _num(body[k])
        if "verified_only" in body:
            S["verified_only"] = bool(body["verified_only"])
        store.save_state(st)
        return S


def kept_recent(store, n=14):
    with _L:
        st, perf = store.state(), store.performers()
        keeps = sorted(((v["t"], s) for s, v in st["decisions"].items() if v["d"] == "keep"), reverse=True)[:n]
        return [card(perf[s], store) for _, s in keeps if s in perf]
