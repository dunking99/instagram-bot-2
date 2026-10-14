#!/usr/bin/python3
"""Video Finder: give it a data18 scene (or 'Title - Performer'); it searches the sites and shows the best match on each, with thumbnails.

    ./start.sh            then open http://127.0.0.1:8792

Standalone: it does not touch the Light table, the data18 scraper or any other tool. It only READS the scraper's saved results
to look up a data18 link. Everything is fixed rules (see matcher.py and rules.json), no AI. Python 3.9, standard library only.
"""
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import data18   # noqa: E402
import matcher  # noqa: E402
import sites    # noqa: E402

PORT = int(os.environ.get("FINDER_PORT", "8792"))
JOBS_DIR = os.path.join(HERE, "data", "jobs")
JOBS = {}
LOCK = threading.Lock()
IMG_CACHE = {}


# ---------------------------------------------------------------- the search
def parse_length(value):
    """'44:47' (min:sec), '45' or 45 (minutes), '' -> seconds (0 = unknown)"""
    text = str(value or "").strip()
    try:
        if ":" in text:
            m, sec = text.split(":", 1)
            return int(m) * 60 + int(sec)
        return int(float(text) * 60) if text else 0
    except ValueError:
        return 0


def build_queries(want, rules):
    """The search ladder with the blanks filled in -> [{q, pages, deep}]
    pages = result pages read in the main pass (normally 1); deep = extra pages read only if the main pass found nothing."""
    perfs = want.get("performers") or []
    stop = set(rules["stopwords"])
    core_words = [w for w in want.get("title", "").split() if matcher.tokens(w) and not all(t in stop for t in matcher.tokens(w))]
    fill = {"title": want.get("title") or "", "title_core": " ".join(core_words), "title_key": " ".join(core_words[:3]),
            "performer": perfs[0] if perfs else "", "performers": " ".join(perfs), "studio": want.get("studio") or ""}
    out = []
    for item in rules["search_ladder"]:
        pattern, pages, deep, extra = (item, 1, 0, False) if isinstance(item, str) else (item.get("q", ""), int(item.get("pages", 1)), int(item.get("deep", 0)), bool(item.get("extra")))
        needed = [k for k in fill if "{%s}" % k in pattern]
        if any(not fill[k] for k in needed):
            continue                                               # e.g. no performer known: skip the queries that need one
        q = " ".join(pattern.format(**fill).split())
        if q and q.lower() not in [x["q"].lower() for x in out]:
            out.append({"q": q, "pages": max(0, min(pages, 10)), "deep": max(0, min(deep, 9)), "extra": extra})
    return out


def rank_site(st, want, rules):
    """Rank one site's results so far with the current rules.json (no new requests); sets st["results"] and st["keep"]."""
    pool = {}
    for qi, q in enumerate(st["queries"]):
        for c in q["cards"]:
            e = pool.setdefault(c["url"], dict(c, found_by=[]))
            e["found_by"].append(qi + 1)
    ranked = []
    for c in pool.values():
        pts, why = matcher.score(c, want, rules)
        if pts > -900:                                             # -999 = too short, left out
            ranked.append(dict(c, score=pts, why=why))
    ranked.sort(key=lambda x: (-x["score"], -(x.get("duration") or 0)))
    seen_same, unique = set(), []
    for c in ranked:                                               # the same video listed more than once (same title and length) appears once
        key = (tuple(matcher.tokens(c["title"])), c.get("duration"))
        if key not in seen_same:
            seen_same.add(key)
            unique.append(c)
    ranked = unique
    st["results"] = dict(verdict=matcher.verdict(ranked, rules), ranked=ranked[:8], total=len(pool), left_out=len(pool) - len(ranked))
    st["keep"] = [c["url"] for c in ranked[:25]]                   # the only candidates a saved copy needs (results, thumbnails, re-scoring)


