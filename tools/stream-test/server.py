"""Stream test: play freepornvideos.xxx videos straight from the site, nothing saved.
Standalone. Python 3.9 stdlib only.   python3 server.py  ->  http://127.0.0.1:8793
"""
import json, re, shutil, subprocess, sys, threading, time, urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor
from html import unescape as html_unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST, PORT = "127.0.0.1", 8793
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
HERE = Path(__file__).parent


SITES = {   # page hosts that may be opened (the video address is read from the page); only freepornvideos accepts a bare ID
    "freepornvideos.xxx": "https://www.freepornvideos.xxx/videos/%s/x/",
    "fpo.xxx": None, "porntrex.com": None, "xozilla.com": None, "porneec.com": None, "playvids.com": None, "pornflip.com": None,
    "tnaflix.com": None, "xhamster.com": None, "youporn.com": None, "xxxbunker.com": None, "eporner.com": None, "pornhub.com": None,
    "trendyporn.com": None, "youcrazyx.com": None, "yrprno.com": None,
}
KVS = {"freepornvideos.xxx", "fpo.xxx", "porntrex.com", "xozilla.com"}      # sites whose player block lists every quality (read by parse_sources)
NOT_STREAMABLE = {
    "porngrey.net": "its video files answer 'error' to anything but its own player (they are protected); not worked around",
    "shyfap.net": "its video files answer 'error' to anything but its own player (they are protected); not worked around",
    "pornzog.com": "the page only embeds another site's player (videotxxx.com), so there is no video file on the page",
}
YTDLP_FIRST = {"tnaflix.com", "youporn.com", "pornhub.com", "eporner.com", "xxxbunker.com"}   # crowded pages full of other videos' previews: ask yt-dlp straight away
ISSUED = {}            # every video address handed to the page -> the headers it needs (the proxy and ffmpeg only fetch these)
MIN_VIDEO_BYTES = 5_000_000


