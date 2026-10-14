#!/usr/bin/env python3
"""
Links UI - local web interface for the scrape / sort / download pipeline.

Run:  python3 ui/server.py        (opens http://127.0.0.1:8790)

Rules this app follows:
  * It never writes to ../necessary or ../good too. Those scripts are only
    *run* (scrape_fruitsvids.py) or *read* (domain, keyword lists).
  * All output lives in ui/data/.
  * It starts with no links; the Creators tab is how you get them.
"""
import sys

sys.dont_write_bytecode = True  # never drop __pycache__ next to your scripts

import argparse
import difflib
import hashlib
import ast
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

UI_DIR = Path(__file__).resolve().parent
ROOT = UI_DIR.parent
STATIC = UI_DIR / "static"
DATA = Path(os.environ.get("LINKS_UI_DATA") or UI_DIR / "data")
LINKS = DATA / "links"      # raw output of scrape_fruitsvids.py (one file per creator)
LISTS = DATA / "lists"      # optional exported .txt lists
SETTINGS_FILE = DATA / "settings.json"
CREATORS_FILE = DATA / "creators.json"
DOWNLOADED_FILE = DATA / "downloaded.json"
RUN_CONFIG = DATA / "run_config.json"
PROFILES_FILE = DATA / "profiles.json"
PROFILE_DIR = DATA / "profiles"
AVATARS = DATA / "avatars"
TEMPLATES = DATA / "templates"   # pictures of the VDH icon / Download button, used to find them on screen

import scraper as profile_scraper  # ui/scraper.py (lazy-imports requests/bs4)
import discover                    # ui/discover.py: the swipe-through "Discover" page

DEFAULTS = {
    "scraper_path": str(ROOT / "necessary" / "scrape_fruitsvids.py"),
    "scrape_pause": 2,
    "bucket_edges_min": [11, 17, 25],
    "download_dir": str(Path.home() / "Downloads"),
    "library_dir": str(Path(__file__).resolve().parents[3] / "library"),
    "vdh_icon": [1248, 95],
    "download_button": [1177, 382],
    "page_load_wait": 5.5,
    "menu_wait": 1.8,
    "download_wait": 25,
    "download_method": "vdh",     # "vdh" = click Video DownloadHelper in Chrome, "ytdlp" = run yt-dlp (no browser, no clicking)
    "ytdlp_max_height": "",       # yt-dlp only: don't download better than this many pixels high (e.g. 720). Empty = best available
    "stop_after_failures": 4,     # stop a download run after this many links in a row that didn't start (0 = never stop)
    "use_image_clicks": True,      # find the VDH icon and Download button by their picture (needs them captured in Settings)
    "image_match_threshold": 0.8, # how closely the screen must match the picture (0 to 1)
    "max_parallel": 3,            # downloads allowed in progress at the same time
    "max_download_minutes": 40,   # give up on a single download after this long
    "pause_between_links": 3,
    "target_success": 10,
    "max_attempts": 30,
    "startup_delay": 8,
    "min_video_minutes": "",      # scrapes skip videos shorter than this many minutes (empty = no lower limit)
    "max_video_minutes": "",      # ... and longer than this (empty = no upper limit)
    "default_site": "",           # the site preselected when you add creators or import (empty = the first one)
    "pages_default_all": True,    # a link with no page number (or a plain name) scrapes every page until the site runs out
    "name_match": True,           # link "jane-doe" and "liljanedoe" to one creator automatically
    "name_match_min_len": 7,      # auto-link only when the shorter name has at least this many letters
    "name_match_ask_pct": 80,     # share of the shorter name found in the other, at or above which we ask you
}

LOCK = threading.RLock()


def code_fingerprint():
    """A short hash of the program's code files. When it changes on disk, the running server is out of date."""
    h = hashlib.md5()
    for name in ("server.py", "scraper.py", "downloader.py"):
        try:
            h.update((UI_DIR / name).read_bytes())
        except OSError:
            pass
    return h.hexdigest()[:10]


STARTED_WITH = None   # set when the server starts

# Child processes must print UTF-8 (the ✓/✗/→ in logs). Windows pipes default to cp1252 and would crash.
CHILD_ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONWARNINGS": "ignore", "PYTHONDONTWRITEBYTECODE": "1"}


# ───────────────────────── storage helpers ─────────────────────────

def ensure_dirs():
    for d in (DATA, LINKS, LISTS, PROFILE_DIR, AVATARS):
        d.mkdir(parents=True, exist_ok=True)


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_settings():
    s = dict(DEFAULTS)
    s.update(read_json(SETTINGS_FILE, {}))
    return s


def save_settings(new):
    s = load_settings()
    for k, default in DEFAULTS.items():
        if k not in new:
            continue
        v = new[k]
        try:
            if isinstance(default, bool):
                v = bool(v)
            elif isinstance(default, int):
                v = int(float(v))
            elif isinstance(default, float):
                v = float(v)
            elif isinstance(default, list):
                v = [int(float(x)) for x in v]
                if len(v) != len(default) and k != "bucket_edges_min":
                    raise ValueError("wrong length")
                if k == "bucket_edges_min":
                    v = sorted(set(x for x in v if x > 0))
                    if not v:
                        raise ValueError("need at least one edge")
            else:
                v = str(v).strip()
        except Exception:
            raise ValueError("Invalid value for %s" % k)
        s[k] = v
    if s.get("download_method") not in ("vdh", "ytdlp"):
        raise ValueError("Download method must be vdh or ytdlp")
    if str(s.get("ytdlp_max_height", "")).strip() and not str(s["ytdlp_max_height"]).strip().isdigit():
        raise ValueError("Highest quality must be a number of pixels (like 720), or empty")
    for k in ("min_video_minutes", "max_video_minutes"):
        if str(s.get(k, "")).strip():
            try:
                if float(s[k]) < 0:
                    raise ValueError
            except ValueError:
                raise ValueError("%s must be a number of minutes, or empty" % ("Shortest video" if k.startswith("min") else "Longest video"))
            s[k] = str(s[k]).strip()
    lo, hi = limit_seconds(s)
    if lo is not None and hi is not None and lo > hi:
        raise ValueError("The shortest video can't be longer than the longest")
    write_json(SETTINGS_FILE, s)
    return s


# ───────────────────────── reading the user's scraper (read-only) ─────────────────────────

_script_cache = {"mtime": None, "path": None, "info": None, "slug_fn": None}


def _fallback_slug(url):
    parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
    if parts and parts[0] in ("es", "fr", "pt", "de", "it", "zh", "ja", "ru", "tr"):
        parts = parts[1:]
    for p in reversed(parts):
        if not p.isdigit() and "sort_by" not in p:
            return p.replace("-", "_")
    return "unknown"


def script_info():
    """Read the scraper's domain, keyword lists and slug function without modifying it."""
    s = load_settings()
    path = Path(s["scraper_path"])
    info = {
        "path": str(path),
        "exists": path.exists(),
        "base_url": None,
        "domain": None,
        "categories": ["Other"],
        "keywords": {},
        "negative": [],
        "error": None,
    }
    if not path.exists():
        info["error"] = "Scraper script not found"
        return info, _fallback_slug

    mtime = path.stat().st_mtime
    if _script_cache["path"] == str(path) and _script_cache["mtime"] == mtime:
        return _script_cache["info"], _script_cache["slug_fn"]

    text = path.read_text(encoding="utf-8")

    m = re.search(r"def build_page_url.*?(https?)://([A-Za-z0-9.\-:]+)", text, re.S)
    if m:
        info["base_url"] = "%s://%s" % (m.group(1), m.group(2))
        info["domain"] = m.group(2)
    else:
        info["error"] = "Could not find the site domain in build_page_url()"

    try:
        tree = ast.parse(text)
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                t = node.targets[0]
                if isinstance(t, ast.Name) and t.id.endswith("_KEYWORDS"):
                    kws = [str(k).lower() for k in ast.literal_eval(node.value)]
                    name = t.id[: -len("_KEYWORDS")]
                    if name == "NEGATIVE":
                        info["negative"] = kws
                    else:
                        cat = name.title()
                        info["keywords"][cat] = kws
        info["categories"] = list(info["keywords"].keys()) + ["Other"]
    except Exception as e:  # keep going with no categories
        info["error"] = "Could not read keyword lists: %s" % e

    slug_fn = _fallback_slug
    try:
        spec = importlib.util.spec_from_file_location("user_scraper_readonly", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "get_creator_slug"):
            slug_fn = mod.get_creator_slug
    except Exception:
        pass

    _script_cache.update(mtime=mtime, path=str(path), info=info, slug_fn=slug_fn)
    return info, slug_fn


def categorise(url, info):
    slug = url.lower()
    for neg in info["negative"]:
        if neg in slug:
            return "Other"
    dom = info.get("dominant") or ""
    order = ([dom] if dom in info["keywords"] else []) + [c for c in info["keywords"] if c != dom]
    for cat in order:
        for kw in info["keywords"][cat]:
            if kw in slug:
                return cat
    return "Other"


# ───────────────────────── site profiles ─────────────────────────
# "script" is a virtual profile: it runs the user's scrape_fruitsvids.py unchanged.
# Every other profile is stored in ui/data/profiles.json and run by ui/scraper.py.

SCRIPT_ID = "script"


def load_profiles():
    # with_defaults also upgrades profiles saved with the older pagination fields
    return [profile_scraper.with_defaults(dict(p, id=p["id"])) for p in read_json(PROFILES_FILE, [])]


def script_profile():
    info, _ = script_info()
    return {
        "id": SCRIPT_ID,
        "name": "Your script" + (" (%s)" % info["domain"] if info["domain"] else ""),
        "virtual": True,
        "base_url": info["base_url"],
        "keywords": info["keywords"],
        "negative": info["negative"],
    }


def all_profiles():
    return [script_profile()] + load_profiles()


def get_profile(pid):
    for p in all_profiles():
        if p["id"] == pid:
            return p
    return script_profile()


