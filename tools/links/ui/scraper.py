#!/usr/bin/env python3
"""
Profile-driven scraper used by the UI (a configurable take on scrape_fruitsvids.py).

  scraper.py --profile-file profile.json <creator-url>           scrape, write <slug>_links.txt in cwd
  scraper.py --profile-file profile.json --test <creator-url>    fetch page 1 only and explain what was found
  scraper.py --profile-file profile.json --find-name "Jane Doe"  try the site's creator addresses for a name
  (add --slug jane_doe to a scrape to choose the output file name, --all-pages to keep going until the last page)

The output file format matches scrape_fruitsvids.py (ALL LINKS + CATEGORISED sections).
"""
import sys

sys.dont_write_bytecode = True

import json
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

for _stream in (sys.stdout, sys.stderr):  # Windows consoles/pipes default to cp1252, which can't print ✓ ✗ →
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LANG_PREFIXES = ("es", "fr", "pt", "de", "it", "zh", "ja", "ru", "tr")

DEFAULT_PROFILE = {
    "name": "New site",
    "base_url": "https://example.com",
    # URL of page N (N>1), relative to the site. {path} = the creator page path, {page} = page number.
    "page_template": "{path}/{page}/",
    "video_link_regex": r"/videos/[^/]+/?$",
    "duration_regex": r"(?:(\d+):)?(\d+):(\d{2})",
    "slug_strip": ["videos", "exclusive-videos", "new-videos", "videosis"],
    "keywords": {},
    "download_method": "",   # "", "vdh" or "ytdlp": how videos from this site are downloaded ("" = the global setting)
    "views_selector": "",    # optional CSS selector (inside each video's box) of its view count; empty = look for "123 views" text
    "dominant": "",          # optional category that wins whenever any of its words is present
    "negative": [],
    "request_delay": 1.0,
    # Addresses to try when someone is added by name only, in order. Placeholders:
    #   {name} jane-doe   {compact} janedoe   {underscore} jane_doe
    "creator_patterns": [],
    # tick when each video's ID is in the link after a "?" (e.g. /watch?id=123): keeps the query so videos stay distinct
    "keep_query": False,
    "max_auto_pages": 100,   # safety limit for "all pages" mode
    # Alternative to reading links: collect an ID from an attribute on each video's element
    # (e.g. data-video-vkey="abc123") and build the link from it.
    "video_key_attr": "",
    "video_url_template": "/view_video.php?viewkey={key}",
    # Several pages per creator, scraped one after the other and combined (e.g. "uploaded" and "tagged" videos live on
    # different addresses). Each: {"address": "{root}/videos/upload?o=mv", "scope": "#uploadedVideosSection"}.
    # {root} is the creator's own address with any of these endings removed. Empty = just the address you give.
    "sections": [],
    "exclude_selector": "",  # optional CSS selector: everything inside it is ignored (e.g. extra videos the site adds to every page)
    "scope_selector": "",    # optional CSS selector: only look inside it (skips "recommended" videos etc.)
    # Creator's profile picture: CSS selector of the <img> (or <meta property="og:image">), and which attribute holds the address
    "avatar_selector": "",
    "avatar_attr": "src",
    # Some sites answer a missing creator with a normal page (HTTP 200) that says "404 page not found" and then
    # lists unrelated videos. If any of these phrases is on the page, it counts as "no such creator".
    "not_found_text": ["page not found"],
}


def with_defaults(profile):
    p = dict(DEFAULT_PROFILE)
    p.update(profile or {})
    # profiles saved before page_template existed used pagination "path" / "query"
    if profile and "page_template" not in profile and "pagination" in profile:
        if profile["pagination"] == "query":
            p["page_template"] = "{path}/?%s={page}" % (profile.get("page_param") or "page")
        else:
            p["page_template"] = "{path}/{page}/"
    p.pop("pagination", None)
    p.pop("page_param", None)
    return p


# ───────────── URL helpers ─────────────

def _template_parts(template):
    """-> (path_template, query_param_name_or_None)"""
    path_part, _, query_part = template.partition("?")
    param = None
    m = re.search(r"(?:^|&)([^=&]+)=\{page\}", query_part)
    if m:
        param = m.group(1)
    return path_part, param


