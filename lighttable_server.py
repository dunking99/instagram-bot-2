#!/usr/bin/env python3
"""Light table: a second face for the Postroom.

Serves the interface in ui-lighttable/dist and passes every /api request straight through to the running Postroom
(default http://127.0.0.1:8503). So both interfaces show exactly the same videos, frames, favourites and jobs, and anything
you do in one shows up in the other. The Postroom itself (server.py and ui/) is not touched or changed.

    python3 lighttable_server.py                 # http://localhost:8504
    LIGHTTABLE_PORT=8600 python3 lighttable_server.py
    POSTROOM_URL=http://127.0.0.1:8503 python3 lighttable_server.py

Standard library only.
"""
import http.client
import json
import subprocess
import time
import uuid
import mimetypes
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "ui-lighttable", "dist")
PORT = int(os.environ.get("LIGHTTABLE_PORT", "8504"))
TARGET = urllib.parse.urlparse(os.environ.get("POSTROOM_URL", "http://127.0.0.1:8503"))
REVIEW_PORTS = [int(p) for p in os.environ.get("REVIEW_PORTS", "8777,8765").split(",")]    # where the model dashboard may be running
REVIEW_PY = os.path.join(HERE, "CLIP Training", ".venv", "bin", "python")
_start_lock = __import__("threading").Lock()
D18_DIR = os.path.expanduser("~/data18-scraper")                    # the data18 scraper (its own folder, its own python)
D18_PY = os.path.join(D18_DIR, ".venv", "bin", "python")
D18_PORT = int(os.environ.get("D18_PORT", "8790"))
REMOTE_FRAMES = os.path.join(HERE, "remote_frames.py")              # frames from a video link without downloading the video
FRAMES = {}                                                         # job id -> {"proc", "status", "started", "url"}
_tool_env = dict(os.environ, PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", PYTHONUNBUFFERED="1")


def _up_path(port, path, timeout=1.5):
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        c.request("GET", path)
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except Exception:
        return False


def ensure_data18():
    """Make sure the data18 scraper's server is running (start it like start_all.sh would). Returns an error text, or None."""
    if _up_path(D18_PORT, "/api/status"):
        return None
    with _start_lock:
        if _up_path(D18_PORT, "/api/status"):
            return None
        if not os.path.exists(D18_PY):
            return "The data18 scraper could not be started: ~/data18-scraper/.venv is missing."
        os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
        log = open(os.path.join(HERE, "logs", "data18.log"), "ab")
        subprocess.Popen([D18_PY, "-u", "server.py"], cwd=D18_DIR, env=_tool_env, stdout=log, stderr=log, start_new_session=True)
        for _ in range(40):
            time.sleep(0.5)
            if _up_path(D18_PORT, "/api/status"):
                return None
    return "The data18 scraper did not start in time. Check logs/data18.log."


def frames_start(body):
    url = str(body.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Paste the video's page link (it has to start with http:// or https://).")
    every = max(1.0, min(60.0, float(body.get("every") or 5)))
    height = int(body.get("height") or 480)
    jid = uuid.uuid4().hex[:10]
    os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
    status = os.path.join(HERE, "logs", f"frames-{jid}.json")
    cmd = [sys.executable, REMOTE_FRAMES, "--url", url, "--every", str(every), "--height", str(height), "--status", status]
    start, end = float(body.get("startSeconds") or 0), float(body.get("endSeconds") or 0)
    if start < 0 or end < 0 or (end and end <= start):
        raise ValueError("The end of the section has to be after its start.")
    if start:
        cmd += ["--start-seconds", str(start)]
    if end:
        cmd += ["--end-seconds", str(end)]
    if body.get("limitMinutes"):
        cmd += ["--limit-minutes", str(float(body["limitMinutes"]))]
    FRAMES[jid] = {"proc": None, "cmd": cmd, "status": status, "started": time.time(), "url": url}     # waits here until a slot is free
    for old in sorted(FRAMES, key=lambda k: FRAMES[k]["started"])[:-30]:       # keep the last few dozen
        if FRAMES[old]["proc"] is not None and FRAMES[old]["proc"].poll() is not None:
            FRAMES.pop(old, None)
    frames_pump()
    return jid


MAX_FRAME_JOBS = int(os.environ.get("FRAMES_MAX_JOBS", "3"))              # videos taken at the same time; more wait in line (be polite to the site)
_frames_lock = __import__("threading").Lock()


def frames_pump():
    """Start waiting videos, oldest first, while fewer than MAX_FRAME_JOBS are running."""
    with _frames_lock:
        running = sum(1 for j in FRAMES.values() if j["proc"] is not None and j["proc"].poll() is None)
        for jid, j in sorted(FRAMES.items(), key=lambda kv: kv[1]["started"]):
            if j["proc"] is not None:
                continue
            if running >= MAX_FRAME_JOBS:
                break
            log = open(os.path.join(HERE, "logs", f"frames-{jid}.log"), "ab")
            j["proc"] = subprocess.Popen(j["cmd"], cwd=HERE, env=_tool_env, stdout=log, stderr=log, start_new_session=True)
            j["began"] = time.time()
            running += 1


def frames_state(jid):
    frames_pump()                                                       # a finished video frees a slot for the next one
    job = FRAMES.get(jid)
    if not job:
        return None
    if job["proc"] is None:
        ahead = sum(1 for k, j in FRAMES.items() if j["proc"] is None and j["started"] < job["started"])
        running = sum(1 for j in FRAMES.values() if j["proc"] is not None and j["proc"].poll() is None)
        return {"id": jid, "url": job["url"], "phase": "queued", "running": False, "started": job["started"], "progress": 0,
                "message": "Waiting its turn: %d video%s being taken now, %d ahead in line." % (running, "" if running == 1 else "s", ahead)}
    try:
        with open(job["status"]) as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        st = {"phase": "starting"}
    running = job["proc"].poll() is None
    if not running and st.get("phase") not in ("done", "error"):
        st = dict(st, phase="error", error=st.get("error") or "The frame grabber stopped unexpectedly. See logs/frames-%s.log." % jid)
    return dict(st, id=jid, url=job["url"], running=running, started=job.get("began", job["started"]))


def _up(port, timeout=1.5):
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        c.request("GET", "/api/list")
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except Exception:
        return False


def review_url():
    """The model dashboard's address. If it is not running, start it (the same way start_all.sh does) and wait for it."""
    if os.environ.get("REVIEW_URL"):
        return os.environ["REVIEW_URL"].rstrip("/"), None
    for p in REVIEW_PORTS:
        if _up(p):
            return f"http://localhost:{p}", None
    with _start_lock:
        for p in REVIEW_PORTS:
            if _up(p):
                return f"http://localhost:{p}", None
        port = REVIEW_PORTS[-1]
        if not os.path.exists(REVIEW_PY):
            return None, "The model dashboard could not be started: CLIP Training/.venv is missing."
        log = open(os.path.join(HERE, "logs", "review.log"), "ab")
        subprocess.Popen([REVIEW_PY, "-u", "scripts/review_server.py"], cwd=os.path.join(HERE, "CLIP Training"),
                         env=dict(os.environ, REVIEW_PORT=str(port)), stdout=log, stderr=log, start_new_session=True)
        for _ in range(60):
            time.sleep(0.5)
            if _up(port):
                return f"http://localhost:{port}", None
    return None, "The model dashboard did not start in time. Check logs/review.log."


HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "host"}
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LightTable/1"

    def log_message(self, fmt, *args):                      # one short line per API error only (see proxy)
        return

    # ---------- static files ----------
    def _static(self, head_only=False):
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        rel = os.path.normpath(path.lstrip("/"))
        full = os.path.join(DIST, rel)
        if not os.path.abspath(full).startswith(os.path.abspath(DIST)):
            return self._json(403, {"detail": "No."})
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            if "." in os.path.basename(rel):                   # a missing asset is a 404; any other path is the app (single page)
                return self._json(404, {"detail": "Not found"})
            full = os.path.join(DIST, "index.html")
        if not os.path.isfile(full):
            return self._json(503, {"detail": "The Light table interface has not been built yet. Run: cd ui-lighttable && npx vite build"})
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        size = os.path.getsize(full)
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
        self.send_header("Content-Length", str(size))
        hashed = "/assets/" in path or path.startswith("/fonts/")
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if hashed and "/assets/" in path else "no-cache")
        self.end_headers()
        if not head_only:
            with open(full, "rb") as fh:
                while True:
                    chunk = fh.read(1 << 16)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # ---------- the pass-through to the Postroom ----------
    def _proxy(self, host=None, port=None, path=None):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host"):    # only pages this server itself served (blocks other sites)
            return self._json(403, {"detail": "Cross-site request refused."})
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP | {"origin", "referer"}}    # the Postroom only accepts localhost origins
        host, port = host or TARGET.hostname, port or (TARGET.port or 80)
        headers["Host"] = "%s:%s" % (host, port)
        headers["Accept-Encoding"] = "identity"
        try:
            conn = http.client.HTTPConnection(host, port, timeout=600)
            conn.request(self.command, path or self.path, body=body, headers=headers)
            resp = conn.getresponse()
        except Exception as e:                              # the Postroom is not running, or died
            return self._json(502, {"detail": f"Can't reach the server on {host}:{port} ({type(e).__name__}). Start it first (start_all.sh)."})
        try:
            self.send_response(resp.status, resp.reason)
            clen = resp.getheader("Content-Length")
            for k, v in resp.getheaders():
                if k.lower() in HOP or k.lower() == "content-length":
                    continue
                self.send_header(k, v)
            no_body = self.command == "HEAD" or resp.status in (204, 304) or 100 <= resp.status < 200
            if clen is not None or no_body:
                if clen is not None:
                    self.send_header("Content-Length", clen)
                self.end_headers()
                if not no_body:
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            else:                                           # unknown length (streamed): pass it on in chunks
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                while True:
                    chunk = resp.read(1 << 14)
                    if not chunk:
                        break
                    self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):     # the browser closed the request (a video seek, a navigation)
            self.close_connection = True
        finally:
            conn.close()

    def _handle(self):
        if self.path.startswith("/api/") or self.path == "/api":
            return self._proxy()
        route = self.path.split("?")[0]
        if route == "/d18":                                                 # the data18 scraper, shown inside the Light table
            self.send_response(301); self.send_header("Location", "/d18/"); self.send_header("Content-Length", "0"); self.end_headers()
            return
        if self.path.startswith("/d18/"):
            if self.headers.get("Sec-Fetch-Site") == "cross-site":          # another website must not drive the scraper
                return self._json(403, {"detail": "Cross-site request refused."})
            err = ensure_data18()
            return self._json(503, {"detail": err}) if err else self._proxy("127.0.0.1", D18_PORT, self.path[4:])
        if route == "/lt/data18":
            err = ensure_data18()
            return self._json(503, {"detail": err}) if err else self._json(200, {"url": "/d18/"})
        if route == "/lt/frames/start" and self.command == "POST":          # frames from a video link, without downloading it
            origin = self.headers.get("Origin")
            if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host"):
                return self._json(403, {"detail": "Cross-site request refused."})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                return self._json(200, {"id": frames_start(body)})
            except (ValueError, TypeError) as e:
                return self._json(400, {"detail": str(e)})
        if route == "/lt/frames/status":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            st = frames_state((q.get("id") or [""])[0])
            return self._json(200, st) if st else self._json(404, {"detail": "No such job."})
        if route == "/lt/frames/list":
            return self._json(200, {"jobs": [frames_state(k) for k in sorted(FRAMES, key=lambda k: -FRAMES[k]["started"])]})
        if self.path.split("?")[0] == "/lt/review":                 # the Light table asks where the model dashboard is
            url, err = review_url()
            return self._json(200, {"url": url}) if url else self._json(503, {"detail": err})
        if self.command in ("GET", "HEAD"):
            return self._static(head_only=self.command == "HEAD")
        return self._json(405, {"detail": "Method not allowed"})

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = _handle


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    print(f"Light table on http://localhost:{PORT}  ->  Postroom at {TARGET.geturl()}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