def validate_profile(raw):
    base = dict(profile_scraper.DEFAULT_PROFILE)
    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError("Give the site a name")
    base_url = str(raw.get("base_url", "")).strip().rstrip("/")
    if not re.match(r"^https?://[^/\s]+$", base_url):
        raise ValueError("Base URL must look like https://example.com (no path)")
    template = str(raw.get("page_template", "")).strip()
    if not (template.startswith("/") or template.startswith("{path}")) \
            or "{path}" not in template or "{page}" not in template:
        raise ValueError("Next-page format must contain both {path} and {page}, "
                         "e.g. {path}/page/{page}/")
    for field in ("video_link_regex", "duration_regex"):
        try:
            re.compile(str(raw.get(field, "")))
        except re.error as e:
            raise ValueError("Invalid pattern in %s: %s" % (field, e))
        if not str(raw.get(field, "")).strip():
            raise ValueError("%s can't be empty" % field)
    def clean(w):
        return str(w).strip().strip("\"'“”‘’").strip().lower()

    key_attr = clean_text(raw.get("video_key_attr", "")).strip("\"'“”‘’ ")
    key_tpl = clean_text(raw.get("video_url_template") or "/view_video.php?viewkey={key}").strip("\"'“”‘’ ")
    scope = clean_text(raw.get("scope_selector", ""))
    nf = raw.get("not_found_text", ["page not found"])
    nf = [x.strip() for x in (nf.splitlines() if isinstance(nf, str) else nf) if str(x).strip()]
    avatar_sel = clean_text(raw.get("avatar_selector", ""))
    avatar_attr = clean_text(raw.get("avatar_attr") or "src").strip("\"'“”‘’ ") or "src"
    sections = []
    raw_secs = raw.get("sections") or []
    if isinstance(raw_secs, str):
        raw_secs = [{"address": a.strip(), "scope": b.strip()} for a, _, b in (ln.partition("|") for ln in raw_secs.splitlines()) if a.strip()]
    for sec in raw_secs:
        addr = clean_text(sec.get("address", "")).strip("\"'“”‘’ ")
        scope_ = clean_text(sec.get("scope", ""))
        if not addr:
            continue
        if not addr.startswith("{root}"):
            raise ValueError("Each page address must start with {root}, e.g. {root}/videos/upload?o=mv  (got: %s)" % addr)
        if scope_:
            try:
                from bs4 import BeautifulSoup
                BeautifulSoup("<p></p>", "html.parser").select(scope_)
            except Exception as e:
                raise ValueError("The 'only look inside' selector for %s isn't valid: %s" % (addr, e))
        sections.append({"address": addr, "scope": scope_})
    views_sel = clean_text(raw.get("views_selector", ""))
    if views_sel:
        try:
            from bs4 import BeautifulSoup
            BeautifulSoup("<p></p>", "html.parser").select(views_sel)
        except Exception as e:
            raise ValueError("The view count selector isn't valid: %s" % e)
    exclude = clean_text(raw.get("exclude_selector", ""))
    if exclude:
        try:
            from bs4 import BeautifulSoup
            BeautifulSoup("<p></p>", "html.parser").select(exclude)
        except Exception as e:
            raise ValueError("The 'ignore' selector isn't valid: %s" % e)
    if avatar_sel:
        try:
            from bs4 import BeautifulSoup
            BeautifulSoup("<p></p>", "html.parser").select(avatar_sel)
        except Exception as e:
            raise ValueError("The profile picture selector isn't valid: %s" % e)
    if key_attr:
        if not re.match(r"^[A-Za-z_:][-A-Za-z0-9_:.]*$", key_attr):
            raise ValueError("The attribute name looks wrong. It should be something like data-video-vkey")
        if "{key}" not in key_tpl or not (key_tpl.startswith("/") or re.match(r"^https?://", key_tpl)):
            raise ValueError("The video link must start with / and contain {key}, e.g. /view_video.php?viewkey={key}")
    if scope:
        try:
            from bs4 import BeautifulSoup
            BeautifulSoup("<div></div>", "html.parser").select(scope)
        except Exception as e:
            raise ValueError("That CSS selector isn't valid: %s" % str(e)[:80])

    patterns = []
    for line in (raw.get("creator_patterns") or []):
        line = clean_text(line).strip("\"'“”‘’").strip()
        if not line:
            continue
        if not any(ph in line for ph in ("{name}", "{compact}", "{underscore}")):
            raise ValueError("Each address to try must contain {name}, {compact} or {underscore}: %s" % line)
        if not (line.startswith("/") or re.match(r"^https?://", line)):
            raise ValueError("Each address to try must start with / or https://: %s" % line)
        if line not in patterns:
            patterns.append(line)
    if len(patterns) > 60:
        raise ValueError("Too many addresses to try (max 60)")

    kws = {}
    for cat, words in (raw.get("keywords") or {}).items():
        cat = str(cat).strip().strip("\"'“”‘’").strip()
        if not cat or cat.lower() == "other":
            continue
        kws[cat] = [clean(w) for w in words if clean(w)]
    base.update({
        "name": name,
        "base_url": base_url,
        "page_template": template,
        "video_link_regex": str(raw["video_link_regex"]),
        "duration_regex": str(raw["duration_regex"]),
        "slug_strip": [str(s).strip() for s in raw.get("slug_strip", []) if str(s).strip()],
        "keywords": kws,
        "negative": [clean(w) for w in raw.get("negative", []) if clean(w)],
        "download_method": raw.get("download_method") if raw.get("download_method") in ("vdh", "ytdlp") else "",
        "dominant": (lambda d: d if d in kws else "")(str(raw.get("dominant") or "").strip().strip("\"'“”‘’ ")),
        "request_delay": max(0.0, float(raw.get("request_delay", 1.0))),
        "creator_patterns": patterns,
        "keep_query": bool(raw.get("keep_query", False)),
        "video_key_attr": key_attr,
        "video_url_template": key_tpl,
        "scope_selector": scope,
        "exclude_selector": exclude,
        "views_selector": views_sel,
        "sections": sections,
        "not_found_text": [clean(x) for x in nf],
        "avatar_selector": avatar_sel,
        "avatar_attr": avatar_attr,
    })
    return base


def api_save_profile(body):
    prof = validate_profile(body.get("profile") or {})
    pid = (body.get("profile") or {}).get("id")
    with LOCK:
        profiles = load_profiles()
        if pid and pid != SCRIPT_ID and any(p["id"] == pid for p in profiles):
            prof["id"] = pid
            profiles = [prof if p["id"] == pid else p for p in profiles]
        else:
            base_id = re.sub(r"[^a-z0-9]+", "_", prof["name"].lower()).strip("_") or "site"
            new_id, n = base_id, 2
            existing = {p["id"] for p in profiles} | {SCRIPT_ID}
            while new_id in existing:
                new_id, n = "%s_%d" % (base_id, n), n + 1
            prof["id"] = new_id
            profiles.append(prof)
        write_json(PROFILES_FILE, profiles)
    return {"id": prof["id"]}


def api_delete_profile(body):
    pid = body.get("id")
    with LOCK:
        if any(s["profile"] == pid for c in load_creators() for s in c["sources"]):
            raise ValueError("Creators still use this site. Remove them first.")
        write_json(PROFILES_FILE, [p for p in load_profiles() if p["id"] != pid])
    return {"ok": True}


_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
_URL_RE = re.compile(r"""https?://[^\s"'“”„‟‘’`<>\[\]{}|\\^]+""", re.I)
_BARE_RE = re.compile(r"""(?<![\w/@.:-])((?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+/[^\s"'“”„‟‘’`<>\[\]{}|\\^,;]*)""", re.I)


def clean_text(text):
    """Remove zero-width characters, turn non-breaking spaces into spaces, trim."""
    return str(text).translate(_INVISIBLE).replace(" ", " ").strip()


def extract_urls(text):
    """Pull every link out of messy text: quotes, leading spaces, bullets, commas, several per line.
    Links without http(s):// (e.g. 'www.site.com/x/') get https:// added."""
    text = clean_text(text)
    found = _URL_RE.findall(text)
    if not found:
        found = ["https://" + m for m in _BARE_RE.findall(text)]
    out = []
    for u in found:
        u = u.rstrip(".,;:!?)")  # punctuation that sticks to the end when pasted from text
        if u and u not in out:
            out.append(u)
    return out