def _parse(url, profile):
    """-> (base_path, max_page, extra_query, has_page_marker, ends_with_slash)"""
    parsed = urlparse(url)
    path = parsed.path
    slash = path.endswith("/") or not path.strip("/")  # page 1 is fetched exactly as it was given
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    path_part, param = _template_parts(profile["page_template"])
    prefix = path_part.split("{path}")[0]  # literal text the template puts before {path}

    def unprefixed(p):
        p = p.rstrip("/")
        return p[len(prefix):] if prefix and p.startswith(prefix) else p

    if param:
        if param in query:
            try:
                return unprefixed(path), int(query.pop(param)), query, True, slash
            except ValueError:
                query.pop(param, None)
        return unprefixed(path), 1, query, False, slash

    pattern = re.escape(path_part)
    pattern = pattern.replace(re.escape("{path}"), "(?P<path>.+?)").replace(re.escape("{page}"), r"(?P<page>\d+)")
    if path_part.endswith("/"):
        pattern = pattern[:-1] + "/?"
    m = re.fullmatch(pattern, path)
    if m and "path" in m.groupdict() and "page" in m.groupdict():
        # a page-N link only shows the slash style of page 1 if the format itself ends in "/"
        return m.group("path").rstrip("/"), int(m.group("page")), query, True, (path.endswith("/") if path_part.endswith("/") else True)
    return unprefixed(path), 1, query, False, slash


def with_pages(url, pages, profile):
    """Turn a creator URL into 'scrape pages 1..pages' form, if it doesn't already say so."""
    profile = with_defaults(profile)
    base_path, _, extra, has_page, _slash = _parse(url, profile)
    if has_page or not pages or int(pages) <= 1:
        return url
    parsed = urlparse(url)
    local = dict(profile, base_url="%s://%s" % (parsed.scheme, parsed.netloc))
    return build_page_url(local, base_path, int(pages), extra)


def slug_from_url(url, profile, separator="_"):
    """Creator name from a creator link. separator="-" keeps the link's own hyphens (used for folder names)."""
    profile = with_defaults(profile)
    base_path = creator_root(_parse(url, profile)[0], profile)  # drops any page marker and section ending
    parts = [x for x in base_path.strip("/").split("/") if x]
    if parts and parts[0] in LANG_PREFIXES:
        parts = parts[1:]
    # longest suffix first, so "exclusive-videos" is stripped whole rather than just "videos"
    suffixes = sorted((s.strip("- ") for s in profile["slug_strip"] if s.strip("- ")), key=len, reverse=True)
    for p in reversed(parts):
        if p and not p.isdigit() and "sort_by" not in p and p.lower() != "videos":
            for s in suffixes:
                if p.endswith("-" + s):
                    p = p[: -(len(s) + 1)]
                    break
            return p.replace("-", separator)
    return "unknown"


def parse_url(url, profile):
    """-> (base_path, max_page, extra_query, ends_with_slash)"""
    base_path, max_page, extra, _has, slash = _parse(url, profile)
    return base_path, max_page, extra, slash


def build_page_url(profile, base_path, page, extra_query, slash=True):
    base = profile["base_url"].rstrip("/")
    template = profile["page_template"]
    if page <= 1:
        prefix = template.partition("?")[0].split("{path}")[0]
        path_q = prefix + base_path + ("/" if slash else "")
    else:
        path_q = template.replace("{path}", base_path).replace("{page}", str(page))
    path, _, q = path_q.partition("?")
    extra = urlencode(extra_query)
    q = "&".join(x for x in (q, extra) if x)
    return base + path + ("?" + q if q else "")



# ───────────── several pages per creator ─────────────

def _section_suffix(sec):
    return sec["address"].replace("{root}", "").split("?")[0].rstrip("/")


def creator_root(base_path, profile):
    """The creator's own address: base_path with the ending of one of the sections taken off
    (/pornstar/jane/videos/upload -> /pornstar/jane). An address that ends in none of them is already the root."""
    path = base_path.rstrip("/")
    best = ""
    for sec in profile.get("sections") or []:
        suf = _section_suffix(sec)
        if suf and path.endswith(suf) and len(suf) > len(best):
            best = suf
    return path[: len(path) - len(best)] if best else path


def expand_sections(profile, url):
    """-> [(address to scrape, scope selector, label)]. Without sections that is just the address you gave."""
    secs = profile.get("sections") or []
    if not secs:
        return [(url, profile.get("scope_selector", ""), "")]
    base_path = _parse(url, profile)[0]
    root = creator_root(base_path, profile)
    base = profile["base_url"].rstrip("/")
    return [(base + sec["address"].replace("{root}", root), sec.get("scope") or profile.get("scope_selector", ""), _section_suffix(sec) or "/")
            for sec in secs]


# ───────────── parsing ─────────────

def duration_seconds(text, regex):
    m = re.fullmatch(regex, text.strip())
    if not m:
        return None
    g = m.groups()
    if len(g) >= 3:
        h, mi, s = g[-3], g[-2], g[-1]
        return int(h or 0) * 3600 + int(mi) * 60 + int(s)
    if len(g) == 2:
        return int(g[0]) * 60 + int(g[1])
    return None