def site_of(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    for k in list(SITES) + list(NOT_STREAMABLE):
        if host == k or host == "www." + k:
            return k
    return None


def quality_of(label):
    m = re.search(r"(\d{3,4})\s*p", label or "")
    return int(m.group(1)) if m else None


def parse_sources(html):
    """[{label, quality, url}] from a KVS player block (video_url, video_alt_url, video_alt_url2 ...) or <source> get_file links."""
    out = []
    for m in re.finditer(r"video_(alt_)?url(\d?)\s*:\s*'(https?://[^']+)'", html):
        t = re.search(r"video_%surl%s_text\s*:\s*'([^']+)'" % (m.group(1) or "", m.group(2)), html)
        label = t.group(1) if t else "?"
        out.append({"label": label, "quality": quality_of(label), "url": m.group(3)})
    if not out:
        for url, q in re.findall(r"""["'](https?://[^"'?]+/get_file/[^"'?]+?_(\d+)m\.mp4/)["']""", html):
            out.append({"label": q + "p", "quality": int(q), "url": url})
    if all(o["quality"] for o in out):
        out.sort(key=lambda o: o["quality"])
    return out


PAGE_SOURCES = {"tnaflix.com", "porneec.com", "playvids.com", "pornflip.com"}   # the page itself names the video file: read it straight from the page
FFMPEG_HEADERS = {}      # HLS address -> headers only ffmpeg sends when taking frames (the browser plays these with no referrer, so they are not "issued" headers)


def _attr(tag, name):
    m = re.search(r"""\b%s\s*=\s*(?:"([^"]*)"|'([^']*)')""" % name, tag)
    return html_unescape(m.group(1) if m.group(1) is not None else m.group(2)) if m else ""


def parse_page_sources(page, page_url):
    """[{label, quality, url}] named by the page itself: <source> tags (tnaflix: one mp4 per size; playvids and pornflip: an HLS playlist)
    or a contentUrl (porneec: one plain mp4). Checked in a real Chrome (play_test.py, 2026-10-14): all four play and seek straight from these
    addresses with no referrer. Plain mp4s come lowest quality first, then any HLS playlist."""
    text = page.replace("\\/", "/")
    mp4, hls = [], []

    def add(bucket, url, label, quality=None):
        if url.startswith("http") and url not in [o["url"] for o in mp4 + hls]:
            bucket.append({"label": label, "quality": quality, "url": url})

    tags = re.findall(r"<source\b[^>]*>", text, re.I)
    for tag in tags[:12]:                                         # a page with more is crowded with other videos' previews
        src, typ = _attr(tag, "src"), _attr(tag, "type").lower()
        if ".m3u8" in src or "mpegurl" in typ:
            add(hls, src, "HLS (automatic quality)")
        elif ".mp4" in src or typ == "video/mp4":
            size = _attr(tag, "size") or _attr(tag, "label") or _attr(tag, "res")
            add(mp4, src, ("%sp" % size) if size.isdigit() else (size or "mp4"), int(size) if size.isdigit() else None)
    for m in re.finditer(r"""itemprop=["']contentUrl["'][^>]*content=["']([^"']+)["']|content=["']([^"']+)["'][^>]*itemprop=["']contentUrl["']""", text):
        u = html_unescape(m.group(1) or m.group(2))
        if re.search(r"\.mp4(\?|$)", u):
            add(mp4, u, "mp4")
    if all(o["quality"] for o in mp4):
        mp4.sort(key=lambda o: o["quality"])
    for o in hls:
        FFMPEG_HEADERS[o["url"]] = {"Referer": page_url}          # frames only: ffmpeg is told which page it came from
    return mp4 + hls


PREVIEW_WORDS = re.compile(r"preview|thumb|trailer|teaser|sprite|_th_|/th/|/gifs?/|promo", re.I)


def head_info(url, headers=None):
    """(status, total bytes) of a partial read of the first bytes; the video must really answer partial reads."""
    h = {"User-Agent": UA, "Range": "bytes=0-99"}
    h.update(headers or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=25) as r:
            cr = r.headers.get("Content-Range") or ""
            total = int(cr.split("/")[-1]) if "/" in cr and cr.split("/")[-1].isdigit() else int(r.headers.get("Content-Length") or 0)
            ok = r.status == 206 and (r.headers.get("Content-Type", "").startswith(("video/", "application/octet")))
            return (r.status if ok else 0), total
    except Exception:
        return 0, 0


def own_scan(html, page_url):
    """Plain .mp4 addresses on the page that really are videos (answer partial reads, 5 MB or more) -> [{label, quality, url}]"""
    text = html.replace("\\/", "/")
    found = []
    for u in re.findall(r"https?://[^\"'\s<>\\]+?\.mp4[^\"'\s<>\\]*", text):
        if not PREVIEW_WORDS.search(u) and u not in found:
            found.append(u)
    if not found or len(found) > 8:                       # none, or a page crowded with other videos' previews
        return []
    out = []
    for u in found:
        status, total = head_info(u)
        if status and total >= MIN_VIDEO_BYTES:
            m = re.search(r"(\d{3,4})\s*[pP]\b|[-_/](\d{3,4})\.mp4|(\d{3,4})[pP]_", u)
            q = int(next(g for g in m.groups() if g)) if m else None
            out.append({"label": ("%dp" % q if q else "%d MB" % (total // 1_000_000)), "quality": q, "url": u, "size": total})
    out.sort(key=lambda o: (o["quality"] or 0, o["size"]))
    return out


YT_CACHE = {}


def ytdlp_sources(page_url):
    """Ask yt-dlp (it knows many sites' players) -> ({duration, sources}, error). Plain https mp4 files only (no HLS/DASH)."""
    hit = YT_CACHE.get(page_url)
    if hit and time.time() - hit[0] < 600:
        return hit[1], None
    exe = shutil.which("yt-dlp") or "/opt/homebrew/bin/yt-dlp"
    try:
        r = subprocess.run([exe, "-J", "--no-warnings", "--no-playlist", page_url], capture_output=True, text=True, timeout=120)
    except Exception as e:
        return None, "yt-dlp could not run: %s" % e
    if r.returncode:
        return None, (r.stderr.strip().splitlines() or ["yt-dlp found nothing"])[-1][:160]
    j = json.loads(r.stdout)
    seen, best = set(), {}
    for f in j.get("formats", []):
        if f.get("url") and f.get("protocol") in ("https", "http") and f.get("ext") == "mp4" and f.get("vcodec") != "none" and f["url"] not in seen:
            seen.add(f["url"])
            q = f.get("height")
            key = q or f["url"]                              # the same height offered in two encodings: keep H.264 (plays in every browser)
            h264 = str(f.get("vcodec") or "").startswith("avc")
            if key not in best or (h264 and not best[key][1]):
                best[key] = ({"label": ("%dp" % q if q else "%s" % (f.get("format_note") or f.get("format_id") or "mp4")), "quality": q, "url": f["url"],
                              "headers": dict({k: v for k, v in (f.get("http_headers") or {}).items() if k.lower() in ("referer", "cookie")}, Referer=page_url)}, h264)
    out = [v[0] for v in best.values()]
    if out and not any(o["quality"] for o in out):            # no heights given (xxxbunker): label by file size instead
        for o in out[:8]:
            _, total = head_info(o["url"], o.get("headers"))
            o["size"] = total
            o["label"] = "%d MB" % (total // 1_000_000) if total else o["label"]
        out = [o for o in out[:8] if o.get("size", 1) >= MIN_VIDEO_BYTES]
        out.sort(key=lambda o: o.get("size", 0))
        out = [o for i, o in enumerate(out) if i == 0 or o.get("size") != out[i - 1].get("size")]      # the same file listed twice
    else:
        out.sort(key=lambda o: o["quality"] or 0)
    res = {"duration": int(j["duration"]) if j.get("duration") else None, "sources": out}
    YT_CACHE[page_url] = (time.time(), res)
    return res, None


def page_duration(html):
    for pat in (r'duration"\s+content="(\d+)"', r"duration:\s*'(\d+)'", r'"duration"\s*:\s*"P?(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"', r'video:duration"\s+content="(\d+)"',
                r'itemprop="duration"\s+content="P?(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"', r'data-duration="(\d+)"'):
        m = re.search(pat, html)
        if m:
            g = m.groups()
            if len(g) == 3:
                sec = int(g[0] or 0) * 3600 + int(g[1] or 0) * 60 + int(g[2] or 0)
            else:
                sec = int(g[0])
            if sec >= 30:
                return sec
    return None


def fetch_info(v):
    v = v.strip()
    if re.fullmatch(r"\d{5,10}", v):                      # bare ID: freepornvideos only
        url = SITES["freepornvideos.xxx"] % v
    else:
        url = v if "://" in v else "https://" + v
    site = site_of(url)
    if site in NOT_STREAMABLE:
        raise ValueError("%s cannot be streamed: %s." % (site, NOT_STREAMABLE[site]))
    if not site:
        raise ValueError("Supported sites: " + ", ".join(SITES) + " (paste the video page link; a bare ID means freepornvideos)")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace").replace("&amp;", "&")
        page_url = r.geturl()
    vid = (re.search(r"/(?:videos?)/(\d+)", page_url) or re.search(r"(\d{6,10})", page_url) or re.search(r"([A-Za-z0-9_-]{6,})/?$", page_url.split("?")[0].rstrip("/") + "/")).group(1)
    title = re.search(r'property="og:title"\s+content="([^"]*)"', html) or re.search(r"<title>([^<]*)</title>", html)
    duration = page_duration(html)
    sources, how = [], "player block"
    if site in KVS:
        sources = parse_sources(html)
    else:
        if site in PAGE_SOURCES:
            sources, how = parse_page_sources(html, page_url), "page source"
        if not sources and site not in YTDLP_FIRST:
            sources, how = own_scan(html, page_url), "page scan"
        if not sources:
            yt, err = ytdlp_sources(page_url)
            if yt:
                sources, how = yt["sources"], "yt-dlp"
                duration = duration or yt["duration"]
            elif not sources:
                raise ValueError("no video file could be read from this page (%s)" % err)
        if not sources:
            raise ValueError("no video file could be read from this page")
        for o in sources:                                   # only these addresses may be fetched by the proxy / frame maker
            ISSUED[o["url"]] = o.get("headers") or {}
    for o in sources:
        ISSUED.setdefault(o["url"], o.get("headers") or {})
    while len(ISSUED) > 2000:
        ISSUED.pop(next(iter(ISSUED)))
    nums = [int(n) for n in re.findall(r"/%s/player/(\d+)\.jpg" % re.escape(vid), html)]
    base = re.search(r"(https://img\.freepornvideos\.xxx/\d+/%s)/" % re.escape(vid), html)
    return {
        "id": vid, "site": site, "page": page_url, "read_with": how,
        "title": re.split(r" [|/] ", (title.group(1) if title else "").strip())[0],
        "duration": duration,
        "sources": [dict({k: o[k] for k in ("label", "quality", "url")}, needs_proxy=bool(o.get("headers"))) for o in sources],
        "frames": max(nums) if nums else 0,
        "frame_base": (base.group(1) + "/player/") if base else None,
    }


FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FRAMES = HERE / "frames"
JOBS = {}                      # job id -> status dict (this run only; the files stay on disk until deleted)
MAX_FRAMES = 600
WORKERS = {"fpo.xxx": 3, "trendyporn": 3, "youcrazyx": 3, "yrprno": 3, "xxxbunker": 2}      # parallel frames per site (default 6); fpo.xxx refused some requests at 6
DEFAULT_WORKERS = 6


def resolve_final(url):
    """Follow the site's redirects once, so every frame does not repeat them (about 3 s saved per frame)."""
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA, "Range": "bytes=0-0"}, **(ISSUED.get(url) or {})))
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.geturl()
        except urllib.error.URLError:
            if attempt == 3:
                raise
            time.sleep(2 * attempt)


def grab(job, final, sec, height):
    out = job["dir"] / ("f_%05d.jpg" % sec)
    hdr = "".join("%s: %s\r\n" % kv for kv in (job.get("headers") or {}).items())
    cmd = [FFMPEG, "-v", "error", "-y", "-user_agent", UA, "-probesize", "500000", "-analyzeduration", "0"] + (["-headers", hdr] if hdr else []) + ["-ss", str(sec), "-i", final,
           "-frames:v", "1", "-vf", "scale=-2:%d" % height, "-q:v", "3", str(out)]
    for attempt in (1, 2, 3):
        if job["cancel"]:
            return
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            if r.returncode and r.stderr.strip():
                job["last_error"] = r.stderr.strip().splitlines()[-1][:160]
        except subprocess.TimeoutExpired:
            job["last_error"] = "ffmpeg took too long"
        if out.exists() and out.stat().st_size > 0:
            job["done"] += 1
            job["files"].append(sec)
            return
        time.sleep(attempt)
    job["failed"] += 1


def run_frames(job, url, secs, height):
    workers = WORKERS.get(job["site"], DEFAULT_WORKERS)
    try:
        final = resolve_final(url)
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(lambda t: grab(job, final, t, height), secs))
        job["state"] = "cancelled" if job["cancel"] else "done"
    except Exception as e:
        job["state"], job["error"] = "error", str(e)
    job["seconds"] = round(time.time() - job["t0"], 1)


def start_frames(q):
    g = lambda k, d=None: (q.get(k) or [d])[0]
    info = fetch_info(g("v", ""))
    srcs = info["sources"]
    i = int(g("q", 0))
    if not 0 <= i < len(srcs):
        raise ValueError("quality number out of range")
    dur = float(g("dur") or info["duration"] or 0)
    if dur <= 0:
        raise ValueError("this video's length is unknown; open it in the player first")
    every = max(2.0, float(g("every", 10)))
    start = max(0.0, float(g("start", 0)))
    end = float(g("end") or 0) or dur
    end = min(end, dur - 1)
    height = int(g("height", 224))
    secs = []
    t = start
    while t <= end and len(secs) < MAX_FRAMES:
        secs.append(int(t))
        t += every
    if not secs:
        raise ValueError("nothing to take: check the from/to times")
    jid = "%s_%s_%d" % (info["site"].split(".")[0], info["id"], int(time.time()))
    d = FRAMES / jid
    d.mkdir(parents=True, exist_ok=True)
    job = dict(id=jid, dir=d, state="running", total=len(secs), done=0, failed=0, files=[], cancel=False, t0=time.time(),
               title=info["title"], site=info["site"], quality=srcs[i]["label"], every=every, error=None, last_error="", headers=ISSUED.get(srcs[i]["url"]) or FFMPEG_HEADERS.get(srcs[i]["url"]) or {})
    JOBS[jid] = job
    threading.Thread(target=run_frames, args=(job, srcs[i]["url"], secs, height), daemon=True).start()
    return jid


def frames_status(jid):
    job = JOBS.get(jid)
    if not job:
        raise ValueError("unknown job (the server restarted?)")
    return {k: (sorted(v) if k == "files" else v) for k, v in job.items() if k not in ("dir", "t0", "cancel")} | \
        {"elapsed": round(time.time() - job["t0"], 1) if job["state"] == "running" else job.get("seconds")}



class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            b = (HERE / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif u.path == "/api/info":
            try:
                self.send_json(fetch_info(q.get("v", [""])[0]))
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
        elif u.path == "/api/frames/start":
            try:
                self.send_json({"job": start_frames(q)})
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
        elif u.path == "/api/frames/status":
            try:
                self.send_json(frames_status(q.get("job", [""])[0]))
            except Exception as e:
                self.send_json({"error": str(e)}, 404)
        elif u.path == "/api/frames/cancel":
            j = JOBS.get(q.get("job", [""])[0])
            if j:
                j["cancel"] = True
            self.send_json({"ok": bool(j)})
        elif u.path == "/api/frames/delete":
            jid = q.get("job", [""])[0]
            if re.fullmatch(r"[a-z0-9]+_\d+_\d+", jid) and (FRAMES / jid).is_dir():
                if jid in JOBS:
                    JOBS[jid]["cancel"] = True
                shutil.rmtree(FRAMES / jid, ignore_errors=True)
                JOBS.pop(jid, None)
            self.send_json({"ok": True})
        elif u.path.startswith("/frames/"):
            m = re.fullmatch(r"/frames/([a-z0-9]+_\d+_\d+)/(f_\d{5}\.jpg)", u.path)
            f = FRAMES / m.group(1) / m.group(2) if m else None
            if not f or not f.is_file():
                return self.send_error(404)
            b = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif u.path == "/proxy":
            self.proxy(q.get("u", [""])[0])
        else:
            self.send_error(404)

    def proxy(self, target):
        # only addresses this tool read from a supported site's page (not an open proxy)
        if target not in ISSUED:
            return self.send_error(403)
        headers = {"User-Agent": UA}
        headers.update(ISSUED.get(target) or {})
        if self.headers.get("Range"):
            headers["Range"] = self.headers["Range"]
        try:
            r = urllib.request.urlopen(urllib.request.Request(target, headers=headers), timeout=30)
        except urllib.error.HTTPError as e:
            return self.send_error(e.code)
        except Exception as e:
            sys.stderr.write("proxy error %s: %r\n" % (target[:80], e))
            sys.stderr.flush()
            return self.send_error(502)
        self.send_response(r.status)
        for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
            if r.headers.get(h):
                self.send_header(h, r.headers[h])
        self.end_headers()
        try:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            r.close()


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