def api_test_profile(body):
    prof = validate_profile(body.get("profile") or {})
    if body.get("name"):
        name = clean_text(body["name"]).strip("\"'“”‘’").strip()
        if not name:
            raise ValueError("Enter a name to look for")
        tmp = DATA / "_test_profile.json"
        write_json(tmp, prof)
        try:
            r = subprocess.run([sys.executable, "-u", str(UI_DIR / "scraper.py"), "--profile-file", str(tmp), "--find-name", name],
                               capture_output=True, encoding="utf-8", errors="replace", timeout=180,
                               env=dict(os.environ, **CHILD_ENV))
            return {"output": (r.stdout + r.stderr).strip()}
        except subprocess.TimeoutExpired:
            return {"output": "Timed out after 3 minutes."}
    urls = extract_urls(body.get("url", ""))
    if not urls:
        raise ValueError("Enter a creator page URL to test")
    url = urls[0]
    tmp = DATA / "_test_profile.json"
    write_json(tmp, prof)
    try:
        r = subprocess.run([sys.executable, "-u", str(UI_DIR / "scraper.py"), "--profile-file", str(tmp), "--test", url],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=60,
                           env=dict(os.environ, **CHILD_ENV))
        out = (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        out = "Timed out after 60s."
    return {"output": out}


def profile_keyword_info(p):
    return {"keywords": p.get("keywords") or {}, "negative": p.get("negative") or [], "dominant": p.get("dominant") or ""}


# ───────────────────────── durations & buckets ─────────────────────────

def parse_dur(text):
    m = re.match(r"^(?:(\d+):)?(\d+):(\d{2})$", text.strip())   # m:ss or h:mm:ss
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def fmt_dur(secs):
    if secs is None:
        return "??"
    return "%d:%02d" % (secs // 60, secs % 60)


def bucket_labels(edges):
    labels = ["under_%dmin" % edges[0]]
    for a, b in zip(edges, edges[1:]):
        labels.append("%d_to_%dmin" % (a, b))
    labels.append("%dmin_plus" % edges[-1])
    labels.append("unknown_duration")
    return labels


def bucket_of(secs, edges, labels):
    if secs is None:
        return labels[-1]
    for i, e in enumerate(edges):
        if secs <= e * 60:          # 11:00 is still in the band that ends at 11; the next band starts at 11:01
            return labels[i]
    return labels[len(edges)]


# ───────────────────────── creators / library ─────────────────────────

def links_file(slug):
    return LINKS / ("%s_links.txt" % slug)


AVATAR_EXTS = (".jpg", ".png", ".webp", ".gif", ".avif")


def avatar_path(slug):
    for ext in AVATAR_EXTS:
        f = AVATARS / (slug + ext)
        if f.exists():
            return f
    return None


def drop_avatar(slug):
    for ext in AVATAR_EXTS:
        try:
            (AVATARS / (slug + ext)).unlink()
        except OSError:
            pass


def pending_avatar_path(slug):
    for ext in AVATAR_EXTS:
        f = AVATARS / ("__pending__" + slug + ext)
        if f.exists():
            return f
    return None


def drop_pending_avatar(slug):
    for ext in AVATAR_EXTS:
        try:
            (AVATARS / ("__pending__" + slug + ext)).unlink()
        except OSError:
            pass


def _same_bytes(a, b):
    try:
        return hashlib.sha1(a.read_bytes()).digest() == hashlib.sha1(b.read_bytes()).digest()
    except OSError:
        return False


def take_avatar(slug, pid, work, say=None):
    """A scrape may have saved the creator's picture in its work folder.
    - no picture yet, or the picture came from this same site: it is saved (a re-scrape refreshes it)
    - the picture came from another site and this one is different: it waits as a choice for you on the Creators tab."""
    new = next(iter(sorted(work.glob("*_avatar.*"))), None)
    if not new or new.suffix.lower() not in AVATAR_EXTS:
        return False
    AVATARS.mkdir(parents=True, exist_ok=True)
    with LOCK:
        creators = load_creators()
        c = next((x for x in creators if x["slug"] == slug), None)
        if not c:
            return False
        cur = avatar_path(slug)
        source_site = c.get("avatar_site") or (c["sources"][0]["profile"] if c["sources"] else None)
        if not cur or source_site == pid:
            drop_avatar(slug)
            drop_pending_avatar(slug)
            shutil.move(str(new), str(AVATARS / (slug + new.suffix.lower())))
            c["avatar_site"] = pid
            c.pop("avatar_pending", None)
            save_creators(creators)
            return True
        if _same_bytes(cur, new):
            return False                                   # the other site has the very same picture
        drop_pending_avatar(slug)
        shutil.move(str(new), str(AVATARS / ("__pending__" + slug + new.suffix.lower())))
        c["avatar_pending"] = {"profile": pid}
        save_creators(creators)
        if say:
            say("The %s picture for %s is different from the one you have. Choose which to keep on the Creators tab." % (get_profile(pid)["name"], slug))
    return False


def api_avatar_choice(body):
    slug, choice = body.get("slug", ""), body.get("choice", "")
    with LOCK:
        creators = load_creators()
        c = next((x for x in creators if x["slug"] == slug), None)
        pend = pending_avatar_path(slug)
        if not c or not pend or not c.get("avatar_pending"):
            raise ValueError("There is no picture waiting for a choice")
        if choice == "new":
            drop_avatar(slug)
            shutil.move(str(pend), str(AVATARS / (slug + pend.suffix.lower().replace("__pending__", ""))))
            c["avatar_site"] = c["avatar_pending"]["profile"]
        elif choice == "current":
            drop_pending_avatar(slug)
        else:
            raise ValueError("choice must be 'current' or 'new'")
        c.pop("avatar_pending", None)
        save_creators(creators)
    return {"ok": True}


SITE_MARK = "# site:"   # starts a section of the combined file: "# site: <site id>  (<name>, n videos)"


def site_order():
    """Sites in the order of the Sites tab. A creator's file always lists sites in this order."""
    return [p["id"] for p in all_profiles()]


def read_sections(path, default_pid):
    """-> {site id: [raw link lines]}. A file written before sections existed belongs to default_pid."""
    sections, cur, in_all = {}, default_pid, False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return sections
    for line in lines:
        if line.startswith("=== ALL LINKS"):
            in_all = True
            continue
        if line.startswith("=== CATEGORISED"):
            break
        if not in_all:
            continue
        if line.startswith(SITE_MARK):
            cur = line[len(SITE_MARK):].strip().split(" ")[0] or default_pid
            sections.setdefault(cur, [])
        elif line.startswith("http"):
            sections.setdefault(cur, []).append(line)
    return sections


def write_sections(path, sections):
    order = site_order()
    names = {p["id"]: p["name"] for p in all_profiles()}
    pids = [p for p in order if sections.get(p)] + [p for p in sections if p not in order and sections[p]]
    lines = ["=== ALL LINKS (%d) ===" % sum(len(sections[p]) for p in pids)]
    for pid in pids:
        lines.append("%s %s  (%s, %d videos)" % (SITE_MARK, pid, names.get(pid, pid), len(sections[pid])))
        lines += sections[pid]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_VIEWS_TAIL = re.compile(r"\s*@@views=(\d+)\s*$")


def parse_link_line(line):
    """'url | 12:34 | title @@views=123' -> (url, seconds or None, title, views or None). The views part is optional."""
    views = None
    m = _VIEWS_TAIL.search(line)
    if m:
        views, line = int(m.group(1)), line[:m.start()]
    parts = [x.strip() for x in line.split("|", 2)]
    return parts[0], (parse_dur(parts[1]) if len(parts) > 1 else None), (parts[2] if len(parts) > 2 else ""), views


def parse_links_file(path, default_pid=SCRIPT_ID):
    """-> [(url, seconds_or_None, title, site id, views_or_None)] in file order"""
    out = []
    for pid, lines in read_sections(path, default_pid).items():
        for l in lines:
            url, secs, title, views = parse_link_line(l)
            out.append((url, secs, title, pid, views))
    return out


def default_pid_for(creator):
    return creator.get("legacy_pid") or creator["profile"]


def limit_seconds(s):
    """-> (shortest, longest) allowed length in seconds; None = no limit"""
    def one(k):
        v = str(s.get(k, "")).strip()
        try:
            return float(v) * 60 if v else None
        except ValueError:
            return None
    return one("min_video_minutes"), one("max_video_minutes")


def merge_source(slug, pid, part_path):
    """Put one site's freshly scraped links into the creator's file. Other sites' links are left alone,
    and the sections stay in site order no matter which site was scraped first."""
    with LOCK:
        creator = next((c for c in load_creators() if c["slug"] == slug), None)
        if not creator:
            return 0
        f = links_file(slug)
        sections = read_sections(f, default_pid_for(creator))
        new = list(dict.fromkeys(read_sections(part_path, pid).get(pid, [])))
        lo, hi = limit_seconds(load_settings())
        kept = []
        for line in new:                       # a video with no known length can't be judged, so it stays
            secs = parse_link_line(line)[1]
            if secs is not None and ((lo is not None and secs < lo) or (hi is not None and secs > hi)):
                continue
            kept.append(line)
        sections[pid] = kept
        write_sections(f, sections)
        return len(kept), len(new) - len(kept)


def normalize_creator(c):
    """Every creator has a list of sources (one per site). Older entries had a single url/profile."""
    srcs = c.get("sources")
    if not srcs:
        src = {"url": c["url"], "profile": c.get("profile", SCRIPT_ID), "added": c.get("added", 0)}
        if c.get("all_pages"):
            src["all_pages"] = True
        srcs = [src]
        c = dict(c, legacy_pid=src["profile"])   # their existing file has no site sections yet
    order = site_order()
    srcs = sorted(srcs, key=lambda s: order.index(s["profile"]) if s["profile"] in order else 999)
    c = dict(c, sources=srcs, url=srcs[0]["url"], profile=srcs[0]["profile"])   # top level mirrors the first site
    if srcs[0].get("all_pages"):
        c["all_pages"] = True
    else:
        c.pop("all_pages", None)
    return c


def load_creators():
    return [normalize_creator(c) for c in read_json(CREATORS_FILE, [])]


def save_creators(creators):
    write_json(CREATORS_FILE, [normalize_creator(c) for c in creators])


def creator_rows():
    rows = []
    for c in load_creators():
        f = links_file(c["slug"])
        items = parse_links_file(f, default_pid_for(c)) if f.exists() else None
        counts = {}
        for it in items or []:
            counts[it[3]] = counts.get(it[3], 0) + 1
        sources = [dict(s, count=counts.get(s["profile"], 0), site=get_profile(s["profile"])["name"]) for s in c["sources"]]
        av = avatar_path(c["slug"])
        rows.append(dict(c, sources=sources, folder=folder_for(c), display=c.get("display_name") or c["slug"],
                         folder_custom=bool(c.get("folder_override")),
                         avatar_site_name=get_profile(c["avatar_site"])["name"] if c.get("avatar_site") else None,
                         avatar_pending=(("/avatars/%s?v=%d" % (pp.name, int(pp.stat().st_mtime))) if (pp := pending_avatar_path(c["slug"])) and c.get("avatar_pending") else None),
                         avatar_pending_site=get_profile(c["avatar_pending"]["profile"])["name"] if c.get("avatar_pending") else None,
                         avatar=("/avatars/%s?v=%d" % (av.name, int(av.stat().st_mtime))) if av else None,
                         count=None if items is None else len(items),
                         last_scraped=int(f.stat().st_mtime) if items is not None else None))
    return rows


def folder_for(creator):
    """Library folder for a creator: the name in their link, endings removed, hyphens kept.
    https://site/video-creators/jane-doe-exclusive-videos/  ->  jane-doe
    A creator imported from a file has no link yet, so it uses the folder name chosen at import."""
    if creator.get("folder_override"):          # you renamed it by hand
        return creator["folder_override"]
    for src in creator["sources"]:
        if not src.get("url"):
            continue
        if src["profile"] == SCRIPT_ID:
            prof = {"slug_strip": list(profile_scraper.DEFAULT_PROFILE["slug_strip"])}  # same endings your script strips
        else:
            prof = get_profile(src["profile"])
        name = profile_scraper.slug_from_url(src["url"], prof, separator="-")
        if name and name != "unknown":
            return name
    return creator.get("folder_name") or creator["slug"].replace("_", "-")


def ensure_folder(creator, say=None):
    """Create the creator's folder in the download library (if it isn't there), so downloads have a place to go."""
    try:
        d = Path(load_settings()["library_dir"]).expanduser() / folder_for(creator)
        if d.is_dir():
            return False
        d.mkdir(parents=True, exist_ok=True)
        if say:
            say("Created folder %s" % d)
        return True
    except Exception as e:
        if say:
            say("(couldn't create the library folder: %s)" % e)
        return False


def api_make_folders(body):
    """Create the library folder of every creator that doesn't have one yet."""
    made = [folder_for(c) for c in load_creators() if ensure_folder(c)]
    return {"created": made, "count": len(made)}


def build_library():
    s = load_settings()
    edges = s["bucket_edges_min"]
    labels = bucket_labels(edges)
    profiles = {p["id"]: profile_keyword_info(p) for p in all_profiles()}
    # category list: every profile's categories (in order), then Other
    cats = []
    for p in all_profiles():
        for c in (p.get("keywords") or {}):
            if c not in cats:
                cats.append(c)
    cats.append("Other")
    records = []
    seen = set()
    for c in load_creators():
        f = links_file(c["slug"])
        if not f.exists():
            continue
        folder = folder_for(c)
        for url, secs, title, site, views in parse_links_file(f, default_pid_for(c)):
            if url in seen:
                continue
            seen.add(url)
            kw = profiles.get(site) or profiles[SCRIPT_ID]
            records.append({
                "url": url,
                "creator": c["slug"],
                "folder": folder,
                "site": site,
                "secs": secs,
                "title": title,
                "views": views,
                "category": categorise(url + " " + title, kw),
                "bucket": bucket_of(secs, edges, labels),
            })
    return records, labels, {"categories": cats}


def select_records(params):
    records, labels, _ = build_library()
    cat = params.get("category") or ""
    bucket = params.get("bucket") or ""
    creator = params.get("creator") or ""
    pool = [r for r in records
            if (not cat or r["category"] == cat)
            and (not bucket or r["bucket"] == bucket)
            and (not creator or r["creator"] == creator)]
    if params.get("exclude_downloaded") in ("1", 1, True, "true"):
        done = set(read_json(DOWNLOADED_FILE, []))
        pool = [r for r in pool if r["url"] not in done]
    return pool


# ───────────────────────── jobs ─────────────────────────

class Job:
    def __init__(self, kind, title):
        self.id = int(time.time() * 1000)
        self.kind = kind
        self.title = title
        self.status = "running"
        self.log = []
        self.results = []
        self.started = time.time()
        self.finished = None
        self.proc = None
        self.stop_flag = False
        self.accepting = False   # scrape jobs: True while new creators may still be queued
        self.current = None
        self.items = {}          # download jobs: url -> what each download is doing (for the progress panel)
        self.target = None

    def event(self, fields):
        """A progress event from the downloader: TARGET n | START url folder | PROG url pct mb | DONE url file | FAIL url reason"""
        kind = fields[0] if fields else ""
        with LOCK:
            if kind == "TARGET" and len(fields) > 1:
                try:
                    self.target = int(fields[1])
                except ValueError:
                    pass
                return
            if len(fields) < 2:
                return
            url = fields[1]
            it = self.items.get(url)
            if it is None:
                it = self.items[url] = {"url": url, "folder": "", "status": "downloading", "pct": None, "mb": 0.0,
                                        "file": "", "reason": "", "t0": time.time(), "t1": None}
            if kind == "START":
                it.update(folder=fields[2] if len(fields) > 2 else it["folder"], status="downloading", t0=time.time())
            elif kind == "PROG" and it["status"] == "downloading":
                try:
                    pct = float(fields[2])
                    it["pct"] = None if pct < 0 else pct
                    it["mb"] = float(fields[3]) if len(fields) > 3 else it["mb"]
                except ValueError:
                    pass
            elif kind == "DONE":
                it.update(status="done", pct=100.0, file=fields[2] if len(fields) > 2 else "", t1=time.time())
            elif kind == "FAIL":
                it.update(status="failed", reason=fields[2] if len(fields) > 2 else "", t1=time.time())

    def say(self, line):
        with LOCK:
            self.log.append(line)
            if len(self.log) > 5000:
                del self.log[:1000]

    def summary(self):
        return {
            "id": self.id, "kind": self.kind, "title": self.title,
            "status": self.status, "results": self.results,
            "started": self.started, "finished": self.finished,
            "nlines": len(self.log),
        }


CURRENT = {"job": None}


def active_job():
    j = CURRENT["job"]
    return j if j and j.status == "running" else None


def start_job(kind, title, target):
    with LOCK:
        if active_job():
            raise RuntimeError("Another job is already running")
        job = Job(kind, title)
        CURRENT["job"] = job

    def runner():
        try:
            target(job)
            if job.status == "running":
                job.status = "stopped" if job.stop_flag else "done"
        except Exception as e:
            job.say("ERROR: %s" % e)
            job.status = "failed"
        finally:
            job.finished = time.time()

    threading.Thread(target=runner, daemon=True).start()
    return job


def stream_process(job, cmd, cwd, on_line=None):
    env = dict(os.environ, **CHILD_ENV)
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding="utf-8", errors="replace", env=env, bufsize=1)
    job.proc = proc
    for line in proc.stdout:
        line = line.rstrip("\n")
        if on_line and on_line(line) is True:
            continue                      # the callback handled it (e.g. a progress event): keep it out of the log
        job.say(line)
    proc.wait()
    job.proc = None
    return proc.returncode


def interruptible_sleep(job, seconds):
    end = time.time() + seconds
    while time.time() < end and not job.stop_flag:
        time.sleep(0.2)


def scrape_command(profile_id, url, slug=None, all_pages=False):
    """Command that scrapes one creator URL with the right engine."""
    if profile_id == SCRIPT_ID:
        info, _ = script_info()
        if not info["exists"]:
            raise RuntimeError("Scraper script not found: %s" % info["path"])
        return [sys.executable, "-u", info["path"], url]
    prof = next((p for p in load_profiles() if p["id"] == profile_id), None)
    if not prof:
        raise RuntimeError("Site profile '%s' no longer exists" % profile_id)
    pfile = PROFILE_DIR / ("%s.json" % profile_id)
    write_json(pfile, prof)
    cmd = [sys.executable, "-u", str(UI_DIR / "scraper.py"), "--profile-file", str(pfile)]
    if slug:
        cmd += ["--slug", slug]  # the output file must match the creator's name in the table
    if all_pages:
        cmd += ["--all-pages"]   # keep going until a page has nothing new
    return cmd + [url]


# Work waiting for the single background job, in order. Two kinds of item:
#   {"kind": "scrape", "key": slug, "url", "slug", "pid"}
#   {"kind": "find",   "key": slug, "name", "pid", "pages", "scrape"}   (look a creator up by name)
SCRAPE_QUEUE = []


def run_scrape_item(job, s, url, slug, pid, all_pages=False):
    """Scrape one site's page for one creator, then merge it into the creator's file as that site's section."""
    work = LINKS / "_work" / re.sub(r"[^A-Za-z0-9_.@-]", "_", "%s@%s" % (slug, pid))
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    found = {"n": None}

    def on_line(line):
        m = re.search(r"Total unique videos found:\s*(\d+)", line)
        if m:
            found["n"] = int(m.group(1))

    try:
        code = stream_process(job, scrape_command(pid, url, slug, all_pages), work, on_line)
        if job.stop_flag:
            return False
        ok = code == 0 and bool(found["n"])
        parts = sorted(work.glob("*_links.txt"))
        if ok and parts:
            n, dropped = merge_source(slug, pid, parts[0])
            if dropped:
                lo, hi = limit_seconds(load_settings())
                job.say("Skipped %d video%s outside your length limits (%s)" % (dropped, "" if dropped == 1 else "s",
                        " to ".join(x for x in (("from %g min" % (lo / 60)) if lo is not None else "", ("up to %g min" % (hi / 60)) if hi is not None else "") if x)))
            if take_avatar(slug, pid, work, job.say):
                job.say("Saved the profile picture for %s" % slug)
            cr = next((c for c in load_creators() if c["slug"] == slug), None)
            if cr:
                ensure_folder(cr, job.say)
            job.say("Saved %d videos as the %s section of %s" % (n, get_profile(pid)["name"], links_file(slug).name))
        else:
            ok = False
    finally:
        shutil.rmtree(work, ignore_errors=True)
    job.results.append({"slug": slug, "ok": ok, "count": found["n"]})
    if not ok:
        job.say("✗ %s (%s): nothing new saved, so what was there before is kept (blocked, wrong URL, or page structure differs)"
                % (slug, get_profile(pid)["name"]))
    return True


def run_find_item(job, s, item):
    name, pid = item["name"], item["pid"]
    slug = profile_scraper.creator_slug_from_name(name)
    profile = get_profile(pid)
    patterns = profile.get("creator_patterns") or []
    job.say("Looking for \"%s\" - trying %d address%s, stopping at the first that works" %
            (name, len(patterns), "" if len(patterns) == 1 else "es"))
    hit = profile_scraper.find_creator(profile, name, job.say, lambda: job.stop_flag)
    if job.stop_flag:
        return False
    if not hit:
        job.say("✗ Couldn't find \"%s\". None of the %d addresses worked." % (name, len(patterns)))
        job.results.append({"slug": slug, "ok": False, "count": None})
        return True
    url, n = hit
    all_pages = bool(item.get("all_pages"))
    if item.get("pages") and not all_pages:
        url = profile_scraper.with_pages(url, item["pages"], profile)
    source = {"url": url, "profile": pid, "added": int(time.time()), **({"all_pages": True} if all_pages else {})}
    with LOCK:
        creators = load_creators()
        same = next((c for c in creators if c["slug"] == (item.get("target") or slug)), None)
        if not same:
            m = match_existing(slug, creators, pid)
            if m and m[2] == "auto":
                same = m[0]
                remember_alias(same, slug)
                job.say("(\"%s\" matches %s, so this site is added to that creator)" % (name, same["slug"]))
            elif m:
                job.say("(note: \"%s\" looks like %s; added separately. Use Link on the Creators tab to merge them)" % (name, m[0]["slug"]))
        if same:
            slug = same["slug"]          # always scrape into the creator it joined
        placeholder = next((x for x in same["sources"] if x["profile"] == pid and not x.get("url")), None) if same else None
        if same and not placeholder and any(x["profile"] == pid for x in same["sources"]):
            job.say("(%s is already in your list from this site; use Re-scrape to refresh it)" % slug)
            return True
        if placeholder:
            placeholder.update(url=url, added=int(time.time()), **({"all_pages": True} if all_pages else {}))
            placeholder.pop("imported", None)
            job.say("✓ Found %s -> %s  (this completes the file you imported for %s)" % (name, url, slug))
        elif same:
            same["sources"].append(source)
            slug = same["slug"]      # scrape into the creator it joined, not the typed name
            job.say("✓ Found %s -> %s  (added as another site for %s)" % (name, url, slug))
        else:
            creators.append({"slug": slug, "name": name, "added": int(time.time()), "sources": [source]})
            job.say("✓ Found %s -> %s" % (name, url))
        save_creators(creators)
    if item.get("scrape"):
        job.say("")
        job.say("Scraping %s…" % slug)
        return run_scrape_item(job, s, url, slug, pid, all_pages)
    job.results.append({"slug": slug, "ok": True, "count": n})
    return True


def scrape_target(job):
    s = load_settings()
    done = 0
    job.accepting = True
    try:
        while True:
            with LOCK:
                if job.stop_flag or not SCRAPE_QUEUE:
                    job.accepting = False
                    break
                item = SCRAPE_QUEUE.pop(0)
                job.current = item["key"]
                position, total = done + 1, done + 1 + len(SCRAPE_QUEUE)
            label = item["name"] if item["kind"] == "find" else item["slug"]
            job.say("")
            job.say("═══ [%d/%d] %s (%s) ═══" % (position, total, label, get_profile(item["pid"])["name"]))
            if item["kind"] == "find":
                completed = run_find_item(job, s, item)
            else:
                completed = run_scrape_item(job, s, item["url"], item["slug"], item["pid"], item.get("all_pages", False))
            if not completed:
                break
            done += 1
            if SCRAPE_QUEUE:
                interruptible_sleep(job, s["scrape_pause"])
    finally:
        with LOCK:
            job.accepting = False
            job.current = None
            SCRAPE_QUEUE.clear()
    okc = sum(1 for r in job.results if r["ok"])
    job.say("")
    job.say("Finished: %d of %d succeeded" % (okc, done))


def enqueue(items):
    """Run these in the background, one at a time. If a scrape job is already going they join its queue."""
    with LOCK:
        running = active_job()
        if running and running.kind == "scrape" and running.accepting:
            waiting = {i["key"] for i in SCRAPE_QUEUE} | {running.current}
            fresh = [i for i in items if i["key"] not in waiting]
            SCRAPE_QUEUE.extend(fresh)
            if fresh:
                running.say("+ queued: %s" % ", ".join(i.get("name") or i["slug"] for i in fresh))
            return dict(running.summary(), queued=len(fresh))
        if running:
            raise RuntimeError("Another job is already running")
        SCRAPE_QUEUE[:] = items
    try:
        job = start_job("scrape", "Scraping creators", scrape_target)
    except Exception:
        SCRAPE_QUEUE.clear()
        raise
    return dict(job.summary(), queued=len(items))


def download_target(job):
    s = load_settings()
    if s.get("download_method") == "ytdlp":
        job.say("Starting downloader (yt-dlp).")
    else:
        job.say("Starting downloader. Keep Chrome open & maximised and don't touch the mouse.")

    def on_line(line):
        if line.startswith("@@EV\t"):
            job.event(line.split("\t")[1:])
            return True
        if line.startswith("@@OK "):
            url = line[5:].strip()
            with LOCK:
                done = read_json(DOWNLOADED_FILE, [])
                if url not in done:
                    done.append(url)
                    write_json(DOWNLOADED_FILE, done)

    stream_process(job, [sys.executable, "-u", str(UI_DIR / "downloader.py"), str(RUN_CONFIG)], UI_DIR, on_line)


def capture_target(job):
    if job.kind.endswith("_image"):
        name = job.kind[len("capture:"):-len("_image")]
        TEMPLATES.mkdir(parents=True, exist_ok=True)
        stream_process(job, [sys.executable, "-u", str(UI_DIR / "downloader.py"), "--shot", name, str(TEMPLATES / (name + ".png"))], UI_DIR)
    else:
        stream_process(job, [sys.executable, "-u", str(UI_DIR / "downloader.py"), "--pos"], UI_DIR)


# ───────────────────────── API handlers ─────────────────────────

def api_state():
    info, _ = script_info()
    job = CURRENT["job"]
    return {
        "script": info,
        "settings": load_settings(),
        "templates": {n: int((TEMPLATES / (n + ".png")).stat().st_mtime) for n in ("vdh_icon", "download_button")
                      if (TEMPLATES / (n + ".png")).exists()},
        "creators": creator_rows(),
        "running_version": STARTED_WITH,       # the code this server was started with
        "disk_version": code_fingerprint(),    # the code on disk now; different = restart needed
        "links_dir": str(LINKS),
        "profiles": all_profiles(),
        "defaults": profile_scraper.DEFAULT_PROFILE,
        "job": job.summary() if job else None,
    }


# ───────────────────────── matching the same person across sites ─────────────────────────

def _norm_name(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def name_similarity(a, b):
    """-> (share, shorter length). Share = longest unbroken run of letters the two names have in common,
    divided by the shorter name (hyphens/underscores/case ignored). 'janedoe' in 'liljanedoe' = 1.0.
    Order matters, so anagrams like 'dan-lee' don't match."""
    a, b = _norm_name(a), _norm_name(b)
    if not a or not b:
        return 0.0, 0
    short = min(len(a), len(b))
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size / short, short


def match_existing(name, creators, pid, s=None):
    """Is this name probably someone already in the list? -> (creator, share, "auto" | "ask") or None.
    A creator who already has an address on this site is never a candidate: two people can't share one site."""
    s = s or load_settings()
    if not s.get("name_match", True):
        return None
    min_len, ask = int(s["name_match_min_len"]), float(s["name_match_ask_pct"]) / 100.0
    best = None
    for c in creators:
        if any(x["profile"] == pid and x.get("url") for x in c["sources"]):
            continue
        for known in [c["slug"], folder_for(c)] + list(c.get("aliases") or []):
            share, short = name_similarity(name, known)
            if short < 4 or share < ask:
                continue
            kind = "auto" if share >= 1.0 and short >= min_len else "ask"
            rank = (kind == "auto", share, short)
            if not best or rank > best[0]:
                best = (rank, c, share, kind)
    return (best[1], best[2], best[3]) if best else None


def remember_alias(creator, slug):
    if slug and slug != creator["slug"] and slug not in (creator.get("aliases") or []):
        creator.setdefault("aliases", []).append(slug)


def auto_all_pages(url, pid):
    """True when this address should be walked page by page until the site runs out: the setting is on, it's a
    site from the Sites tab, and the address doesn't already say how many pages (like /6/ or &page=9)."""
    if pid == SCRIPT_ID or not load_settings().get("pages_default_all", True):
        return False
    try:
        return not profile_scraper._parse(url, profile_scraper.with_defaults(get_profile(pid)))[3]
    except Exception:
        return False


def source_slug(src):
    if src["profile"] == SCRIPT_ID:
        return script_info()[1](src["url"])
    return profile_scraper.slug_from_url(src["url"], get_profile(src["profile"]))


def domain_of(url):
    n = urlparse(url).netloc.lower()
    return n[4:] if n.startswith("www.") else n


def api_add_creators(body):
    """Add creators from pasted links and/or plain names, and (optionally) start scraping them.

    A line holding a link is added as is. A line with no link is treated as a person's name and looked up
    with the site's "creator addresses to try" (custom sites only). A creator who already exists is not
    duplicated: a second site simply becomes another source of the same creator and the same file."""
    pid = body.get("profile") or SCRIPT_ID
    profile = get_profile(pid)
    if pid == SCRIPT_ID:
        info, slug_fn = script_info()
        site_domain = info["domain"]
        patterns = []
    else:
        slug_fn = lambda u: profile_scraper.slug_from_url(u, profile)
        site_domain = urlparse(profile["base_url"]).netloc
        patterns = [x for x in (profile.get("creator_patterns") or []) if x.strip()]
    raw = body.get("urls", "")
    lines = raw.splitlines() if isinstance(raw, str) else [str(x) for x in raw]
    pages = body.get("pages")
    all_pages = str(pages or "").strip().lower() in ("all", "a", "*", "every", "max")
    try:
        pages = None if all_pages else (int(pages) if pages not in (None, "", 0, "0") else None)
    except Exception:
        pages = None
    notes = []
    if all_pages and pid == SCRIPT_ID:
        all_pages = False
        notes.append("'all' pages needs a site added in the Sites tab. Your own script always uses the number in the link.")
    scrape = body.get("scrape", True)
    with LOCK:
        creators = load_creators()
        by_slug = {c["slug"]: c for c in creators}

        def has_site(slug):
            """True when this creator already has an address for this site (an imported file without one doesn't count)"""
            return slug in by_slug and any(x["profile"] == pid and x.get("url") for x in by_slug[slug]["sources"])

        added, joined, attached, skipped, warnings, names, to_scrape = [], [], [], [], [], [], []
        linked, suggestions = [], []
        link_map = body.get("link_map") or {}      # {pasted link: existing creator, or "" for "keep as a new creator"}
        settings = load_settings()
        found_urls = []
        for line in lines:
            got = extract_urls(line)
            if got:
                found_urls.extend(got)
                continue
            text = clean_text(line).lstrip("-*•> \t").strip().strip("\"'“”‘’`").strip()
            if not text:
                continue
            nslug = profile_scraper.creator_slug_from_name(text)
            if not patterns:
                skipped.append({"url": text[:80], "reason": "no link found (to add by name, give this site addresses to try in the Sites tab)"})
            elif not nslug or len(text) > 80:
                skipped.append({"url": text[:80], "reason": "not a usable name"})
            elif has_site(nslug) or any(n[1] == nslug for n in names):
                skipped.append({"url": text, "reason": "already added from this site (%s)" % nslug})
            else:
                names.append((text, nslug))
        for orig in found_urls:
            u = orig
            if pages and pid != SCRIPT_ID:
                u = profile_scraper.with_pages(u, pages, profile)
            elif pages:  # your script always uses a trailing /N/
                p = urlparse(u)
                path = p.path.rstrip("/")
                if not re.search(r"/\d+$", path):
                    u = p._replace(path=path + "/%d/" % pages).geturl()
            slug = slug_fn(u)
            if has_site(slug):
                skipped.append({"url": u, "reason": "already added from this site (%s)" % slug})
                continue
            if slug not in by_slug:
                target, how, share = None, None, 0
                if orig in link_map:                       # you decided
                    target = link_map[orig] or None
                    how = "you"
                    if target and (target not in by_slug or has_site(target)):
                        skipped.append({"url": u, "reason": "can't link to %s (missing, or it already has this site)" % target})
                        continue
                else:
                    m = match_existing(slug, list(by_slug.values()), pid, settings)
                    if m and m[2] == "auto":
                        target, how, share = m[0]["slug"], "auto", m[1]
                    elif m:
                        suggestions.append({"url": orig, "slug": slug, "candidate": m[0]["slug"], "pct": int(round(m[1] * 100))})
                        continue
                if target:
                    src = {"url": u, "profile": pid, "added": int(time.time()), **({"all_pages": True} if all_pages else {})}
                    by_slug[target]["sources"].append(src)
                    remember_alias(by_slug[target], slug)
                    linked.append({"slug": slug, "to": target, "how": how, "pct": int(round(share * 100))})
                    to_scrape.append((target, u, all_pages or (pages is None and auto_all_pages(u, pid))))
                    continue
            if site_domain and domain_of(u) != domain_of("http://" + site_domain):
                warnings.append("%s is not on %s; page URLs will be rebuilt on %s regardless."
                                % (slug, site_domain, site_domain))
            source = {"url": u, "profile": pid, "added": int(time.time()), **({"all_pages": True} if all_pages else {})}
            placeholder = next((x for x in by_slug[slug]["sources"] if x["profile"] == pid and not x.get("url")), None) if slug in by_slug else None
            if placeholder:                      # an imported file: give it its address, keep the links it has
                placeholder.update(url=u, **{k: v for k, v in source.items() if k in ("added", "all_pages")})
                placeholder.pop("imported", None)
                attached.append(slug)
            elif slug in by_slug:
                by_slug[slug]["sources"].append(source)
                joined.append(slug)
            else:
                c = {"slug": slug, "added": int(time.time()), "sources": [source]}
                creators.append(c)
                by_slug[slug] = c
                added.append(slug)
            to_scrape.append((slug, u, all_pages or (pages is None and auto_all_pages(u, pid))))
        save_creators(creators)
        for slug_ in {t[0] for t in to_scrape}:
            cr = next((c for c in creators if c["slug"] == slug_), None)
            if cr:
                ensure_folder(normalize_creator(cr))

    items = []
    if scrape:
        items += [{"kind": "scrape", "key": "%s@%s" % (s, pid), "url": u, "slug": s, "pid": pid, "all_pages": ap}
                  for s, u, ap in to_scrape]
    items += [{"kind": "find", "key": "%s@%s" % (nslug, pid), "name": text, "pid": pid, "pages": pages,
               "all_pages": all_pages or (pages is None and pid != SCRIPT_ID and settings.get("pages_default_all", True)),
               "scrape": bool(scrape)} for text, nslug in names]
    job = enqueue(items) if items else None
    return {"added": added, "joined": joined, "attached": attached, "linked": linked, "suggestions": suggestions,
            "finding": [n[0] for n in names], "skipped": skipped, "warnings": warnings + notes, "job": job}


def api_import(body):
    """Register existing *_links.txt files as creators, filed under a chosen site (whose keywords then sort them).

    overwrite=True means "re-import": anything an earlier import created for the same name is replaced.
    Links you scraped yourself are never overwritten."""
    raw_folder = clean_text(body.get("folder") or "").strip("\"'“”‘’`").strip() or str(LINKS)   # tolerate quotes from "Copy as path"
    folder = Path(raw_folder).expanduser()
    if folder.is_file() and folder.name.endswith("_links.txt"):   # pasted a file instead of its folder: use the folder
        folder = folder.parent
    if not folder.is_dir():
        raise ValueError("That folder doesn't exist: %s" % folder)
    pid = body.get("site") or SCRIPT_ID
    if pid not in {p["id"] for p in all_profiles()}:
        raise ValueError("Unknown site")
    overwrite = bool(body.get("overwrite"))
    keep_underscores = bool(body.get("keep_underscores"))
    imported, replaced, skipped = [], [], []
    with LOCK:
        creators = load_creators()
        by_slug = {c["slug"]: c for c in creators}
        for f in sorted(folder.glob("*_links.txt")):
            slug = f.name[: -len("_links.txt")]
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", slug):
                skipped.append({"name": f.name, "reason": "unusual characters in the file name"})
                continue
            dest = links_file(slug)
            in_place = dest.exists() and f.resolve() == dest.resolve()
            c = by_slug.get(slug)
            folder_name = slug if keep_underscores else slug.replace("_", "-")
            if c and not overwrite:
                skipped.append({"name": f.name, "reason": "already in your list (tick 'Replace earlier imports' to redo it)"})
                continue
            if not c and dest.exists() and not in_place and not overwrite:
                skipped.append({"name": f.name, "reason": "a different file with that name is already in the links folder"})
                continue

            if c:   # ── re-import over an existing creator
                real = [s for s in c["sources"] if s.get("url")]
                if any(s["profile"] == pid for s in real):
                    skipped.append({"name": f.name, "reason": "you scraped this creator from that site, so it was left alone"})
                    continue
                imported_pids = {s["profile"] for s in c["sources"] if not s.get("url")}
                existing = read_sections(dest, default_pid_for(c)) if dest.exists() else {}
                if in_place:     # the file is the one already stored: re-file its imported links under the chosen site
                    moved = [l for q in existing if q in imported_pids for l in existing[q]]
                    new = {pid: moved} if moved else {}
                else:
                    new = read_sections(f, pid)
                count = sum(len(v) for v in new.values())
                if not count:
                    skipped.append({"name": f.name, "reason": "no links found in it"})
                    continue
                for q in imported_pids:
                    existing.pop(q, None)
                c["sources"] = real
                for q, lines in new.items():
                    if lines:
                        existing[q] = list(dict.fromkeys(lines))
                        if not any(s["profile"] == q for s in c["sources"]):
                            c["sources"].append({"url": "", "profile": q, "imported": True, "added": int(time.time())})
                c.update(legacy_pid=pid, folder_name=folder_name)
                write_sections(dest, existing)
                replaced.append({"slug": slug, "count": count})
                continue

            # ── a new creator
            new = read_sections(f, pid)                       # unmarked files belong to the chosen site
            count = sum(len(v) for v in new.values())
            if not count:
                skipped.append({"name": f.name, "reason": "no links found in it"})
                continue
            write_sections(dest, new)                         # saved in the UI's format (the old categorised part is dropped)
            sources = [{"url": "", "profile": q, "imported": True, "added": int(time.time())} for q in new if new[q]]
            c = {"slug": slug, "added": int(time.time()), "imported": True, "legacy_pid": pid,
                 "folder_name": folder_name, "sources": sources}
            creators.append(c)
            by_slug[slug] = c
            imported.append({"slug": slug, "count": count})
        save_creators(creators)
    return {"imported": imported, "replaced": replaced, "skipped": skipped, "folder": str(folder),
            "site": get_profile(pid)["name"]}


def api_remove_creator(body):
    slug = body.get("slug", "")
    with LOCK:
        save_creators([c for c in load_creators() if c["slug"] != slug])
        drop_avatar(slug)
        drop_pending_avatar(slug)
        f = links_file(slug)
        if body.get("delete_file", True) and f.exists() and f.parent == LINKS:
            f.unlink()
    return {"ok": True}


def api_unlink_source(body):
    """Undo a link: take one site out of a creator and make it a creator of its own, with its own file."""
    slug, pid = body.get("slug", ""), body.get("pid", "")
    with LOCK:
        creators = load_creators()
        c = next((x for x in creators if x["slug"] == slug), None)
        src = next((x for x in c["sources"] if x["profile"] == pid), None) if c else None
        if not src:
            raise ValueError("That site isn't part of this creator")
        if len(c["sources"]) < 2:
            raise ValueError("This is the creator's only site, so there is nothing to unlink")
        if not src.get("url"):
            raise ValueError("This one was imported from a file and has no address, so it can't be split out")
        new_slug = source_slug(src)
        if not new_slug or new_slug == "unknown" or any(x["slug"] == new_slug for x in creators):
            raise ValueError("Can't split it out: the name %r is empty or already in use" % new_slug)
        f = links_file(slug)
        sections = read_sections(f, default_pid_for(c))
        mine = sections.pop(pid, [])
        c["sources"] = [x for x in c["sources"] if x["profile"] != pid]
        c["aliases"] = [a for a in (c.get("aliases") or []) if a != new_slug]
        creators.append({"slug": new_slug, "added": int(time.time()), "sources": [src]})
        save_creators(creators)
        if f.exists():
            write_sections(f, sections)
        if mine:
            write_sections(links_file(new_slug), {pid: mine})
    return {"slug": new_slug}


def api_link_creators(body):
    """Merge creator `slug` into creator `into` (their sites and links combine in one file)."""
    slug, into = body.get("slug", ""), body.get("into", "")
    with LOCK:
        creators = load_creators()
        a = next((x for x in creators if x["slug"] == slug), None)
        b = next((x for x in creators if x["slug"] == into), None)
        if not a or not b or a is b:
            raise ValueError("Pick two different creators")
        clash = {x["profile"] for x in a["sources"]} & {x["profile"] for x in b["sources"]}
        if clash:
            raise ValueError("Both have an address on the same site (%s). Remove one first." %
                             ", ".join(get_profile(p)["name"] for p in clash))
        fa, fb = links_file(slug), links_file(into)
        sa = read_sections(fa, default_pid_for(a)) if fa.exists() else {}
        sb = read_sections(fb, default_pid_for(b)) if fb.exists() else {}
        for pid, lines in sa.items():
            sb[pid] = lines
        b["sources"] += a["sources"]
        remember_alias(b, slug)
        for al in a.get("aliases") or []:
            remember_alias(b, al)
        save_creators([x for x in creators if x is not a])
        if any(sb.values()):
            write_sections(fb, sb)
        if fa.exists() and fa.parent == LINKS:
            fa.unlink()
        pa = avatar_path(slug)
        if pa and not avatar_path(into):
            shutil.move(str(pa), str(AVATARS / (into + pa.suffix)))
        else:
            drop_avatar(slug)
    return {"slug": into}


def api_rename_creator(body):
    """Give a creator a different display name (the title on its box) and/or a different download folder.
    The creator's internal name (and its links file) never changes. An empty field goes back to the automatic value."""
    slug = body.get("slug", "")
    display = clean_text(body.get("display", ""))[:80]
    folder = re.sub(r"[^A-Za-z0-9_.-]", "_", clean_text(body.get("folder", ""))).strip("._") if "folder" in body else None
    move = bool(body.get("move_existing"))
    note = []
    with LOCK:
        creators = load_creators()
        c = next((x for x in creators if x["slug"] == slug), None)
        if not c:
            raise ValueError("Unknown creator")
        old_folder = folder_for(c)
        if display and display != slug:
            c["display_name"] = display
        else:
            c.pop("display_name", None)
        if folder is not None:
            if folder:
                c["folder_override"] = folder
            else:
                c.pop("folder_override", None)
        new_folder = folder_for(c)
        if move and new_folder != old_folder:
            if active_job() and active_job().kind == "download":
                raise ValueError("A download is running. Wait for it to finish before moving the folder.")
            lib = Path(load_settings()["library_dir"]).expanduser()
            src, dst = lib / old_folder, lib / new_folder
            if not src.is_dir():
                note.append("There was no existing folder %s to move." % old_folder)
            elif dst.exists():
                note.append("A folder called %s already exists, so the old one (%s) was left where it is." % (new_folder, old_folder))
            else:
                try:
                    src.rename(dst)
                    note.append("Moved the existing folder %s to %s." % (old_folder, new_folder))
                except OSError as e:
                    note.append("Couldn't move the folder: %s" % e)
        elif not move and new_folder != old_folder:
            note.append("New downloads go to %s. Files already in %s were not moved." % (new_folder, old_folder))
        save_creators(creators)
        if ensure_folder(normalize_creator(c)):
            note.append("Created the folder %s." % new_folder)
    return {"display": c.get("display_name") or slug, "folder": new_folder, "note": " ".join(note)}


def api_remove_source(body):
    """Remove one site from a creator: its section of the file goes, the other sites' links stay."""
    slug, pid = body.get("slug", ""), body.get("pid", "")
    with LOCK:
        creators = load_creators()
        c = next((x for x in creators if x["slug"] == slug), None)
        if not c or not any(s["profile"] == pid for s in c["sources"]):
            raise ValueError("That site isn't part of this creator")
        if len(c["sources"]) == 1:
            return api_remove_creator({"slug": slug})
        f = links_file(slug)
        sections = read_sections(f, default_pid_for(c))
        sections.pop(pid, None)
        c["sources"] = [s for s in c["sources"] if s["profile"] != pid]
        save_creators(creators)
        if f.exists():
            write_sections(f, sections)
    return {"ok": True}


def api_scrape(body):
    which = body.get("slugs", "missing")
    only = body.get("source")          # {"slug", "pid"}: just one site of one creator
    wanted = set(which) if isinstance(which, list) else set()
    items = []
    for r in creator_rows():
        for src in r["sources"]:
            if not src.get("url"):
                continue                     # imported from a file: nothing to scrape until its link is added
            if only:
                ok = r["slug"] == only.get("slug") and src["profile"] == only.get("pid")
            elif which == "all":
                ok = True
            elif which == "missing":
                ok = src["count"] == 0
            else:
                ok = r["slug"] in wanted
            if ok:
                items.append({"kind": "scrape", "key": "%s@%s" % (r["slug"], src["profile"]), "url": src["url"],
                              "slug": r["slug"], "pid": src["profile"],
                              "all_pages": bool(src.get("all_pages")) or auto_all_pages(src["url"], src["profile"])})
    if not items:
        raise ValueError("Nothing to scrape")
    return enqueue(items)


_OLD_ENDINGS = {"new", "exclusive", "leaks", "leaked", "videos"}


def search_name(slug):
    """Name to look up for a creator that was imported from a file: the file name with the old endings
    (_new, _exclusive, _new_leaks ...) taken off, underscores as spaces. anya_matusevich_exclusive_new -> 'anya matusevich'."""
    parts = [x for x in re.split(r"[_\s]+", slug) if x]
    while len(parts) > 1 and parts[-1].lower() in _OLD_ENDINGS:
        parts.pop()
    return " ".join(parts)


def api_find_addresses(body):
    """Look up the page address of every creator that has none (imported from a file) by name, using the
    site's "creator addresses to try", then scrape them. Same queue as everything else."""
    wanted = set(body.get("slugs") or [])
    pages = body.get("pages")
    all_pages = str(pages or "").strip().lower() in ("all", "a", "*", "every", "max")
    try:
        pages = None if all_pages else (int(pages) if pages not in (None, "", 0, "0") else None)
    except Exception:
        pages = None
    items, no_patterns = [], set()
    for c in load_creators():
        if wanted and c["slug"] not in wanted:
            continue
        for src in c["sources"]:
            if src.get("url"):
                continue
            prof = get_profile(src["profile"])
            if not [x for x in (prof.get("creator_patterns") or []) if x.strip()]:
                no_patterns.add(prof["name"])
                continue
            items.append({"kind": "find", "key": "%s@%s" % (c["slug"], src["profile"]), "name": search_name(c["slug"]),
                          "pid": src["profile"], "pages": pages,
                          "all_pages": all_pages or (pages is None and load_settings().get("pages_default_all", True)),
                          "scrape": bool(body.get("scrape", True)), "target": c["slug"]})
    if not items:
        if no_patterns:
            raise ValueError("%s has no 'creator addresses to try'. Add some in the Sites tab first." % ", ".join(sorted(no_patterns)))
        raise ValueError("Every creator already has an address")
    return enqueue(items)


SNAPSHOT_FILE = DATA / "category_snapshot.json"


def api_recategorise(body):
    """Re-sort every link with the current keywords and report what moved since the last time you pressed this.
    Nothing is rewritten on disk: categories are always worked out from the current keywords when links are read."""
    records, _labels, _info = build_library()
    now = {r["url"]: r["category"] for r in records}
    before = read_json(SNAPSHOT_FILE, None)
    moved, flows = None, {}
    if isinstance(before, dict) and before:
        moved = 0
        for url, cat in now.items():
            old = before.get(url)
            if old is not None and old != cat:
                moved += 1
                flows["%s -> %s" % (old, cat)] = flows.get("%s -> %s" % (old, cat), 0) + 1
    write_json(SNAPSHOT_FILE, now)
    counts = {}
    for cat in now.values():
        counts[cat] = counts.get(cat, 0) + 1
    return {"total": len(now), "moved": moved, "flows": flows, "counts": counts}


def api_creator_links(q):
    slug = (q.get("slug") or [""])[0]
    creator = next((c for c in load_creators() if c["slug"] == slug), None)
    if not creator:
        raise ValueError("Unknown creator")
    edges = load_settings()["bucket_edges_min"]
    labels = bucket_labels(edges)
    kws = {p["id"]: profile_keyword_info(p) for p in all_profiles()}
    names = {p["id"]: p["name"] for p in all_profiles()}
    f = links_file(slug)
    links = []
    if f.exists():
        for url, secs, title, site, views in parse_links_file(f, default_pid_for(creator)):
            links.append({"url": url, "dur": fmt_dur(secs), "secs": secs, "title": title, "views": views, "site": names.get(site, site),
                          "category": categorise(url + " " + title, kws.get(site) or kws[SCRIPT_ID]),
                          "bucket": bucket_of(secs, edges, labels)})
    return {"slug": slug, "links": links, "bucket_labels": labels, "categories": build_library()[2]["categories"]}


def api_library():
    records, labels, info = build_library()
    cats = {}
    for c in info["categories"]:
        cats[c] = {"count": 0, "buckets": {b: 0 for b in labels}}
    creators = {}
    for r in records:
        c = cats.setdefault(r["category"], {"count": 0, "buckets": {b: 0 for b in labels}})
        c["count"] += 1
        c["buckets"][r["bucket"]] += 1
        creators[r["creator"]] = creators.get(r["creator"], 0) + 1
    done = set(read_json(DOWNLOADED_FILE, []))
    return {
        "total": len(records),
        "downloaded": sum(1 for r in records if r["url"] in done),
        "categories": cats,
        "bucket_labels": labels,
        "creators": [{"slug": k, "count": v} for k, v in sorted(creators.items())],
    }


def seeded_shuffle(items, seed=None):
    """Shuffle a copy. The same seed over the same items always gives the same order, so what you
    preview is exactly what you later save or download. No seed means a fresh random order."""
    items = list(items)
    random.Random(None if seed in (None, "") else str(seed)).shuffle(items)
    return items


def api_pick(q):
    params = {k: v[0] for k, v in q.items()}
    pool = select_records(params)
    n = int(params.get("n") or 10)
    chosen = seeded_shuffle(pool, params.get("seed"))[:n]
    return {"pool": len(pool), "links": [{"url": r["url"], "dur": fmt_dur(r["secs"]), "creator": r["creator"], "title": r.get("title", "")}
                                         for r in chosen]}


def parse_weights(raw):
    out = {}
    for k, v in (raw or {}).items():
        try:
            out[str(k)] = max(float(v), 0.0)
        except (TypeError, ValueError):
            continue
    return out


def mix_by_site(records, weights, seed, keep_order=False):
    """Order links so every prefix keeps the wanted site-to-site ratio (smooth weighted round robin).
    Each site's own links are shuffled with the seed. Sites with weight 0 or no weight are left out;
    a site that runs out simply stops contributing and the rest carry on in their ratio."""
    by = {}
    for r in records:
        if weights.get(r["site"], 0) > 0:
            by.setdefault(r["site"], []).append(r)
    queues = {s: (list(rs) if keep_order else seeded_shuffle(rs, "%s|%s" % (seed, s))) for s, rs in by.items()}
    current = {s: 0.0 for s in queues}
    out = []
    while queues:
        total = sum(weights[s] for s in queues)
        for s in queues:
            current[s] += weights[s]
        best = max(queues, key=lambda s: (current[s], s))
        current[best] -= total
        out.append(queues[best].pop(0))
        if not queues[best]:
            del queues[best], current[best]
    return out


def parse_min_views(raw):
    """'100000', '100k' or '1.5m' -> a number; empty/invalid -> 0 (no minimum)"""
    t = str(raw or "").strip().lower().replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", t)
    if not m:
        return 0
    return int(float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2)])