def fetch(session, url):
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    r = session.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r


def clean_title(s):
    """Collapse whitespace; (HTML entities like &quot; are already decoded by the parser)."""
    return re.sub(r"\s+", " ", str(s or "")).strip()[:300]


def find_title(el, key=None):
    """Best title for a video element: a link's title="..." (preferring the link that holds the key),
    then an image's alt text, then the element's own title."""
    anchors = ([el] if el.name == "a" else []) + el.find_all("a")
    titled = [a for a in anchors if clean_title(a.get("title"))]
    if key:
        for a in titled:
            if key in (a.get("href") or ""):
                return clean_title(a.get("title"))
    if titled:
        return clean_title(titled[0].get("title"))
    for img in el.find_all("img"):
        if clean_title(img.get("alt")):
            return clean_title(img.get("alt"))
    return clean_title(el.get("title"))


_VIEWS_RE = re.compile(r"^\s*([\d][\d.,\s]*)\s*([KkMmBb])?\s*(?:views?|vues|vistas|visualiza\w*|aufrufe|weergaven)?\s*$", re.I)


def parse_views(text):
    """'17.6M views' -> 17600000, '340K' -> 340000, '1,234 views' -> 1234. None if it isn't a count."""
    m = _VIEWS_RE.match(str(text or ""))
    if not m:
        return None
    num, suffix = m.group(1).strip().replace(" ", ""), (m.group(2) or "").upper()
    try:
        if suffix:
            return int(round(float(num.replace(",", ".") if num.count(",") == 1 and "." not in num else num.replace(",", "")) *
                             {"K": 1e3, "M": 1e6, "B": 1e9}[suffix]))
        return int(re.sub(r"[.,]", "", num))
    except ValueError:
        return None


def _find_views(el, profile):
    """View count of one video's box: from the selector if one is set, else from any text that reads like '123 views'."""
    sel = (profile.get("views_selector") or "").strip()
    if sel:
        node = el.select_one(sel)
        return parse_views(node.get_text(" ", strip=True)) if node else None
    for node in el.find_all(True):                       # small elements only: "<span><var>225M</var> views</span>"
        t = node.get_text(" ", strip=True)
        if t and len(t) <= 30 and re.search(r"views?\b|vues|vistas|aufrufe|weergaven", t, re.I):
            v = parse_views(t)
            if v is not None:
                return v
    return None


def _find_duration(el, profile):
    for node in el.find_all(string=True):
        dur = duration_seconds(node, profile["duration_regex"])
        if dur is not None:
            return dur
    return None


def key_elements(soup, profile):
    """Every element carrying the video-key attribute (inside the scope, if one is set)."""
    attr = profile["video_key_attr"]
    roots = soup.select(profile["scope_selector"]) if profile["scope_selector"].strip() else [soup]
    found = []
    for root in roots:
        found.extend(root.find_all(attrs={attr: True}))
    return found


