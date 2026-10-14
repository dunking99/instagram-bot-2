"""Reads what the data18 scraper has already saved (read-only; never contacts data18 and never changes the scraper's files)."""
import ast
import glob
import html
import json
import os
import re
import urllib.error
import urllib.request

RESULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data18", "data", "results")
SESSION = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data18", "data", "session.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def as_list(value):
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            return [str(v) for v in ast.literal_eval(value)]
        except (ValueError, SyntaxError):
            pass
    return [value] if value else []


def clean(text):
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def from_link(link):
    """A data18 scene link (or just its number) -> {title, performers, studio, date, creator} or None"""
    m = re.search(r"scenes/(\d+)", link) or re.fullmatch(r"\s*(\d{5,})\s*", link)
    if not m:
        return None
    sid = m.group(1)
    for path in sorted(glob.glob(os.path.join(RESULTS, "*.json"))):
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        for v in (data.get("videos") if isinstance(data, dict) else data) or []:
            if str(v.get("scene_id")) == sid:
                creator = os.path.basename(path)[:-5]
                owner = clean(creator.replace("-", " ")).title()          # data18 leaves the page's own performer out of the list, so add her back
                perfs = [clean(p) for p in as_list(v.get("performers"))]
                if owner and owner.lower() not in [p.lower() for p in perfs]:
                    perfs.insert(0, owner)
                return dict(title=clean(v.get("title")), performers=perfs, studio=clean(v.get("studio")),
                            date=v.get("date") or "", scene_id=sid, creator=creator)
    return None


def _cookie_header():
    try:
        with open(SESSION) as f:
            cookies = json.load(f).get("cookies", [])
    except (OSError, ValueError):
        return None
    return "; ".join("%s=%s" % (c["name"], c["value"]) for c in cookies if "data18" in (c.get("domain") or "data18"))


def parse_scene(page):
    """One data18 scene page -> {title, performers, studio, date, duration (seconds or 0)} (fixed patterns).
    The heading cuts long titles off with '...', so the full title is taken from the <title> tag when that happens.
    The description comes in two shapes: '... Scene by <studios> Starring: <cast>. ...' and '... Scene by <studios> w/ <cast>. ...'"""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)))
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    title = clean(html.unescape(re.sub(r"<[^>]+>", "", h1.group(1)))) if h1 else ""
    tt = re.search(r"<title>(.*?)</title>", page, re.S)
    if tt:
        full = clean(html.unescape(tt.group(1)))
        full = re.sub(r"\s*\|\s*DATA18\s*$", "", full)
        full = re.sub(r",?\s+w/\s.*$", "", full)                      # ", w/ Kiara Cole (2021) Porn Scene" -> gone
        full = re.sub(r"\s*\(\d{4}\)\s*(?:Porn Scene)?\s*$", "", full).strip()
        if not title or (title.endswith("...") and full.startswith(title[:-3].rstrip())):
            title = full or title
    meta = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', page)
    desc = html.unescape(meta.group(1)) if meta else ""
    m = re.search(r"Scene by\s+(.*?)\.?\s+(?:Starring:|w/)\s+(.*?)\.\s", desc + " ")
    studio, performers = "", []
    if m:
        studio = clean(m.group(1).split(",")[0])
        performers = [clean(x) for x in m.group(2).split(",") if clean(x)]
    else:
        star = re.search(r"Starring:\s*(.*?)\.\s", desc + " ")
        performers = [clean(x) for x in star.group(1).split(",") if clean(x)] if star else []
    date = re.search(r"Release date\s*:\s*([A-Za-z]+ \d+, \d{4})", text)
    dur = re.search(r"Duration:\s*(?:(\d+)\s*hours?,?\s*)?(?:(\d+)\s*min)?,?\s*(?:(\d+)\s*sec)?", text)
    seconds = (int(dur.group(1) or 0) * 3600 + int(dur.group(2) or 0) * 60 + int(dur.group(3) or 0)) if dur else 0
    return dict(title=title, performers=performers, studio=studio, date=date.group(1) if date else "", duration=seconds)


def fetch_scene(sid):
    """-> (dict, error). One request to the scene page on data18."""
    cookie = _cookie_header()
    if cookie is None:
        return None, "No saved data18 session (the data18 scraper's session.json)."
    req = urllib.request.Request("https://www.data18.com/scenes/" + sid, headers={"User-Agent": UA, "Cookie": cookie, "Referer": "https://www.data18.com/"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            page = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return None, "data18 answered HTTP %d for that scene." % e.code
    except Exception as e:
        return None, "Couldn't reach data18: %s" % getattr(e, "reason", e)
    scene = parse_scene(page)
    if not scene["title"]:
        return None, "That page didn't look like a data18 scene (the saved age-check session may have expired: rerun setup_session.py in the scraper)."
    scene.update(scene_id=sid, creator="")
    return scene, None


def from_text(text):
    """'Title - Performer, Performer' -> the same dict (the last ' - ' separates the performers)."""
    text = clean(text)
    if " - " in text:
        title, perf = text.rsplit(" - ", 1)
    else:
        title, perf = text, ""
    perfs = [clean(p) for p in re.split(r"\s*(?:,|&| and )\s*", perf) if clean(p)]
    return dict(title=clean(title), performers=perfs, studio="", date="", scene_id="", creator="")


def parse_input(text):
    """-> (dict, error). Accepts a data18 scene link / number (any scene, read live from data18), or 'Title - Performer'."""
    text = (text or "").strip()
    if not text:
        return None, "Type a data18 scene link or 'Title - Performer'."
    if re.search(r"data18\.com|^\d{5,}$", text):
        m = re.search(r"scenes/(\d+)", text) or re.fullmatch(r"\s*(\d{5,})\s*", text)
        if not m:
            return None, "That doesn't look like a data18 scene link (it should contain /scenes/ and a number)."
        scene, err = fetch_scene(m.group(1))
        if scene:
            return scene, None
        saved = from_link(text)                                # data18 didn't answer: fall back to what the scraper saved, if it has it
        if saved:
            saved["duration"] = 0
            return saved, None
        return None, err
    found = from_text(text)
    found["duration"] = 0
    return found, None