def cap_per_creator(records, cap):
    """Keep at most `cap` links from any one creator, in the order given (so the best-placed ones are kept)."""
    try:
        cap = int(cap or 0)
    except (TypeError, ValueError):
        cap = 0
    if cap <= 0:
        return records
    seen, out = {}, []
    for r in records:
        if seen.get(r["creator"], 0) < cap:
            seen[r["creator"]] = seen.get(r["creator"], 0) + 1
            out.append(r)
    return out


def spread_records(records, n, mode, min_per=0):
    """Decide how many links each creator gets, keeping the order inside each creator.
    equal: take one from each creator in turn (so every creator gets the same number, give or take one when n doesn't
           divide evenly; a creator with fewer links drops out and the rest carry on). Any first-k is balanced too.
    min:   first guarantee `min_per` links from every creator, then fill the rest in the original order."""
    if mode not in ("equal", "min") or not records:
        return records
    by, order = {}, []
    for r in records:
        if r["creator"] not in by:
            by[r["creator"]] = []
            order.append(r["creator"])
        by[r["creator"]].append(r)
    if mode == "equal":
        out, queues = [], [list(by[c]) for c in order]
        while queues:
            nxt = []
            for q in queues:
                out.append(q.pop(0))
                if q:
                    nxt.append(q)
            queues = nxt
        return out
    try:
        k = max(int(min_per or 0), 0)
    except (TypeError, ValueError):
        k = 0
    if not k:
        return records
    first = [r for c in order for r in by[c][:k]]
    taken = {r["url"] for r in first}
    return first + [r for r in records if r["url"] not in taken]