def search_site(job, site, rules):
    """Main pass: the main queries, page 1 only, stopping as soon as this site has a confident match.
    If that found nothing: the extra queries (only on rules["extra_sites"]), then the deep pages (only on rules["deep_sites"])."""
    st = job["sites"][site]
    stop_early = bool(rules.get("stop_when_confident", 1))
    limit = int(rules.get("max_requests_per_site", 14))
    max_pages = sites.SITES[site].get("max_pages", 99)
    deep_ok = bool(rules.get("deep_when_nothing", 1)) and (not rules.get("deep_sites") or site in rules["deep_sites"])
    qs = job["queries"]
    main = [(i, p) for i, item in enumerate(qs) if not item["extra"] for p in range(1, item["pages"] + 1)]
    extra = [(i, p) for i, item in enumerate(qs) if item["extra"] for p in range(1, item["pages"] + 1)]
    deep = [(i, p) for i, item in enumerate(qs) if not item["extra"] for p in range(item["pages"] + 1, item["pages"] + item.get("deep", 0) + 1)]
    extra_ok = not rules.get("extra_sites") or site in rules["extra_sites"]
    seen, exhausted = {}, set()

    def go(i, page, n_total):
        item = job["queries"][i]
        if i in exhausted or page > max_pages:
            return False
        label = item["q"] + (" (page %d)" % page if page > 1 else "")
        st.update(state="searching", message="search %d: %s" % (len(st["queries"]) + 1, label))
        cards, err, url = sites.search(site, item["q"], page)
        st["queries"].append({"q": label, "url": url, "error": err, "count": len(cards), "cards": cards})
        if err and not cards:
            st["error"] = err
            return err.startswith(("HTTP 403", "HTTP 429"))        # refused: do not keep asking
        fresh = {c["url"] for c in cards} - seen.setdefault(i, set())
        seen[i] |= {c["url"] for c in cards}
        if not fresh:                                              # an empty or repeated page: this query has run out
            exhausted.add(i)
        rank_site(st, job["want"], rules)
        return False

    def confident():
        return stop_early and bool(st.get("results")) and st["results"]["verdict"] == "confident"

    def run(plan):
        for i, page in plan:
            if len(st["queries"]) >= limit or confident():
                return False
            if go(i, page, len(plan)):
                return True                                        # refused: stop asking this site
        return False

    def nothing():
        return (st.get("results") or {}).get("verdict") in (None, "none")

    refused = run(main)
    if not refused and extra_ok and nothing():
        refused = run(extra)
    if not refused and deep_ok and nothing():
        run(deep)
    ok = any(not x["error"] for x in st["queries"])
    st["state"] = "done" if ok else "error"
    st["message"] = "" if ok else (st.get("error") or "no answer")
    if not st.get("results"):
        rank_site(st, job["want"], rules)


def strong(res):
    """A match good enough to stop looking at the other sites: confident, or likely with real title evidence (the whole title, or at least 60% of its words) AND the same length as data18's.
    A performer's name plus a similar length is not enough: she has many videos of about the same length."""
    if not res or not res.get("ranked"):
        return False
    if res["verdict"] == "confident":
        return True
    if res["verdict"] != "possible":
        return False
    why = res["ranked"][0].get("why", [])
    length = any(w.startswith("length") and " matches " in w for w in why)
    title = False
    for w in why:
        if w.startswith("title phrase found"):
            title = True
        m = re.match(r"(\d+) of (\d+) title words found", w)
        if m and int(m.group(1)) >= 0.6 * int(m.group(2)):
            title = True
    return length and title


def skip_site(job, site, why):
    job["sites"][site].update(state="done", message=why, skipped=True, queries=[], keep=[], results=dict(verdict="none", ranked=[], total=0, left_out=0))


def run_job(job):
    rules = matcher.load_rules()
    names = list(sites.SITES)
    first = [s for s in names if s in sites.STREAMABLE] if rules.get("streamable_first", 1) and not job.get("all_sites") else names
    rest = [s for s in names if s not in first]
    with ThreadPoolExecutor(len(names)) as pool:
        list(pool.map(lambda s: search_site(job, s, rules), first))
        if rest:
            if (rules.get("streamable_only") or job.get("streamable_only")) and not job.get("all_sites"):
                for s in rest:
                    skip_site(job, s, "not searched: only the streamable sites are searched (rules.json: streamable_only)")
            elif any(strong(job["sites"][s].get("results")) for s in first):
                for s in rest:
                    skip_site(job, s, "not searched: a streamable site already has a match (confident, or likely with the same length)")
            else:
                list(pool.map(lambda s: search_site(job, s, rules), rest))
    rescore(job)
    job["state"] = "done"
    save(job)


def rescore(job):
    """Rank every site's results with the current rules.json (no new requests)."""
    rules = matcher.load_rules()
    for site, st in job["sites"].items():
        if not st.get("skipped"):
            rank_site(st, job["want"], rules)


def save(job):
    """Write the search to disk, keeping only each site's top candidates (a full copy is ~700 KB, a slim one ~100 KB), so hundreds can be kept."""
    try:
        os.makedirs(JOBS_DIR, exist_ok=True)
        slim = json.loads(json.dumps(job))
        for st in slim["sites"].values():
            keep = set(st.get("keep") or [])
            if keep:
                for q in st["queries"]:
                    q["cards"] = [c for c in q["cards"] if c["url"] in keep]
        with open(os.path.join(JOBS_DIR, job["id"] + ".json"), "w") as f:
            json.dump(slim, f)
        for old in sorted(os.listdir(JOBS_DIR))[:-400]:            # keep the last 400 searches
            os.remove(os.path.join(JOBS_DIR, old))
    except OSError:
        pass


def get_job(jid):
    with LOCK:
        if jid in JOBS:
            return JOBS[jid]
    try:
        with open(os.path.join(JOBS_DIR, os.path.basename(jid) + ".json")) as f:
            job = json.load(f)
    except (OSError, ValueError):
        return None
    with LOCK:
        JOBS[jid] = job
    return job