def extract_by_key(soup, profile):
    attr, tpl = profile["video_key_attr"], profile["video_url_template"]
    results, seen = [], set()
    for el in key_elements(soup, profile):
        key = str(el.get(attr, "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", key):
            continue
        link = tpl.replace("{key}", key)
        link = link if re.match(r"^https?://", link) else profile["base_url"].rstrip("/") + link
        if link in seen:
            continue
        seen.add(link)
        results.append((link, _find_duration(el, profile), find_title(el, key), _find_views(el, profile)))
    return results


def extract(html, page_url, profile):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    if (profile.get("exclude_selector") or "").strip():
        for el in soup.select(profile["exclude_selector"]):
            el.decompose()
    if profile["video_key_attr"]:
        return extract_by_key(soup, profile), soup.find_all("a", href=True)
    link_re = re.compile(profile["video_link_regex"])
    results, seen = [], set()
    anchors = soup.find_all("a", href=True)
    if (profile.get("scope_selector") or "").strip():      # only the videos inside this box count
        inside = {id(a) for root in soup.select(profile["scope_selector"]) for a in root.find_all("a", href=True)}
        anchors = [a for a in anchors if id(a) in inside]
    for a in anchors:
        raw = urljoin(page_url, a["href"]).split("#")[0]
        base, _, query = raw.partition("?")
        if profile["keep_query"]:
            target = urlparse(base).path + ("?" + query if query else "")
            if not (link_re.search(target) or link_re.search(urlparse(base).path)):
                continue
            full = raw if query else base.rstrip("/") + "/"
        else:
            if not link_re.search(urlparse(base).path):
                continue
            full = base.rstrip("/") + "/"
        if full in seen:
            continue
        seen.add(full)
        dur, views = None, None
        parent = a.find_parent(["div", "article", "li", "figure"])
        if parent:
            for node in parent.find_all(string=True):
                dur = duration_seconds(node, profile["duration_regex"])
                if dur is not None:
                    break
            views = _find_views(parent, profile)
        results.append((full, dur, find_title(a), views))
    return results, anchors


def categorise(link, profile, title=""):
    slug = ("%s %s" % (link, title)).lower()
    for neg in profile["negative"]:
        if neg.lower() in slug:
            return "Other"
    dom = profile.get("dominant") or ""
    order = ([dom] if dom in profile["keywords"] else []) + [c for c in profile["keywords"] if c != dom]
    for cat in order:
        for kw in profile["keywords"][cat]:
            if kw.lower() in slug:
                return cat
    return "Other"


def fmt(dur):
    return "??" if dur is None else "%d:%02d" % (dur // 60, dur % 60)


# ───────────── finding a creator by name ─────────────

def name_variants(name):
    """'Jane Doe' -> {'name': 'jane-doe', 'compact': 'janedoe', 'underscore': 'jane_doe'}"""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", re.sub(r"['\u2019`]", "", s))
    return {"name": "-".join(words), "compact": "".join(words), "underscore": "_".join(words)}


def creator_slug_from_name(name):
    return name_variants(name)["underscore"]


def expand_pattern(pattern, name, base_url):
    v = name_variants(name)
    out = pattern.strip()
    for k, val in v.items():
        out = out.replace("{%s}" % k, val)
    if out.startswith("/"):
        out = base_url.rstrip("/") + out
    return out


def _page_facts(html):
    """-> (<title> text, lowercase visible text) of a page"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    title = clean_title(soup.title.get_text(" ")) if soup.title else ""
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return title, re.sub(r"\s+", " ", soup.get_text(" ")).lower()


def not_found_hit(profile, title, text):
    """The phrase that marks a 'no such page' page (the site's own wording, or a 404 title), else None."""
    hit = next((ph for ph in (profile.get("not_found_text") or []) if ph.strip() and ph.strip().lower() in text), None)
    if not hit and re.search(r"\b404\b|not found", title.lower()):
        hit = "title says '%s'" % title[:40]
    return hit


def fetch_probe(profile, url, session=None):
    """Load a creator's page 1. -> dict(n=videos, msg, title, links=set of video links, soft404=phrase or None)"""
    first_url, scope, _label = expand_sections(profile, url)[0]
    profile = dict(profile, scope_selector=scope)
    base_path, _, extra, slash = parse_url(first_url, profile)
    return load_page(profile, build_page_url(profile, base_path, 1, extra, slash), session)


def load_page(profile, page_url, session=None):
    """Load one exact page address and describe it."""
    import requests
    out = dict(n=0, msg="", title="", links=set(), soft404=None, loaded=False)
    try:
        r = fetch(session or requests.Session(), page_url)
    except requests.HTTPError as e:
        out["msg"] = "HTTP %s" % (e.response.status_code if e.response is not None else "error")
        return out
    except Exception as e:
        out["msg"] = str(e)[:80]
        return out
    out["loaded"] = True
    wanted, got = urlparse(page_url).path.rstrip("/").lower(), urlparse(r.url).path.rstrip("/").lower()
    if r.history and got != wanted:
        out["msg"] = "redirected to %s" % (urlparse(r.url).path or "/")
        return out
    title, text = _page_facts(r.text)
    out["title"] = title
    hit = not_found_hit(profile, title, text)
    items, _ = extract(r.text, page_url, profile)
    out["links"] = {i[0] for i in items}
    if hit:
        out["soft404"] = hit
        out["msg"] = "the page says it wasn't found (%s), even though it shows %d other videos" % (hit, len(items)) if items \
            else "the page says it wasn't found (%s)" % hit
        return out
    out["n"] = len(items)
    out["msg"] = "%d videos" % len(items) if items else "page loads but no videos found"
    return out


def probe(profile, url, session=None):
    """Does this creator page exist and list videos? -> (video_count, message)"""
    r = fetch_probe(profile, url, session)
    return r["n"], r["msg"]


_CONTROL = {}   # (base url, pattern) -> (time, probe result for a creator that can't exist)
CONTROL_NAME = "zzqx no such creator 4821"


def same_as_missing_page(profile, pattern, found, session):
    """Some sites show the same filler page for any unknown name, with no 'not found' wording. Ask for a name that
    can't exist and compare: same page title, or mostly the same videos, means this isn't a real creator."""
    key = (profile["base_url"], pattern)
    hit = _CONTROL.get(key)
    if not hit or time.time() - hit[0] > 600:
        hit = (time.time(), fetch_probe(profile, expand_pattern(pattern, CONTROL_NAME, profile["base_url"]), session))
        _CONTROL[key] = hit
    ctl = hit[1]
    if not ctl["loaded"] or ctl["msg"].startswith("redirected"):
        return None                       # the site answers an unknown name with a real error: nothing to compare
    if found["title"] and found["title"] == ctl["title"]:
        return "same page title as the site's 'not found' page (%s)" % found["title"][:40]
    if found["links"] and ctl["links"]:
        overlap = len(found["links"] & ctl["links"]) / float(min(len(found["links"]), len(ctl["links"])))
        if overlap >= 0.5:
            return "it lists the same videos as the site's 'not found' page"
    return None


def find_creator(profile, name, say=print, should_stop=lambda: False):
    """Try each address pattern in order; stop at the first that works. -> (url, video_count) or None"""
    import requests
    profile = with_defaults(profile)
    patterns = [p for p in profile["creator_patterns"] if p.strip()]
    if not creator_slug_from_name(name):
        say("✗ '%s' has no usable letters or numbers" % name)
        return None
    session = requests.Session()
    seen = []
    for i, pat in enumerate(patterns, 1):
        if should_stop():
            return None
        url = expand_pattern(pat, name, profile["base_url"])
        if url in seen:
            continue
        seen.append(url)
        res = fetch_probe(profile, url, session)
        n, msg = res["n"], res["msg"]
        if n:
            why = same_as_missing_page(profile, pat, res, session)
            if why:
                n, msg = 0, "not a real creator: " + why
        say("  [%d/%d] %s  ->  %s %s" % (i, len(patterns), url, "✓" if n else "✗", msg))
        if n:
            return url, n
        if i < len(patterns):
            time.sleep(min(float(profile["request_delay"]), 1.0))
    return None


# ───────────── profile picture ─────────────

AVATAR_ATTRS = ("src", "data-src", "data-original", "data-lazy-src", "content")
AVATAR_MAX_BYTES = 8 * 1024 * 1024


def _alnum(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def find_avatar(html, page_url, profile, names=()):
    """-> (image address or None, note). Looks at every element the selector matches. With one match, that is
    the picture. With several (e.g. a 'related creators' row), only one whose alt text matches the creator's
    name is used, and otherwise none, rather than risk someone else's photo."""
    from bs4 import BeautifulSoup
    sel = (profile.get("avatar_selector") or "").strip()
    if not sel:
        return None, "no profile picture selector set for this site"
    soup = BeautifulSoup(html, "html.parser")
    try:
        els = soup.select(sel)
    except Exception as e:
        return None, "the selector isn't valid: %s" % e
    attrs = [profile.get("avatar_attr") or "src"] + [a for a in AVATAR_ATTRS if a != (profile.get("avatar_attr") or "src")]

    def address(el):
        for a in attrs:
            v = (el.get(a) or "").strip()
            if v and not v.startswith("data:"):
                return urljoin(page_url, v.split(" ")[0] if a == "srcset" else v)
        return None

    cands = [(el, address(el)) for el in els]
    cands = [(el, u) for el, u in cands if u]
    if not cands:
        return None, "the selector matched %d element(s) but none has an image address" % len(els)
    if len(cands) == 1:
        return cands[0][1], "1 match"
    wanted = [n for n in (_alnum(x) for x in names) if len(n) >= 4]
    for el, u in cands:
        alt = _alnum(el.get("alt") or el.get("title") or "")
        if alt and any(w == alt or w in alt or alt in w for w in wanted if len(alt) >= 4):
            return u, "%d matches, picked the one whose alt text matches the name" % len(cands)
    return None, "%d matches and none has the creator's name as its alt text, so none was used" % len(cands)


def download_avatar(session, address, referer, dest_stem):
    """Save the image next to the links file. -> file name or None (never raises)."""
    import requests
    try:
        r = session.get(requests.utils.requote_uri(address), timeout=20, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not ctype.startswith("image/"):
            print("  Profile picture: not an image (%s)" % (ctype or "unknown type"))
            return None
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > AVATAR_MAX_BYTES:
                print("  Profile picture: too large, skipped")
                return None
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif"}.get(ctype, ".jpg")
        out = Path(dest_stem + ext)
        out.write_bytes(data)
        return out.name
    except Exception as e:
        print("  Profile picture: download failed (%s)" % e)
        return None


def _title_key(t):
    return re.sub(r"\s+", " ", re.sub(r"\d+|page", "", str(t).lower())).strip(" -|:")


def looks_missing(ctl, first_title, first_links, title, links):
    """Is this later page really the site's 'no such page' filler? ctl = what the site shows for page 99999.
    -> reason or None. Nothing to compare when the site answers an impossible page number with something that looks
    like the creator's own page (it just repeats the last page): the 'nothing new' check handles that case."""
    if not ctl["loaded"] or ctl["msg"].startswith("redirected") or not ctl["links"]:
        return None
    if _title_key(ctl["title"]) == _title_key(first_title):
        return None
    if first_links and len(ctl["links"] & first_links) / float(min(len(ctl["links"]), len(first_links))) >= 0.5:
        return None
    if title and _title_key(title) == _title_key(ctl["title"]):
        return "same page title as the site's 'no such page' page (%s)" % title[:40]
    if links and len(links & ctl["links"]) / float(min(len(links), len(ctl["links"]))) >= 0.5:
        return "it lists the same videos as the site's 'no such page' page"
    return None


# ───────────── commands ─────────────

def run_find_test(profile, name):
    if not profile["creator_patterns"]:
        print("This site has no creator addresses to try yet. Add some above first.")
        return 2
    print("Looking for '%s' (names: %s)" % (name, ", ".join("%s=%s" % kv for kv in name_variants(name).items())))
    hit = find_creator(profile, name)
    if hit:
        print("\nFOUND: %s  (%d videos on page 1)" % hit)
        return 0
    print("\nNone of the %d addresses worked for '%s'." % (len(profile["creator_patterns"]), name))
    return 1



def run_test(profile, url):
    secs = expand_sections(profile, url)
    if len(secs) == 1 and not profile.get("sections"):
        return _run_test_one(profile, url)
    worst = 1
    for u, scope, label in secs:
        print("\n══════ %s  (looking inside: %s) ══════" % (label, scope or "the whole page"))
        rc = _run_test_one(dict(profile, scope_selector=scope), u)
        worst = min(worst, rc)
    return worst


def _run_test_one(profile, url):
    import requests
    base_path, max_page, extra, slash = parse_url(url, profile)
    page_url = build_page_url(profile, base_path, 1, extra, slash)
    print("Fetching page 1: %s" % page_url)
    print("Pages that a scrape of this URL would walk: 1 to %d" % max_page)
    try:
        r = fetch(requests.Session(), page_url)
    except Exception as e:
        print("FAILED to fetch: %s" % e)
        print("-> Check the base URL, and that the path exists on the site.")
        return 1
    print("HTTP %d, %d bytes" % (r.status_code, len(r.content)))
    items, anchors = extract(r.text, page_url, profile)
    if (profile.get("exclude_selector") or "").strip():
        from bs4 import BeautifulSoup
        hits = BeautifulSoup(r.text, "html.parser").select(profile["exclude_selector"])
        plain = dict(profile, exclude_selector="")
        before = len(extract(r.text, page_url, plain)[0])
        print("Ignored: %d element(s) matched your 'ignore' selector, which removed %d video(s) (%d -> %d)" % (len(hits), before - len(items), before, len(items)))
        if not hits:
            print("  -> Nothing on this page matches that selector, so nothing was ignored. Check it in Chrome's Inspect (Copy > Copy selector).")
    with_dur = sum(1 for _, d, *_r in items if d is not None)
    with_views = sum(1 for it in items if it[3] is not None)
    if profile["video_key_attr"]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        everywhere = len(soup.find_all(attrs={profile["video_key_attr"]: True}))
        print("Elements with %s on the page: %d%s" % (profile["video_key_attr"], everywhere,
              " (inside your scope: %d)" % len(key_elements(soup, profile)) if profile["scope_selector"].strip() else ""))
        if everywhere and not len(key_elements(soup, profile)):
            # the attribute is on the page, just not where "only look inside" says: show where it is
            homes = {}
            for el in soup.find_all(attrs={profile["video_key_attr"]: True}):
                node = el.parent
                while node is not None and getattr(node, "name", None) not in (None, "[document]") and not node.get("id"):
                    node = node.parent
                label = "#" + node.get("id") if node is not None and getattr(node, "get", None) and node.get("id") else "(no id on any parent)"
                homes[label] = homes.get(label, 0) + 1
            print("  Your 'only look inside' box matches nothing that holds videos here. The videos on this page sit inside:")
            for label, n in sorted(homes.items(), key=lambda kv: -kv[1]):
                print("    %s  (%d videos)" % (label, n))
            print("  -> Use one of these in 'only look inside' for this page.")
        if not everywhere:
            print("\nNone found in the page the server sent. If you can see it in Chrome's Inspect but not in View Source (Ctrl+U),")
            print("the page builds its list with JavaScript, which this scraper can't read.")
            return 1
    elif not profile["keep_query"]:
        link_re = re.compile(profile["video_link_regex"])
        with_q = sum(1 for a in anchors if "?" in a["href"] and link_re.search(urlparse(urljoin(page_url, a["href"])).path))
        if with_q > len(items) * 2 and with_q > 3:
            print("WARNING: %d video links differ only after the ?, so they collapse into %d. "
                  "Tick 'Keep everything after the ?' in Advanced patterns." % (with_q, len(items)))
    print("Links on page: %d" % len(anchors))
    if (profile.get("avatar_selector") or "").strip():
        addr, note = find_avatar(r.text, page_url, profile, [slug_from_url(url, profile)])
        print("Profile picture: %s  (%s)" % (addr or "none", note))
    print("Matched as videos: %d (with a duration: %d, with a view count: %d)" % (len(items), with_dur, with_views))
    print("Creator name: %s" % slug_from_url(url, profile))
    if items:
        print("\nSample:")
        for link, d, title, views in items[:6]:
            print("  %s  |  %s  |  %s  ->  %s" % (link, fmt(d), "%s views" % format(views, ",") if views is not None else "no views", categorise(link, profile, title)))
            print("      title: %s" % (title or "(none found)"))
        if not any(i[2] for i in items):
            print("\nNo titles found. Links will have no title, so keywords can only match the link itself.")
        if with_dur == 0:
            print("\nNo durations found. Links will be kept as '??'. Check the duration pattern.")
        if with_views == 0:
            print("\nNo view counts found. If the site shows them, put the CSS selector of the number in 'view count selector' (Advanced patterns).")
        return 0
    print("\nNo video links matched. Here are some links the page does contain:")
    seen = set()
    for a in anchors:
        h = urlparse(urljoin(page_url, a["href"]).split("#")[0])
        shown = h.path + ("?" + h.query if h.query else "")
        if shown not in seen and h.path not in ("", "/"):
            seen.add(shown)
            print("  " + shown[:110])
        if len(seen) >= 12:
            break
    print("\n-> Make the 'video link pattern' match the shape of the video links above.")
    print("-> If a video's ID comes after a ? (like /watch?id=123), tick 'Keep everything after the ?' in Advanced patterns.")
    print("-> If the page shows no video links at all, it probably loads them with JavaScript, which this scraper can't do.")
    return 1


def walk_pages(profile, url, creator, all_pages, session, explicit_max, seen, all_items, avatar_done, stats=None):
    """Walk the pages of one address and add what it finds to all_items. -> True once a profile picture is saved."""
    base_path, max_page, extra, slash = parse_url(url, profile)
    if explicit_max:
        max_page = explicit_max
    cap = int(profile["max_auto_pages"]) if all_pages else max_page
    local_seen = set()
    ctl, first_title, first_links = None, "", set()
    for page in range(1, cap + 1):
        page_url = build_page_url(profile, base_path, page, extra, slash)
        print("Scraping page %d%s -> %s" % (page, "" if all_pages else "/%d" % max_page, page_url), flush=True)
        items, error, gone = None, None, None
        for attempt in range(2 if all_pages and page > 1 else 1):   # one retry so a hiccup isn't mistaken for "no more pages"
            try:
                resp = fetch(session, page_url)
                items, _ = extract(resp.text, page_url, profile)
                title, text = _page_facts(resp.text)
                gone = not_found_hit(profile, title, text)          # a normal-looking page that says "not found"
                if not gone and page > 1 and items:
                    if ctl is None:
                        ctl = load_page(profile, build_page_url(profile, base_path, 99999, extra, slash), session)
                    gone = looks_missing(ctl, first_title, first_links, title, {i[0] for i in items})
                if gone:
                    items = []
                elif page == 1:
                    first_title, first_links = title, {i[0] for i in items}
                if page == 1 and not gone and not avatar_done and (profile.get("avatar_selector") or "").strip():
                    addr, note = find_avatar(resp.text, page_url, profile, [slug_from_url(url, profile), creator])
                    if addr:
                        got = download_avatar(session, addr, page_url, "%s_avatar" % creator)
                        avatar_done = bool(got)
                        print("  Profile picture: %s" % ("saved %s" % got if got else "found but not saved"))
                    else:
                        print("  Profile picture: none (%s)" % note)
                break
            except Exception as e:
                error = e
                if attempt == 0 and all_pages and page > 1 and getattr(getattr(e, "response", None), "status_code", None) not in (404, 410):
                    time.sleep(2)
                elif attempt == 0:
                    break
        if items is None:
            print("  Failed to fetch: %s" % error)
            if all_pages:
                code = getattr(getattr(error, "response", None), "status_code", None)
                print("  %s" % ("No page %d, so page %d was the last." % (page, page - 1) if code in (404, 410) and page > 1
                              else "Stopping here (page %d could not be loaded)." % page))
                break
            items = []
        if gone:
            if page > 1:
                print("  Page %d says it wasn't found (%s), so page %d was the last." % (page, gone, page - 1))
            else:
                print("  Page 1 says it wasn't found (%s)." % gone)
            break
        fresh = [i for i in items if i[0] not in local_seen]
        print("  Found %d videos%s" % (len(items), " (%d new)" % len(fresh) if all_pages else ""), flush=True)
        for link, dur, title, views in fresh:
            local_seen.add(link)
            if link not in seen:                 # the same video can be on both of a creator's pages
                seen.add(link)
                all_items.append((link, dur, title, views))
        if all_pages and not fresh:
            print("  Nothing new on this page, so that was the last one.")
            break
        if page < cap:
            time.sleep(float(profile["request_delay"]))
    else:
        if all_pages:
            print("  Reached the safety limit of %d pages." % cap)
    if stats is not None:
        stats["found"] = len(local_seen)
        stats["pages"] = page
    return avatar_done


def run_scrape(profile, url, slug=None, all_pages=False):
    import requests
    base_path, max_page, extra, slash = parse_url(url, profile)
    has_page = _parse(url, profile)[3]
    creator = slug or slug_from_url(url, profile)
    out = Path("%s_links.txt" % creator)
    print("Creator   : %s" % creator)
    print("Base path : %s" % creator_root(base_path, profile))
    print("Pages     : %s\n" % ("all of them (stops when a page has nothing new, at most %d)" % int(profile["max_auto_pages"]) if all_pages else "1 -> %d" % max_page))

    session = requests.Session()
    all_items, seen, avatar_done = [], set(), False
    secs = expand_sections(profile, url)
    for n, (sec_url, scope, label) in enumerate(secs, 1):
        if len(secs) > 1:
            print("%s── part %d of %d: %s ──" % ("\n" if n > 1 else "", n, len(secs), label))
        before, stats = len(all_items), {}
        avatar_done = walk_pages(dict(profile, scope_selector=scope), sec_url, creator, all_pages, session,
                                 max_page if has_page else None, seen, all_items, avatar_done, stats)
        if len(secs) > 1:
            added, found = len(all_items) - before, stats.get("found", 0)
            print("  %s: found %d video%s on this page%s, %d added%s" % (
                label, found, "" if found == 1 else "s", "" if found != 1 else "",
                added, "" if added == found else " (%d already collected from an earlier part)" % (found - added)))
        if n < len(secs):
            time.sleep(float(profile["request_delay"]))

    print("\nTotal unique videos found: %d" % len(all_items))
    if not all_items:
        print("Found 0 videos (blocked, wrong URL, or the page layout doesn't match this site profile).")
        print("Existing file '%s' was NOT overwritten." % out)
        return 1

    cats = defaultdict(list)
    cat_order = list(profile["keywords"].keys()) + ["Other"]
    lines = ["=== ALL LINKS (%d) ===" % len(all_items)]
    def row(link, dur, title, views=None):
        # the view count, when there is one, goes last as "@@views=N" so older readers still see url | length | title
        return "%s  |  %s%s%s" % (link, fmt(dur), "  |  " + title if title else "", "  @@views=%d" % views if views is not None else "")
    for link, dur, title, views in all_items:
        lines.append(row(link, dur, title, views))
        cats[categorise(link, profile, title)].append((link, dur, title, views))
    lines += ["", "", "=== CATEGORISED ==="]
    for cat in cat_order:
        lines += ["", "--- %s (%d) ---" % (cat, len(cats[cat]))]
        lines += [row(l, d, ti, v) for l, d, ti, v in cats[cat]]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nDone! Saved -> %s" % out)
    for cat in cat_order:
        print("  %-12s: %d" % (cat, len(cats[cat])))
    return 0


def main(argv):
    if "--profile-file" not in argv:
        print(__doc__)
        return 2
    args = list(argv)
    i = args.index("--profile-file")
    profile = with_defaults(json.loads(Path(args[i + 1]).read_text(encoding="utf-8")))
    del args[i:i + 2]
    slug = None
    if "--slug" in args:
        j = args.index("--slug")
        slug = args[j + 1]
        del args[j:j + 2]
    if "--find-name" in args:
        j = args.index("--find-name")
        return run_find_test(profile, args[j + 1])
    test = "--test" in args
    all_pages = "--all-pages" in args
    rest = [a for a in args if a not in ("--test", "--all-pages")]
    if not rest:
        print("No URL given.")
        return 2
    return run_test(profile, rest[-1]) if test else run_scrape(profile, rest[-1], slug, all_pages)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