# ───────────────────────── Discover ─────────────────────────
DISC = discover.Store(DATA)
PENDING_SCRAPES = []              # creators waiting for the job slot (another kind of job was running)
_PENDING_LOCK = threading.Lock()
DISCOVER_DRY_RUN = bool(os.environ.get("DISCOVER_DRY_RUN"))      # testing: add the creator but do not scrape


def discover_existing():
    return {c["slug"] for c in load_creators()}


def discover_try_scrape(cslug):
    """Queue this creator's scrape. If another kind of job holds the slot, wait for it (the helper thread retries)."""
    if DISCOVER_DRY_RUN:
        return True
    try:
        api_scrape({"slugs": [cslug]})
        return True
    except RuntimeError:
        with _PENDING_LOCK:
            if cslug not in PENDING_SCRAPES:
                PENDING_SCRAPES.append(cslug)
        return False
    except ValueError:
        return True


def discover_flush():
    with _PENDING_LOCK:
        todo = list(PENDING_SCRAPES)
    for cs in todo:
        j = active_job()
        if j and not (j.kind == "scrape" and getattr(j, "accepting", False)):
            break
        try:
            api_scrape({"slugs": [cs]})
        except RuntimeError:
            break
        except ValueError:
            pass
        with _PENDING_LOCK:
            if cs in PENDING_SCRAPES:
                PENDING_SCRAPES.remove(cs)