def start_job(want, all_sites=False, streamable_only=False):
    rules = matcher.load_rules()
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    job = dict(id=jid, want=want, all_sites=bool(all_sites), streamable_only=bool(streamable_only), queries=build_queries(want, rules), state="running", started=time.time(),
               sites={s: dict(state="waiting", message="", queries=[], results=None) for s in sites.SITES})
    with LOCK:
        JOBS[jid] = job
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return job


def public(job):
    """The job as the page needs it (thumbnails go through /img, raw cards are left out)."""
    def card(c):
        out = {k: c.get(k) for k in ("url", "title", "duration", "score", "why", "found_by", "full")}
        out["thumb"] = "/img?id=%s&u=%s" % (job["id"], urllib.parse.quote(c["thumb"], safe="")) if c.get("thumb") else ""
        return out
    out = dict(id=job["id"], want=job["want"], queries=[q["q"] + (" (extra: streamable sites, if nothing found)" if q.get("extra") else " (+%d pages if nothing found)" % q["deep"] if q.get("deep") else "") for q in job["queries"]], all_sites=job.get("all_sites", False), state=job["state"], sites={}, unavailable=sites.UNAVAILABLE)
    for s, st in job["sites"].items():
        res = st.get("results")
        out["sites"][s] = dict(state=st["state"], message=st["message"], skipped=bool(st.get("skipped")), streamable=s in sites.STREAMABLE,
                               queries=[{k: q[k] for k in ("q", "url", "error", "count")} for q in st["queries"]],
                               verdict=res["verdict"] if res else None, total=res["total"] if res else 0, left_out=res["left_out"] if res else 0,
                               ranked=[card(c) for c in res["ranked"]] if res else [])
    return out


def fetch_image(job, url):
    site = next((s for s, st in job["sites"].items() for q in st["queries"] for c in q["cards"] if c.get("thumb") == url), None)
    if not site:
        return None                                                # only thumbnails that came from a search result are fetched
    if url in IMG_CACHE:
        return IMG_CACHE[url]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": sites.UA, "Referer": sites.SITES[site]["home"], "Accept": "image/*,*/*"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data, ctype = r.read(3_000_000), r.headers.get("Content-Type", "image/jpeg")
    except Exception:
        return None
    if len(IMG_CACHE) > 400:
        IMG_CACHE.clear()
    IMG_CACHE[url] = (data, ctype)
    return IMG_CACHE[url]


# ---------------------------------------------------------------- the web server
class Handler(BaseHTTPRequestHandler):
    server_version = "VideoFinder"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _local_only(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        if host not in ("127.0.0.1", "localhost"):
            return False
        if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host"):
            return False                                           # other websites cannot drive this tool
        return True

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        if not self._local_only():
            return self._send(403, {"error": "Local use only."})
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "static", "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/job":
            job = get_job((q.get("id") or [""])[0])
            return self._send(200, public(job)) if job else self._send(404, {"error": "No such search."})
        if u.path == "/api/rules":
            return self._send(200, matcher.load_rules())
        if u.path == "/img":
            job = get_job((q.get("id") or [""])[0])
            got = fetch_image(job, (q.get("u") or [""])[0]) if job else None
            return self._send(200, got[0], got[1], {"Cache-Control": "max-age=3600"}) if got else self._send(404, b"", "text/plain")
        self._send(404, {"error": "Not found."})

    def do_POST(self):
        if not self._local_only():
            return self._send(403, {"error": "Local use only."})
        u, body = urllib.parse.urlparse(self.path), self._body()
        if u.path == "/api/search":
            if body.get("title") is not None:                      # fields edited on the page
                perfs = body.get("performers") or []
                if isinstance(perfs, str):
                    perfs = [p.strip() for p in perfs.split(",") if p.strip()]
                want = dict(title=str(body.get("title")).strip(), performers=perfs, studio=str(body.get("studio") or "").strip(),
                            date=body.get("date") or "", scene_id=body.get("scene_id") or "", creator=body.get("creator") or "",
                            duration=parse_length(body.get("duration")))
                err = None if want["title"] else "A title is needed."
            else:
                want, err = data18.parse_input(body.get("input"))
            if err:
                return self._send(400, {"error": err})
            return self._send(200, public(start_job(want, bool(body.get("all_sites")), bool(body.get("streamable_only")))))
        if u.path == "/api/rescore":
            job = get_job(body.get("id") or "")
            if not job:
                return self._send(404, {"error": "No such search."})
            if job["state"] != "done":
                return self._send(409, {"error": "Wait until the search has finished."})
            rescore(job)
            save(job)
            return self._send(200, public(job))
        if u.path == "/api/rules":
            try:
                rules = matcher.check_rules(body.get("rules"))
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            with open(matcher.RULES_FILE, "w") as f:
                json.dump(rules, f, indent=2)
            return self._send(200, matcher.load_rules())
        self._send(404, {"error": "Not found."})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("Video Finder on http://127.0.0.1:%d" % PORT, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