def discover_loop():
    while True:
        time.sleep(4)
        try:
            discover_flush()
        except Exception:
            pass


def discover_keep(pslug):
    st = DISC.state()["settings"]
    url = "https://www.pornhub.com/pornstar/%s/videos?o=mv" % pslug
    r = api_add_creators({"urls": url, "profile": "pornhub", "pages": st["scrape_pages"], "scrape": False})
    cslug = r["linked"][0]["to"] if r.get("linked") else discover.creator_slug(pslug)
    if not avatar_path(cslug):                     # the creator card gets the Discover picture straight away
        img = DISC.image_path(pslug)
        if img:
            AVATARS.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, AVATARS / (cslug + ".jpg"))
    queued = discover_try_scrape(cslug)
    return {"creator": cslug, "queued": queued, "note": "; ".join(x["reason"] for x in r.get("skipped", []))}


def discover_queue_info():
    j = active_job()
    cur = (j.current or "").split("@")[0] if (j and j.kind == "scrape") else None
    with LOCK:
        waiting = [i["slug"] for i in SCRAPE_QUEUE]
    with _PENDING_LOCK:
        pend = list(PENDING_SCRAPES)
    return {"scraping": cur, "waiting": waiting + pend, "busy_with": (j.kind if j and j.kind != "scrape" else None)}


def discover_kept_status():
    info = discover_queue_info()
    rows = {r["slug"]: r for r in creator_rows()}
    out = []
    for c in discover.kept_recent(DISC, 16):
        cs = discover.creator_slug(c["slug"])
        links = (rows.get(cs) or {}).get("count", 0)
        st = "scraping" if cs == info["scraping"] else "queued" if cs in info["waiting"] else "done" if links else "added"
        out.append({**c, "creator": cs, "links": links, "status": st})
    return out


def api_discover_collect(body):
    pages = max(1, min(int(body.get("pages") or 40), 100))
    job = start_job("discover", "Collecting performers (%d pages)" % pages,
                    lambda j: discover.collect(DISC, pages, j.say, lambda: j.stop_flag))
    return job.summary()


def api_discover_settings(body):
    s = discover.set_settings(DISC, body)
    return {"settings": s, "left": discover.summary(DISC, discover_existing())["left"]}


def api_discover_decide(body):
    slug = str(body.get("slug", ""))
    keep = bool(body.get("keep"))
    discover.decide(DISC, slug, keep)
    res = {"ok": True}
    if keep:
        try:
            res.update(discover_keep(slug))
        except Exception as e:                     # the decision stands; tell the page what went wrong
            res.update(error=str(e))
    return res


def api_discover_undo(body):
    got = discover.undo(DISC)
    if not got:
        return {"card": None}
    card, was_keep = got
    note = ""
    if was_keep:
        cs = discover.creator_slug(card["slug"])
        with LOCK:
            before = len(SCRAPE_QUEUE)
            SCRAPE_QUEUE[:] = [i for i in SCRAPE_QUEUE if i["slug"] != cs]
            dropped = before != len(SCRAPE_QUEUE)
        with _PENDING_LOCK:
            if cs in PENDING_SCRAPES:
                PENDING_SCRAPES.remove(cs)
                dropped = True
        note = ("Taken back; its scrape was cancelled. It stays in Creators until you remove it there." if dropped
                else "Taken back. It was already added, so it stays in Creators (remove it there if you want it gone).")
    return {"card": card, "was_keep": was_keep, "note": note}


def site_for_url(u):
    """The site profile whose address matches this link, or None (then the global download method is used)."""
    host = urlparse(u).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    for p in all_profiles():
        base = urlparse(p.get("base_url") or "").netloc.lower()
        base = base[4:] if base.startswith("www.") else base
        if base and (host == base or host.endswith("." + base)):
            return p["id"]
    return None


def library_folder_names():
    lib = Path(load_settings()["library_dir"]).expanduser()
    return sorted(d.name for d in lib.iterdir() if d.is_dir() and not d.name.startswith(".")) if lib.is_dir() else []


def resolve_manual_folder(raw):
    """The folder a hand-entered link is saved into. A name that matches an existing library folder (ignoring case,
    '-', '_' and spaces) uses that folder, so it never creates a duplicate like hannah_jo next to hannah-jo."""
    name = re.sub(r"[^A-Za-z0-9_.\- ]", "", str(raw or "")).strip().strip(".")
    if not name:
        return "unsorted"
    k = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    for existing in library_folder_names():
        if k(existing) == k(name):
            return existing
    return re.sub(r"[ _]+", "-", name).strip("-").lower() or "unsorted"


def select_for_download(body):
    """The links to download, in the order they will be tried. -> (records, unknown urls)

    The same filters apply in both modes: creators (include / exclude), categories, lengths (several at once),
    and optionally a ratio between sites.
    mode "list": the links given (e.g. the shuffled list from the Lists tab), in that order, narrowed by the filters.
                 With "random" they are shuffled with the seed instead.
    mode "pick": every matching link in the library, shuffled with the seed so a preview matches the download."""
    if body.get("mode") == "manual":                  # links typed in by hand: they need not be in the library
        folder = resolve_manual_folder(body.get("manual_folder"))
        out, seen = [], set()
        for line in str(body.get("manual") or "").splitlines():
            for u in extract_urls(line)[:1]:
                if u.rstrip("/") in seen:
                    continue
                seen.add(u.rstrip("/"))
                out.append({"url": u, "creator": folder, "folder": folder, "site": site_for_url(u), "secs": 0,
                            "category": "", "bucket": "", "views": 0, "title": ""})
        return out, []
    records, labels, _ = build_library()
    done = set(read_json(DOWNLOADED_FILE, [])) if body.get("exclude_downloaded") else set()
    inc = set(body.get("creators") or ([body["creator"]] if body.get("creator") else []))
    exc = set(body.get("exclude_creators") or [])
    cats = set(body.get("categories") or ([body["category"]] if body.get("category") else []))
    buckets = set(body.get("buckets") or ([body["bucket"]] if body.get("bucket") else []))
    weights = parse_weights(body.get("site_weights"))
    mixing = any(w > 0 for w in weights.values())
    min_views = parse_min_views(body.get("min_views"))

    def finish(ordered):
        """max per creator first, then how the creators share the run (equal split / at least N each)"""
        ordered = cap_per_creator(ordered, body.get("max_per_creator"))
        try:
            n = int(body.get("n") or 0)
        except (TypeError, ValueError):
            n = 0
        return spread_records(ordered, n, body.get("spread"), body.get("min_per_creator"))

    def keep(r):
        return ((not inc or r["creator"] in inc) and r["creator"] not in exc
                and (not cats or r["category"] in cats) and (not buckets or r["bucket"] in buckets)
                and (not min_views or (r.get("views") or 0) >= min_views)       # unknown views can't pass a minimum
                and r["url"] not in done)

    if body.get("mode") == "list":
        index = {r["url"].rstrip("/"): r for r in records}
        ordered, unknown, seen = [], [], set()
        for line in str(body.get("list") or "").splitlines():
            urls = extract_urls(line)
            if not urls:
                continue
            r = index.get(urls[0].rstrip("/"))
            if not r:
                unknown.append(urls[0])
            elif r["url"] not in seen:
                seen.add(r["url"])
                if keep(r):
                    ordered.append(r)
        random_ = bool(body.get("random"))
        ordered = mix_by_site(ordered, weights, body.get("seed"), keep_order=not random_) if mixing \
            else (seeded_shuffle(ordered, body.get("seed")) if random_ else ordered)
        return finish(ordered), unknown

    pool = [r for r in records if keep(r)]
    return finish(mix_by_site(pool, weights, body.get("seed")) if mixing else seeded_shuffle(pool, body.get("seed"))), []


def api_download_preview(body):
    ordered, unknown = select_for_download(body)
    n = int(body.get("n") or load_settings()["target_success"])
    first = ordered[:n]
    names = {p["id"]: p["name"] for p in all_profiles()}

    def tally(rs):
        out = {}
        for r in rs:
            out[names.get(r["site"], r["site"])] = out.get(names.get(r["site"], r["site"]), 0) + 1
        return out

    return {"folder": ordered[0]["folder"] if ordered and body.get("mode") == "manual" else None,
            "folder_exists": bool(ordered) and body.get("mode") == "manual" and ordered[0]["folder"] in library_folder_names(),
            "pool": len(ordered), "shown": len(first), "by_site": tally(first), "pool_by_site": tally(ordered),
            "unknown": len(unknown), "unknown_sample": unknown[:3],
            "links": [{"url": r["url"], "dur": fmt_dur(r["secs"]), "creator": r["creator"], "title": r.get("title", ""),
                       "site": names.get(r["site"], r["site"])} for r in first]}


def method_for_site(pid, settings):
    """How links from this site are downloaded: the site's own choice, else the global setting."""
    m = (get_profile(pid).get("download_method") if pid else "") or settings.get("download_method", "vdh")
    return m if m in ("vdh", "ytdlp") else "vdh"


def build_download_config(body):
    s = load_settings()
    pool, unknown = select_for_download(body)
    if not pool:
        if body.get("mode") == "manual":
            raise ValueError("Paste at least one link first.")
        raise ValueError("None of the links match those settings" if body.get("mode") != "list"
                         else "None of the pasted links are in your library%s" % (" (%d were not recognised)" % len(unknown) if unknown else ""))
    n = int(body.get("n") or s["target_success"])
    cfg = {
        "links": [{"url": r["url"], "creator": r["creator"], "folder": r["folder"], "method": method_for_site(r.get("site"), s)}
                  for r in pool],
        "target_success": n,
        "settings": s,
        "templates_dir": str(TEMPLATES),
        "log_file": str(DATA / "download_log.jsonl"),   # which link produced which file, and where it went
    }
    return cfg, len(pool)


def api_download(body):
    cfg, pool_size = build_download_config(body)
    write_json(RUN_CONFIG, cfg)
    job = start_job("download", "Downloading %d from %d matching links" % (cfg["target_success"], pool_size), download_target)
    return job.summary()


def api_capture(body):
    which = body.get("which")
    if which not in ("vdh_icon", "download_button", "vdh_icon_image", "download_button_image"):
        raise ValueError("bad target")
    job = start_job("capture:" + which, "Capturing a picture" if which.endswith("_image") else "Capturing mouse position", capture_target)
    return job.summary()


def api_stop():
    job = active_job()
    if job:
        job.stop_flag = True
        if job.proc:
            try:
                job.proc.terminate()
            except Exception:
                pass
    return {"ok": True}


# ───────────────────────── list builder ─────────────────────────

def _natural(s):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s)]  # "title 2" sorts before "title 10"


def title_key(rec):
    """Sort key for a record: its real title if it has one, otherwise the words in its link."""
    if rec.get("title"):
        return _natural(rec["title"].lower().strip())
    seg = unquote(urlparse(rec["url"]).path.rstrip("/").split("/")[-1]).replace("-", " ").replace("_", " ")
    return _natural(seg.lower().strip())


ORDERS = ("creator", "title", "category", "random", "scrape", "views")
SPLITS = ("none", "category", "creator")


def api_build_list(body):
    order = body.get("order", "creator")
    split = body.get("split", "none")
    if order not in ORDERS or split not in SPLITS:
        raise ValueError("Unknown order or split option")
    records, labels, info = build_library()
    cats = info["categories"]

    want_creators = set(body.get("creators") or [])
    want_cats = set(body.get("categories") or [])
    want_buckets = set(body.get("buckets") or [])
    done = set(read_json(DOWNLOADED_FILE, [])) if body.get("exclude_downloaded") else set()
    min_views = parse_min_views(body.get("min_views"))
    recs = [r for r in records
            if (not want_creators or r["creator"] in want_creators)
            and (not want_cats or r["category"] in want_cats)
            and (not want_buckets or r["bucket"] in want_buckets)
            and (not min_views or (r.get("views") or 0) >= min_views)
            and r["url"] not in done]

    cat_idx = {c: i for i, c in enumerate(cats)}
    if order == "creator":
        recs.sort(key=lambda r: (r["creator"].lower(), title_key(r)))
    elif order == "title":
        recs.sort(key=lambda r: (title_key(r), r["creator"].lower()))
    elif order == "category":
        recs.sort(key=lambda r: (cat_idx.get(r["category"], 99), r["creator"].lower(), title_key(r)))
    elif order == "random":
        recs = seeded_shuffle(recs, body.get("seed"))
    elif order == "views":
        recs.sort(key=lambda r: (-(r.get("views") or -1), r["creator"].lower(), title_key(r)))   # most viewed first; unknown last

    if split == "category":
        buckets = {}
        for r in recs:
            buckets.setdefault(r["category"], []).append(r)
        groups = [(c, buckets[c]) for c in cats if c in buckets]
    elif split == "creator":
        buckets = {}
        for r in recs:
            buckets.setdefault(r["creator"], []).append(r)
        groups = sorted(buckets.items(), key=lambda kv: kv[0].lower())
    else:
        groups = [("all", recs)]

    with_title = bool(body.get("titles"))
    with_dur = bool(body.get("durations")) or with_title   # titles come after the duration field

    def line(r):
        if not with_dur:
            return r["url"]
        s = "%s  |  %s" % (r["url"], fmt_dur(r["secs"]))
        return s + "  |  " + r["title"] if with_title and r.get("title") else s

    out = [{"name": name, "count": len(g), "lines": [line(r) for r in g]} for name, g in groups]

    saved = None
    if body.get("save"):
        folder = LISTS / "built"
        folder.mkdir(parents=True, exist_ok=True)
        base = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(body.get("name") or "").strip()).strip("_.") \
            or ("%s_by_%s" % ("all" if split == "none" else "per_" + split, order))
        saved = []
        for g in out:
            fname = base + ".txt" if split == "none" else "%s_%s.txt" % (base, re.sub(r"[^A-Za-z0-9_.-]+", "_", g["name"]))
            (folder / fname).write_text("".join(l + "\n" for l in g["lines"]), encoding="utf-8")
            saved.append(fname)
        saved = {"folder": str(folder), "files": saved}

    return {"total": sum(g["count"] for g in out), "groups": out, "saved": saved}


def api_export():
    records, labels, info = build_library()

    def write(path, recs, shuffle=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        recs = list(recs)
        if shuffle:
            random.shuffle(recs)
        path.write_text("".join("%s  |  %s\n" % (r["url"], fmt_dur(r["secs"])) for r in recs), encoding="utf-8")

    written = []
    write(LISTS / "all_links_ordered.txt", records); written.append("all_links_ordered.txt")
    write(LISTS / "all_links_random.txt", records, True); written.append("all_links_random.txt")
    for cat in info["categories"]:
        cr = [r for r in records if r["category"] == cat]
        base = cat.lower()
        write(LISTS / ("all_links_ordered_%s.txt" % base), cr)
        written.append("all_links_ordered_%s.txt" % base)
        for b in labels:
            br = [r for r in cr if r["bucket"] == b]
            write(LISTS / base / ("%s.txt" % b), br)
            write(LISTS / base / ("%s_random.txt" % b), br, True)
    return {"folder": str(LISTS), "files": written}


# ───────────────────────── HTTP plumbing ─────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "LinksUI/1.0"

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "bad host"})
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/api/discover/state":
                return self._json(200, dict(discover.summary(DISC, discover_existing()), queue=discover_queue_info()))
            if u.path == "/api/discover/deck":
                n = max(1, min(int((q.get("n") or ["20"])[0]), 60))
                skip = [x for x in (q.get("skip") or [""])[0].split(",") if x]
                return self._json(200, discover.deck(DISC, n, discover_existing(), skip))
            if u.path == "/api/discover/kept":
                return self._json(200, {"kept": discover_kept_status(), "queue": discover_queue_info()})
            if u.path.startswith("/discover_img/"):
                f = DISC.image_path(Path(unquote(u.path[len("/discover_img/"):])).stem)
                if not f:
                    return self._json(404, {"error": "no picture"})
                data = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
                return
            if u.path == "/api/library_folders":
                return self._json(200, {"folders": library_folder_names()})
            if u.path == "/api/state":
                return self._json(200, api_state())
            if u.path == "/api/library":
                return self._json(200, api_library())
            if u.path == "/api/creator_links":
                return self._json(200, api_creator_links(q))
            if u.path == "/api/pick":
                return self._json(200, api_pick(q))
            if u.path == "/api/job":
                job = CURRENT["job"]
                since = int(q.get("since", ["0"])[0])
                if not job:
                    return self._json(200, {"job": None, "lines": []})
                with LOCK:
                    lines = job.log[since:]
                    items = list(job.items.values()) if job.kind == "download" else []
                return self._json(200, {"job": job.summary(), "lines": lines, "items": items, "target": job.target})
            if u.path.startswith("/templates/"):
                return self._template(u.path[len("/templates/"):])
            if u.path.startswith("/avatars/"):
                return self._avatar(u.path[len("/avatars/"):])
            return self._static(u.path)
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _template(self, name):
        f = TEMPLATES / Path(unquote(name)).name
        if f.suffix.lower() != ".png" or not f.is_file():
            return self._json(404, {"error": "not found"})
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _avatar(self, name):
        f = (AVATARS / Path(unquote(name)).name)
        if f.suffix.lower() not in AVATAR_EXTS or not f.is_file():
            return self._json(404, {"error": "not found"})
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
                                          ".gif": "image/gif", ".avif": "image/avif"}[f.suffix.lower()])
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/"):]
        f = (STATIC / rel).resolve()
        if STATIC not in f.parents or not f.is_file():
            return self._json(404, {"error": "not found"})
        ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8"}.get(f.suffix, "application/octet-stream")
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        # CSRF / DNS-rebinding guard: only our own page can drive these endpoints.
        if not self._host_ok() or self.headers.get("X-UI") != "1":
            return self._json(403, {"error": "forbidden"})
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            return self._json(403, {"error": "forbidden origin"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})
        path = urlparse(self.path).path
        try:
            routes = {
                "/api/creators/add": api_add_creators,
                "/api/creators/remove": api_remove_creator,
                "/api/creators/import": api_import,
                "/api/creators/remove_source": api_remove_source,
                "/api/creators/unlink": api_unlink_source,
                "/api/creators/link": api_link_creators,
                "/api/creators/rename": api_rename_creator,
                "/api/creators/avatar_choice": api_avatar_choice,
                "/api/creators/make_folders": api_make_folders,
                "/api/recategorise": api_recategorise,
                "/api/creators/find_addresses": api_find_addresses,
                "/api/profiles/save": api_save_profile,
                "/api/profiles/delete": api_delete_profile,
                "/api/profiles/test": api_test_profile,
                "/api/scrape": api_scrape,
                "/api/discover/collect": api_discover_collect,
                "/api/discover/decide": api_discover_decide,
                "/api/discover/undo": api_discover_undo,
                "/api/discover/shuffle": lambda b: {"left": discover.reshuffle(DISC)},
                "/api/discover/reset": lambda b: {"restored": discover.reset_skipped(DISC)},
                "/api/discover/settings": lambda b: api_discover_settings(b),
                "/api/download": api_download,
                "/api/download_preview": api_download_preview,
                "/api/capture": api_capture,
                "/api/settings": lambda b: save_settings(b),
                "/api/export": lambda b: api_export(),
                "/api/build_list": api_build_list,
                "/api/stop": lambda b: api_stop(),
            }
            if path not in routes:
                return self._json(404, {"error": "not found"})
            return self._json(200, routes[path](body))
        except RuntimeError as e:
            return self._json(409, {"error": str(e)})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": str(e)})


def watch_for_code_changes():
    """Restart this server when its own code changes and no job is running (Mac/Linux).
    Set LINKS_UI_NO_RELOAD=1 to turn it off. On Windows the page shows a banner instead."""
    if sys.platform.startswith("win") or os.environ.get("LINKS_UI_NO_RELOAD"):
        return

    def loop():
        while True:
            time.sleep(3)
            try:
                if code_fingerprint() != STARTED_WITH and not active_job():
                    print("Code changed - restarting the server...", flush=True)
                    args = [sys.executable] + sys.argv + ([] if "--no-open" in sys.argv else ["--no-open"])
                    os.execv(sys.executable, args)
            except Exception:
                pass

    threading.Thread(target=loop, daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    global STARTED_WITH
    STARTED_WITH = code_fingerprint()
    ensure_dirs()
    watch_for_code_changes()
    threading.Thread(target=discover_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = "http://127.0.0.1:%d" % args.port
    print("Links UI running at %s  (Ctrl+C to quit)" % url)
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBye")


if __name__ == "__main__":
    main()
