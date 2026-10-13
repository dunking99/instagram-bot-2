"""
Postroom: the local web interface for random_post.py.

Run:
    python3 server.py              # serves http://localhost:8503 and opens it in your browser
    python3 server.py --no-open    # don't open the browser
    python3 server.py --rebuild    # rebuild the interface (ui/) first

This is the React interface in ui/. Like app.py and app_v2.py it is a thin front end: searches and
long tasks run random_post.py as a subprocess, so the command line keeps working exactly as before.
It reads and writes the same files (cache/, favourites/, library/, pilot/), so the Streamlit apps
and this one can be used side by side.
"""
from __future__ import annotations

import base64
import csv
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(HERE)

PORT = 8503
DIST = HERE / "ui" / "dist"
CACHE = HERE / "cache"
NOISE = ("NotOpenSSLWarning", "warnings.warn", "use_fast", "urllib3")        # harmless startup chatter
MODELS = ("siglip", "clip")
API_VERSION = 4          # bump when the interface needs a newer server; the page shows a restart banner if they differ
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
CLIP_LENGTHS = {"15 seconds": 15, "30 seconds": 30, "1 minute": 60, "2 minutes": 120,
                "5 minutes": 300, "Full video": 0}
POSE_TAGS = ["standing", "sitting", "kneeling", "lying down", "on all fours",
             "bending over", "leaning", "upper body only"]
HEAVY_KINDS = {"prepare", "index", "import", "import-new", "import-many", "pilot", "index-videos"}   # one at a time


NEEDED = ("fastapi", "uvicorn", "numpy", "PIL", "torch", "transformers", "playwright")


def _missing(python: str | None = None) -> list:
    """Which of the packages this project needs can't be found by `python` (default: the running one)."""
    import importlib.util
    if python is None:
        return [m for m in NEEDED if importlib.util.find_spec(m) is None]
    code = "import importlib.util as u;print(' '.join(m for m in %r if u.find_spec(m) is None))" % (NEEDED,)
    out = subprocess.run([python, "-c", code], capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else list(NEEDED)


def ensure_interpreter() -> None:
    """`python3` can point at a different Python than the one this project's packages were installed into
    (for example Homebrew's after an update). Hand over to one that has them instead of failing."""
    missing = _missing()
    if not missing:
        return
    seen = {os.path.realpath(sys.executable)}
    for cand in ("/usr/bin/python3", "/Library/Developer/CommandLineTools/usr/bin/python3",
                 shutil.which("python3.9"), shutil.which("python3.10"), shutil.which("python3.11"),
                 shutil.which("python3.12"), shutil.which("python3.13")):
        if cand and os.path.exists(cand) and os.path.realpath(cand) not in seen:
            seen.add(os.path.realpath(cand))
            if not _missing(cand):
                print(f"{sys.executable} is missing {', '.join(missing)}; using {cand} instead.")
                os.execv(cand, [cand, *sys.argv])
    sys.exit(f"This Python ({sys.executable}) is missing: {', '.join(missing)}.\n"
             f"Run the server with the Python that has them, e.g. /usr/bin/python3 server.py, "
             f"or install them in a virtual environment:\n"
             f"  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt")


def main_cli() -> None:
    ensure_interpreter()
    args = sys.argv[1:]
    if "--rebuild" in args or not (DIST / "index.html").exists():
        build_ui()
    try:
        import uvicorn
    except ImportError:
        sys.exit("The web server isn't installed. Run: python3 -m pip install fastapi uvicorn python-multipart")
    port = int(args[args.index("--port") + 1]) if "--port" in args else PORT
    if "--no-open" not in args:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    print(f"Postroom is running at http://localhost:{port}   (Ctrl+C to stop)")
    uvicorn.run("server:app", host="127.0.0.1", port=port, log_level="warning")


def build_ui() -> None:
    """Build ui/ into ui/dist (needs Node.js). Done automatically the first time."""
    ui = HERE / "ui"
    if not shutil.which("npm"):
        sys.exit("The interface hasn't been built and Node.js isn't installed. Install Node.js, then run "
                 "`python3 server.py --rebuild` (or `cd ui && npm install && npm run build`).")
    print("Building the interface (first run, about a minute)...")
    if not (ui / "node_modules").exists():
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=ui, check=True)
    subprocess.run(["npm", "run", "build"], cwd=ui, check=True)


if __name__ == "__main__":
    main_cli()
    sys.exit(0)


from fastapi import Body, FastAPI, HTTPException, Query, Request                  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response                 # noqa: E402
from fastapi.staticfiles import StaticFiles                                        # noqa: E402

import photos_import as pi                                                         # noqa: E402
import random_post as rp                                                           # noqa: E402

app = FastAPI(title="Postroom")


@app.middleware("http")
async def local_only(request: Request, call_next):
    """This server controls files and a logged-in browser: only answer pages served from this Mac."""
    host = request.headers.get("host", "").split(":")[0]
    origin = request.headers.get("origin", "")
    if host not in ("localhost", "127.0.0.1", "[::1]") or (
            origin and not re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", origin)):
        return JSONResponse({"detail": "Local requests only."}, status_code=403)
    return await call_next(request)


def fail(code: int, msg: str):
    raise HTTPException(status_code=code, detail=msg)


# =====================================================================================
# Files, thumbnails and downloads
# =====================================================================================
_served: set = set()          # files outside the project folder that this server has handed out a link for


def under_here(path: Path) -> bool:
    try:
        path.resolve().relative_to(HERE)
        return True
    except ValueError:
        return False


def rel(path) -> str:
    p = Path(path).resolve()
    return p.relative_to(HERE).as_posix() if under_here(p) else str(p)


def media_url(path, w: int | None = None) -> str:
    """A link the page can use for an image or video file (registered if it lives outside the project)."""
    p = Path(path)
    try:
        v = int(p.stat().st_mtime)
    except OSError:
        v = 0
    if not under_here(p):
        _served.add(str(p.resolve()))
    q = f"/api/file?p={quote(rel(p))}&v={v}" + (f"&w={w}" if w else "")
    return q


def thumb_url(account: str, name: str, w: int = 560) -> str:
    return f"/api/thumb/{quote(account.lower())}/{quote(name)}.jpg?w={w}"


def resolve_media(p: str) -> Path:
    path = Path(p)
    path = (path if path.is_absolute() else HERE / path).resolve()
    if path.suffix.lower() not in MEDIA_EXT or not path.is_file():
        fail(404, "Not found")
    if not under_here(path) and str(path) not in _served:
        fail(403, "That file isn't available")
    return path


@lru_cache(maxsize=2500)
def _resized(path: str, mtime: float, w: int) -> bytes:
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((w, int(w * 1.25)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return buf.getvalue()


def serve_image(path: Path, w: int | None):
    if w and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        try:
            data = _resized(str(path), path.stat().st_mtime, max(64, min(int(w), 2400)))
            return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})
        except Exception:
            pass
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/file")
def get_file(p: str, w: Optional[int] = None, v: Optional[int] = None):
    return serve_image(resolve_media(p), w)


@app.get("/api/thumb/{account}/{name}.jpg")
def get_thumb(account: str, name: str, w: Optional[int] = 560):
    if not re.fullmatch(r"[\w.-]+", account) or not re.fullmatch(r"[\w@.-]+", name):
        fail(404, "Not found")
    path = rp.THUMB_DIR / account.lower() / f"{name}.jpg"
    if not path.is_file():
        fail(404, "No saved image")
    return serve_image(path, w)


@app.get("/api/download")
def download(p: str, name: Optional[str] = None):
    path = resolve_media(p)
    return FileResponse(path, filename=name or path.name, media_type="application/octet-stream")


def reveal_path(path) -> None:
    subprocess.run(["open", "-R", str(path)])


@app.post("/api/reveal")
def reveal(body: dict = Body(...)):
    p = Path(str(body.get("path", ""))).expanduser()
    if not p.exists():
        fail(404, "That file or folder is no longer there.")
    if p.is_dir():
        subprocess.run(["open", str(p)])
    else:
        reveal_path(p)
    return {"ok": True}


@app.post("/api/open-folder")
def open_folder(body: dict = Body(...)):
    p = Path(str(body.get("path", ""))).expanduser()
    p = p if p.is_absolute() else HERE / p
    if not p.exists():
        fail(404, "That folder doesn't exist yet.")
    subprocess.run(["open", str(p)])
    return {"ok": True}


# =====================================================================================
# Small cached readers
# =====================================================================================
def _mtime(f: Path) -> float:
    try:
        return f.stat().st_mtime
    except OSError:
        return 0


@lru_cache(maxsize=96)
def _json_cached(path: str, mtime: float):
    return json.loads(Path(path).read_text())


def read_json(path: Path, default=None):
    try:
        return _json_cached(str(path), _mtime(path))
    except (OSError, ValueError):
        return default


def local_sources(account: str) -> dict:
    d = read_json(CACHE / f"{account.lower()}.local.json", {})
    return d.get("source", {}) if isinstance(d, dict) else {}


@lru_cache(maxsize=64)
def _video_frames_cached(path: str, mtime: float) -> frozenset:
    return frozenset(json.loads(Path(path).read_text()).get("frames", {}))


def video_frames(account: str) -> frozenset:
    f = CACHE / f"{account.lower()}.videos.json"
    try:
        return _video_frames_cached(str(f), _mtime(f))
    except (OSError, ValueError):
        return frozenset()


# =====================================================================================
# Accounts
# =====================================================================================
def index_files(account: str, model: str) -> list:
    names = [model] + [m for m in MODELS if m != model]
    return [f for f in (CACHE / f"{account}.{m}.npz" for m in names) if f.exists()]


@lru_cache(maxsize=512)
def _index_posts(account: str, stamp) -> tuple:
    try:
        import numpy as np
        f = next(f for f in (CACHE / f"{account}.{m}.npz" for m in MODELS) if f.exists())
        return tuple(str(p) for p in np.load(f, allow_pickle=False)["paths"] if "/@" not in str(p))
    except (OSError, ValueError, KeyError, StopIteration):
        return ()


def _acct_stamp(account: str) -> tuple:
    return tuple(_mtime(CACHE / f"{account}.{s}") for s in
                 ("siglip.npz", "clip.npz", "json", "kinds.json", "expanded.json", "pose.npz", "local.json"))


@lru_cache(maxsize=512)
def _account_stats(account: str, stamp: tuple) -> dict:
    """The expensive part of an account's row, cached until its files change."""
    posts = _index_posts(account, stamp)
    links = read_json(CACHE / f"{account}.json", {}) or {}
    n = len(links.get("links", [])) if isinstance(links, dict) else 0
    kinds = (read_json(CACHE / f"{account}.kinds.json", {}) or {}).get("kinds", {})
    done = (read_json(CACHE / f"{account}.expanded.json", {}) or {}).get("posts", {})
    todo = [p for p in posts if not re.search(r"/(reel|reels)/", p) and kinds.get(p, "carousel") == "carousel"]
    return {"posts": n or len(posts),
            "opened": sum(1 for p in todo if p in done), "toOpen": len(todo) if posts else 0,
            "extraSlides": sum(max(v.get("slides", 1) - 1, 0) for v in done.values()) if posts else 0}


_covers: dict = {}


def cover_for(account: str):
    if account in _covers:
        return _covers[account]
    out = None
    try:
        with os.scandir(rp.THUMB_DIR / account.lower()) as it:
            for e in it:
                if e.name.endswith(".jpg") and "@" not in e.name:
                    out = thumb_url(account, e.name[:-4], 96)
                    break
    except OSError:
        pass
    if out:
        _covers[account] = out
    return out


_AUX_JSON = re.compile(r"\.(kinds|expanded(\.w\d+)?|local|folders|videos|watch)\.json$")
_INDEX_FILE = re.compile(r"^(.+)\.(siglip|clip|pose)\.npz$")


def account_names() -> set:
    """Every account or collection we hold data for. Usernames may contain dots (talitha.balinska)."""
    names = set()
    for f in CACHE.iterdir():
        m = _INDEX_FILE.match(f.name)
        if m and m.group(2) != "pose":
            names.add(m.group(1))
        elif f.name.endswith(".json") and not _AUX_JSON.search(f.name):
            names.add(f.name[:-5])
    names.discard("settings")
    return names


def account_rows() -> list:
    names = account_names()
    rows = []
    watched = set(rp.watched_collections())
    for name in sorted(names):
        stamp = _acct_stamp(name)
        st = _account_stats(name, stamp)
        models = {m: (CACHE / f"{name}.{m}.npz").exists() for m in MODELS}
        row = {"handle": name, "kind": "local" if (CACHE / f"{name}.local.json").exists() else "instagram",
               "posts": st["posts"], "videos": 0, "models": models,
               "pose": (CACHE / f"{name}.pose.npz").exists(),
               "carouselDetected": (CACHE / f"{name}.kinds.json").exists(),
               "opened": st["opened"], "toOpen": st["toOpen"], "extraSlides": st["extraSlides"],
               "prepared": None, "libraryBuilt": (HERE / "library" / name).exists(),
               "cover": cover_for(name)}
        stamps = [_mtime(CACHE / f"{name}.{m}.npz") for m in MODELS if models[m]]
        if stamps:
            row["prepared"] = datetime.date.fromtimestamp(max(stamps)).isoformat()
        if name in watched:
            row["videos"] = len(rp.load_watch(name)["videos"])
        rows.append(row)
    for name in sorted(watched - names):
        w = rp.load_watch(name)
        if w["attached"]:
            continue
        rows.append({"handle": name, "kind": "videos", "posts": len(w["videos"]), "videos": len(w["videos"]),
                     "models": {m: True for m in MODELS}, "pose": False, "carouselDetected": True,
                     "opened": 0, "toOpen": 0, "extraSlides": 0, "prepared": None, "libraryBuilt": False,
                     "cover": cover_for(name)})
    return sorted(rows, key=lambda r: r["handle"])


@app.get("/api/accounts")
def get_accounts():
    return {"accounts": account_rows()}


@app.get("/api/accounts/{account}/sample")
def account_sample(account: str, n: int = 8):
    """A few saved pictures of an account, to pick a reference from."""
    out = []
    try:
        with os.scandir(rp.THUMB_DIR / account.lower()) as it:
            for e in it:
                if e.name.endswith(".jpg") and "@" not in e.name:
                    out.append({"name": e.name[:-4], "src": thumb_url(account, e.name[:-4], 160),
                                "path": f"cache/thumbs/{account.lower()}/{e.name}"})
                    if len(out) >= n:
                        break
    except OSError:
        pass
    return {"items": out}


def tag_options() -> dict:
    try:
        data = json.loads((HERE / "labels.json").read_text())
        options = {facet: list(labels) for facet, labels in data.items()}
    except (OSError, ValueError, TypeError):
        options = {}
    options["pose"] = POSE_TAGS
    options["arms"] = ["arms up"]
    return options


@app.get("/api/config")
def get_config():
    import socket
    return {"apiVersion": API_VERSION, "tags": tag_options(), "clipLengths": CLIP_LENGTHS, "host": socket.gethostname().split(".")[0],
            "model": os.environ.get("RPP_MODEL", "siglip"), "autoImport": auto_import_on()}


# =====================================================================================
# Describing a result (link, saved image, where it came from)
# =====================================================================================
def post_date(url: str):
    t = rp.post_time(url.replace("https://www.instagram.com", "", 1))
    return time.strftime("%-d %b %Y", time.gmtime(t)) if t else None


def code_of(path: str) -> str:
    m = re.search(r"/(?:p|reel|reels)/([\w-]+)", path)
    return m.group(1) if m else ""


def source_of(account: str, url: str) -> dict:
    key = url.replace("https://www.instagram.com", "", 1)
    if (CACHE / f"{account.lower()}.watch.json").exists():
        wv = rp.watched_video(account, key)
        if wv:
            return {"type": "watch", "original": wv["file"], "video": True}
    original = local_sources(account).get(key)
    if original:
        return {"type": "local", "original": original, "video": key in video_frames(account)}
    return {"type": "instagram", "original": None, "video": False}


def describe(account: str, url: str, slide=None, score=None, src_file: Path | None = None) -> dict:
    code = code_of(url)
    name = code + (f"@{slide}" if slide else "")
    f = rp.THUMB_DIR / account.lower() / f"{name}.jpg"
    has = (src_file or f).is_file()
    item = {"id": f"{account.lower()}:{name}", "account": account, "url": url, "slide": slide, "name": name,
            "score": score, "date": post_date(url), **source_of(account, url), "hasThumb": has,
            "thumb": None, "full": None, "src": rel(src_file or f)}
    if item["type"] == "local" and item["video"]:
        info = rp.video_frame(account, url.replace("https://www.instagram.com", "", 1))
        if info:
            item["at"], item["videoName"] = int(info["t"]), Path(info["file"]).name
    if has and src_file:
        item["thumb"], item["full"] = media_url(src_file, 560), media_url(src_file, 1400)
    elif has:
        item["thumb"], item["full"] = thumb_url(account, name, 560), thumb_url(account, name, 1400)
    return item


def parse_index_path(account: str, path: str) -> tuple:
    """(post URL, slide number or None) for an index key such as /user/p/CODE/ or /p/CODE/@3."""
    slide = re.search(r"/@(\d+)$", path)
    return ("https://www.instagram.com" + re.sub(r"/@\d+$", "/", path), int(slide.group(1)) if slide else None)


@app.post("/api/describe")
def describe_many(body: dict = Body(...)):
    account = str(body.get("account", ""))
    out = []
    for path in body.get("paths", [])[:200]:
        url, slide = parse_index_path(account, path)
        out.append(describe(account, url, slide))
    return {"items": out}


# =====================================================================================
# Favourites
# =====================================================================================
FAV_DIR = HERE / "favourites"
FAV_DB = FAV_DIR / "favourites.json"
_fav_lock = threading.Lock()


def load_favs() -> dict:
    try:
        return json.loads(FAV_DB.read_text())
    except (OSError, ValueError):
        return {}


def save_favs(favs: dict) -> None:
    FAV_DIR.mkdir(exist_ok=True)
    FAV_DB.write_text(json.dumps(favs, indent=1))


def fav_view(fid: str, v: dict) -> dict:
    f = HERE / v["file"]
    d = describe(v["account"], v["url"], None, None)
    return {**d, "id": fid, "account": v["account"], "name": v["stem"], "url": v["url"], "added": v.get("added", 0),
            "slide": int(v["stem"].split("@")[1]) if "@" in v["stem"] else None,
            "filename": f.name, "src": v["file"], "hasThumb": f.exists(),
            "thumb": media_url(f, 560) if f.exists() else None, "full": media_url(f, 1400) if f.exists() else None}


@app.get("/api/favs")
def get_favs():
    favs = load_favs()
    items = [fav_view(k, v) for k, v in sorted(favs.items(), key=lambda kv: -kv[1].get("added", 0))]
    return {"items": items}


@app.post("/api/favs/toggle")
def toggle_fav(body: dict = Body(...)):
    """Star or un-star an image. Starring copies the picture into favourites/<account>/."""
    account, stem, url = str(body["account"]), str(body["stem"]), str(body.get("url", ""))
    fid = f"{account.lower()}:{stem}"
    with _fav_lock:
        favs = load_favs()
        if fid in favs:
            (HERE / favs[fid]["file"]).unlink(missing_ok=True)
            del favs[fid]
            starred = False
        else:
            src = body.get("src") or f"cache/thumbs/{account.lower()}/{stem}.jpg"
            src_path = Path(src)
            src_path = src_path if src_path.is_absolute() else HERE / src_path
            if not src_path.is_file() or not (under_here(src_path) or str(src_path.resolve()) in _served):
                fail(404, "That picture isn't saved on disk, so it can't be starred.")
            dest = FAV_DIR / account.lower() / f"{stem}{src_path.suffix}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_path, dest)
            favs[fid] = {"account": account.lower(), "stem": stem, "url": url,
                         "file": str(dest.relative_to(HERE)), "added": time.time()}
            starred = True
        save_favs(favs)
    return {"starred": starred, "id": fid}


@app.get("/api/favs/ids")
def fav_ids():
    return {"ids": list(load_favs())}


# =====================================================================================
# Breakdown (tag counts) for the Library
# =====================================================================================
_bd_cache: dict = {}
_bd_locks: dict = {}


def run_env(model: str | None) -> dict:
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if model in MODELS:
        env["RPP_MODEL"] = model
    return env


def index_stamp(account: str) -> tuple:
    files = [CACHE / f"{account}.clip.npz", CACHE / f"{account}.siglip.npz", CACHE / f"{account}.pose.npz",
             CACHE / f"{account}.kinds.json", CACHE / f"{account}.expanded.json", HERE / "labels.json"]
    return tuple(_mtime(f) for f in files)


def clean_lines(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if l.strip() and not any(n in l for n in NOISE))


@app.get("/api/breakdown")
def breakdown(account: str, conf: float = 0.5, model: str = "siglip"):
    if not re.fullmatch(r"[\w.-]+", account):
        fail(400, "Bad account name")
    key = (account, round(conf, 2), model, index_stamp(account))
    lock = _bd_locks.setdefault(key[:3], threading.Lock())
    with lock:
        if key in _bd_cache:
            return _bd_cache[key]
        out = subprocess.run([sys.executable, "random_post.py", account, "--list-tags", "--json",
                              "--min-conf", str(conf)], cwd=HERE, env=run_env(model), capture_output=True, text=True)
        info = None
        for line in out.stdout.splitlines():
            if line.startswith("@@JSON@@"):
                info = json.loads(line[len("@@JSON@@"):])
        if info is None:
            fail(422, clean_lines(out.stdout + "\n" + out.stderr)[-600:] or "Couldn't read this account's index.")
        for k in [k for k in _bd_cache if k[:3] == key[:3]]:
            _bd_cache.pop(k)
        _bd_cache[key] = info
        return info


# =====================================================================================
# Processes: searches, saves and background jobs
# =====================================================================================
class Run:
    """A subprocess whose output is captured line by line (searches and full-size fetches)."""

    def __init__(self, cmd: list, env: dict, meta: dict):
        self.id = uuid.uuid4().hex[:10]
        self.meta, self.lines, self.code, self.cancelled = meta, [], None, False
        self.started, self.result, self.lock = time.time(), None, threading.Lock()
        self.proc = subprocess.Popen(cmd, cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1, start_new_session=True)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            line = line.rstrip()
            if line and not any(n in line for n in NOISE):
                self.lines.append(line)
        self.proc.wait()
        self.code = self.proc.returncode

    @property
    def status(self) -> str:
        if self.code is None:
            return "running"
        return "cancelled" if self.cancelled else ("done" if self.code == 0 else "failed")

    def cancel(self) -> None:
        self.cancelled = True
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


RUNS: dict = {}


def start_run(cmd, env, meta) -> Run:
    for rid in [r for r, run in RUNS.items() if time.time() - run.started > 3600 and run.code is not None]:
        RUNS.pop(rid, None)
    run = Run(cmd, env, meta)
    RUNS[run.id] = run
    return run


def build_command(p: dict, users: list, like, pose) -> list:
    """Turn the form values into a random_post.py command line (the same one the Streamlit app builds)."""
    take_all = bool(p.get("takeAll"))
    query = str(p.get("text") or "").strip()
    tags = list(p.get("tags") or [])
    count = 5 if take_all else max(1, int(p.get("count") or 5))
    cmd = [sys.executable, "random_post.py", *users, "--count", str(count), "--no-open"]
    if int(p.get("expand") or 0):
        cmd += ["--expand-carousels", str(int(p["expand"]))]
    if take_all:
        cmd.append("--all")
        if int(p.get("cap") or 0):
            cmd += ["--limit", str(int(p["cap"]))]
    for tag in tags:
        cmd += ["--tag", tag]
    if tags:
        cmd += ["--min-conf", str(float(p.get("confidence") or 0.5))]
    if query or like or pose:
        if pose:
            cmd += ["--pose", str(pose)]
            if not p.get("mirror", True):
                cmd.append("--no-mirror")
            if query or like:
                cmd += ["--scene-top", str(p.get("sceneTop") or 30)]
        if query:
            cmd += ["--find", query]
        if like:
            cmd += ["--like", str(like)]
            if query:
                cmd += ["--like-weight", str(float(p.get("imageWeight") if p.get("imageWeight") is not None else 0.5))]
        cmd += ["--top", str(int(p.get("top") or 50))]
        if p.get("polarity") == "worst":
            cmd.append("--worst")
    saving = p.get("resultMode") == "full"
    save_dir = p.get("_saveDir")
    if saving and save_dir:
        cmd += ["--save", str(save_dir)]
        if p.get("allSlides"):
            cmd.append("--all-slides")
            if p.get("margin") is not None:
                cmd += ["--slide-margin", str(p["margin"])]
    if p.get("includeVideo"):
        cmd.append("--include-videos")
    if p.get("clipSeconds") is not None:
        cmd += ["--clip-seconds", str(int(p["clipSeconds"]))]
    if p.get("mixVideos"):
        cmd.append("--mix-videos")
    if p.get("videoMix") is not None and not take_all:
        cmd += ["--video-mix", str(int(p["videoMix"]))]
    if p.get("dateFrom"):
        cmd += ["--after", str(p["dateFrom"])]
    if p.get("dateTo"):
        cmd += ["--before", str(p["dateTo"])]
    mix = p.get("mix", "each")
    if mix == "even" and not take_all:
        cmd.append("--even")
    elif mix == "pool":
        cmd.append("--combine")
    if p.get("cacheMode") == "rebuild":
        cmd.append("--full")
    elif p.get("cacheMode") == "refresh":
        cmd.append("--refresh")
    return cmd


def save_upload(data_url: str, tag: str) -> Path:
    m = re.match(r"data:image/(\w+);base64,(.*)", data_url, re.S)
    if not m:
        fail(400, "That reference image couldn't be read.")
    refs = CACHE / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    ext = {"jpeg": "jpg"}.get(m.group(1), m.group(1))
    path = refs / f"{time.strftime('%Y%m%d-%H%M%S')}_{tag}_{uuid.uuid4().hex[:4]}.{ext}"
    path.write_bytes(base64.b64decode(m.group(2)))
    return path


def reference_path(value, tag: str):
    """A reference given as an uploaded data URL, or as the project-relative path of a saved picture."""
    if not value:
        return None
    if str(value).startswith("data:"):
        return save_upload(value, tag)
    p = (HERE / str(value)).resolve()
    if not p.is_file() or not under_here(p):
        fail(400, "That reference picture isn't on disk.")
    return p


@app.post("/api/search")
def start_search(body: dict = Body(...)):
    p = dict(body)
    users = [u.strip().lstrip("@").strip("/") for u in p.get("accounts", []) if str(u).strip()]
    model = p.get("model") if p.get("model") in MODELS else "siglip"
    like = reference_path(p.get("refImage"), "ref") if p.get("useImage") and p.get("refImage") else None
    pose = reference_path(p.get("poseImage"), "pose") if p.get("usePose") and p.get("poseImage") else None
    if not (p.get("useText", True)):
        p["text"] = ""
    query = str(p.get("text") or "").strip()
    if not users:
        fail(400, "Choose at least one account.")
    if p.get("takeAll") and not (p.get("tags") or query or like or pose):
        fail(400, "Pick at least one tag (or give a search) to take everything that matches.")
    session_ok = (HERE / "auth.json").exists()
    needs_session = p.get("cacheMode", "cache") != "cache" or any(
        not any((CACHE / f"{u.lower()}.{m}.npz").exists() for m in MODELS) and not rp.is_watched(u) for u in users)
    if not session_ok and needs_session:
        fail(400, "That needs a saved Instagram session. Log in first (top bar, Session).")
    if p.get("mixVideos") and (query or like or pose or p.get("tags")) and all(rp.load_videos(u)["frames"] for u in users):
        p["mixVideos"] = False         # every account here is searchable by video frame, so random watched videos would only add noise
    mode = p.get("resultMode", "thumbs")
    save_dir = None
    if mode == "full":
        base = str(p.get("baseDir") or "picks").rstrip("/") or "picks"
        save_dir = f"{base}/{time.strftime('%Y-%m-%d_%H-%M-%S')}"
        p["_saveDir"] = save_dir
    cmd = build_command(p, users, like, pose)
    run = start_run(cmd, run_env(model), {"kind": "search", "mode": mode, "saveDir": save_dir, "users": users})
    return {"id": run.id}


def build_result(run: Run) -> dict:
    """Pull the post links (and saved files) out of a finished search's output."""
    files, links, last_url = {}, [], None
    for line in run.lines:
        m = re.match(r"\s*saved (\S+)\s+<-\s+(https://\S+)", line)
        if m:
            files[m.group(1)], last_url = m.group(2), m.group(2)
            continue
        m = re.match(r"\s+saved (\S+)$", line)
        if m and last_url:
            files[m.group(1)] = last_url
            continue
        m = re.match(r"\s+\[(.+?)\]\s+(https://\S+)(?:\s+\(slide (\d+)\))?(?:\s+score ([-\d.]+))?", line)
        if m:
            links.append((m.group(1), m.group(2), int(m.group(3)) if m.group(3) else None,
                          float(m.group(4)) if m.group(4) else None))
    warnings = [l for l in run.lines if l.startswith("Error") or "Warning" in l or l.startswith("Browser error")]
    mode, items, folder = run.meta.get("mode"), [], None
    if mode == "full" and run.meta.get("saveDir"):
        folder = HERE / run.meta["saveDir"]
        images = sorted(folder.glob("*.*")) if folder.exists() else []
        for img in images:
            if img.suffix.lower() not in MEDIA_EXT:
                continue
            url = files.get(img.name)
            account = img.name.split("_")[0]
            if url:
                extra = re.search(r"_(\d\d)\.\w+$", img.name)
                slide = int(extra.group(1)) if extra else None
                d = describe(account, url, slide, None, src_file=img)
                items.append({**d, "id": f"{account.lower()}:{d['name']}", "filename": img.name})
            else:
                items.append({"id": f"file:{img.name}", "account": account, "url": None, "slide": None, "name": img.stem,
                              "score": None, "date": None, "type": "local", "original": None, "video": False,
                              "hasThumb": True, "thumb": media_url(img, 560), "full": media_url(img, 1400),
                              "src": rel(img), "filename": img.name, "noFav": True})
    else:
        for user, url, slide, score in links:
            items.append(describe(user, url, slide, score))
    return {"items": items, "folder": rel(folder) if folder else None, "warnings": warnings,
            "linkCount": len(links), "mode": mode}


@app.get("/api/runs/{rid}")
def get_run(rid: str, since: int = 0):
    run = RUNS.get(rid)
    if not run:
        fail(404, "That run has ended or the server restarted.")
    out = {"id": rid, "status": run.status, "code": run.code, "lines": run.lines[since:], "total": len(run.lines)}
    if run.code is not None and run.meta.get("kind") == "search":
        with run.lock:
            if run.result is None:
                time.sleep(0.2)                        # let the reader thread drain the last lines
                out["lines"], out["total"] = run.lines[since:], len(run.lines)
                run.result = build_result(run)
        out["result"] = run.result
    if run.code is not None and run.meta.get("kind") == "fetch":
        out["folder"] = run.meta.get("folder")
    return out


@app.post("/api/runs/{rid}/cancel")
def cancel_run(rid: str):
    run = RUNS.get(rid)
    if run:
        run.cancel()
    return {"ok": True}


def unique_name(base: str) -> str:
    return re.sub(r"[^\w@.-]", "_", base)


@app.post("/api/save")
def save_results(body: dict = Body(...)):
    """Save ticked results: thumbnails are copied at once; full-size photos are fetched from Instagram."""
    kind = body.get("kind", "thumbs")
    items = body.get("items", [])
    if not items:
        fail(400, "Nothing selected.")
    base = str(body.get("baseDir") or "picks").rstrip("/") or "picks"
    out_dir = HERE / base / time.strftime("%Y-%m-%d_%H-%M-%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    def thumb_of(it):
        return rp.THUMB_DIR / str(it["account"]).lower() / f"{it['name']}.jpg"

    def file_name(it):
        score = it.get("score")
        return f"{it['account']}_{str(it['name']).replace('@', '_s')}" + (f"_{score}" if score else "")
    saved = 0
    if kind == "thumbs":
        for it in items:
            f = thumb_of(it)
            if f.exists():
                shutil.copyfile(f, out_dir / f"{unique_name(file_name(it))}.jpg")
                saved += 1
        return {"dir": rel(out_dir), "saved": saved}
    fetch_urls = []
    for it in items:
        if it.get("slide"):                                 # slides are already saved full-size
            f = thumb_of(it)
            if f.exists():
                shutil.copyfile(f, out_dir / f"{unique_name(it['account'] + '_' + str(it['name']).replace('@', '_s'))}.jpg")
                saved += 1
        elif it.get("url") and it["url"] not in fetch_urls:
            fetch_urls.append(it["url"])
    if not fetch_urls:
        return {"dir": rel(out_dir), "saved": saved}
    run = start_run([sys.executable, "random_post.py", "--fetch", *fetch_urls, "--save", str(out_dir), "--no-open"],
                    run_env(body.get("model")), {"kind": "fetch", "folder": rel(out_dir)})
    return {"dir": rel(out_dir), "saved": saved, "runId": run.id}


# --- Playing a video result ----------------------------------------------------------
_clips: dict = {}


@app.get("/api/clip")
def get_clip(account: str, url: str, secs: int = 15):
    """The clip to play for a video result: a window of a watched video, or the part around an imported frame."""
    key = url.replace("https://www.instagram.com", "", 1)
    if (CACHE / f"{account.lower()}.watch.json").exists():
        wv = rp.watched_video(account, key)
        if wv:
            got = _clips.get((account, key, secs))
            if not got or (got[1] and not Path(got[1]).exists()):
                got = _clips[(account, key, secs)] = rp.cut_window(
                    wv, secs, rp.CLIPS_DIR / f"watch_{wv['id']}_{int(time.time() * 1000)}.mp4", wv.get("start"))
            start, clip = got
            if clip:
                return {"url": media_url(clip), "start": 0, "name": Path(wv["file"]).name}
            if wv["duration"] <= secs or secs <= 0:
                return {"url": media_url(wv["file"]), "start": int(wv.get("start") or start or 0),
                        "name": Path(wv["file"]).name}
            fail(422, "The clip could not be cut (is ffmpeg installed?).")
    if key in video_frames(account):
        clip = rp.make_clip(account, key, secs)
        if not clip:
            fail(422, "The clip could not be cut (is the video file still where it was?).")
        start = 0
        if secs <= 0:
            info = rp.video_frame(account, key)
            start = int(info["t"]) if info else 0
        return {"url": media_url(clip), "start": start, "name": Path(clip).name}
    fail(404, "That result isn't a video.")


# --- Background jobs -------------------------------------------------------------------
JOB_DIR = CACHE / "jobs"
LEGACY = JOB_DIR / "current.json"
JOBS: dict = {}
_jobs_lock = threading.Lock()


def _alive(pid) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _persist(job: dict) -> None:
    try:
        meta = {k: v for k, v in job.items() if k != "proc"}
        (JOB_DIR / f"ui_{job['id']}.json").write_text(json.dumps(meta))
    except OSError:
        pass


def _watch_job(job: dict) -> None:
    code = job["proc"].wait()
    with _jobs_lock:
        job["exit"] = code
        job["finished"] = time.time()
        if job.get("stopped"):
            job["status"] = "stopped"
        else:
            job["status"] = "done" if code == 0 else "failed"
        _persist(job)


def _load_jobs() -> None:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(JOB_DIR.glob("ui_*.json")):
        try:
            job = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if job.get("dismissed"):
            continue
        if job.get("status") == "running" and not _alive(job["pid"]):
            job["status"] = "stopped" if job.get("stopped") else "done"
        JOBS[job["id"]] = job


def job_lines(path: str, n: int = 60) -> list:
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return []
    return [l for l in text.splitlines() if l.strip() and not any(x in l for x in NOISE)][-n:]


def job_view(job: dict) -> dict:
    lines = job_lines(job["log"])
    progress, text = None, None
    for l in reversed(lines):
        m = re.search(r"Progress: (\d+) / (\d+)", l)
        if m:
            done, total = int(m.group(1)), int(m.group(2))
            progress, text = (100.0 * min(done / total, 1.0) if total else 100.0), l
            break
    running = job["status"] == "running"
    if job["status"] == "done" and progress is None:
        progress = 100.0
    return {"id": job["id"], "kind": job["kind"], "title": job["title"], "account": job.get("account"),
            "status": job["status"], "progress": progress, "progressText": text, "log": lines,
            "started": job["started"] * 1000, "pid": job["pid"], "logPath": rel(job["log"]),
            "exit": job.get("exit"), "running": running}


def heavy_running() -> dict | None:
    with _jobs_lock:
        for job in JOBS.values():
            if job["kind"] in HEAVY_KINDS and job["status"] == "running" and _alive(job["pid"]):
                return job
    try:
        info = json.loads(LEGACY.read_text())                      # a job started from the Streamlit app
        if _alive(info["pid"]) and info["pid"] not in {j["pid"] for j in JOBS.values()}:
            return {"title": info.get("label", "a job")}
    except (OSError, ValueError, KeyError):
        pass
    return None


def start_job(kind: str, title: str, cmd: list, account: str | None = None, model: str | None = None) -> dict:
    if kind in HEAVY_KINDS:
        busy = heavy_running()
        if busy:
            fail(409, f"Another job is running ({busy['title']}). Wait for it or stop it first.")
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    log = JOB_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}.log"
    with open(log, "w") as fh:
        proc = subprocess.Popen(cmd, cwd=HERE, env=run_env(model), stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)
    job = {"id": uuid.uuid4().hex[:8], "kind": kind, "title": title, "account": account, "pid": proc.pid,
           "log": str(log), "started": time.time(), "status": "running", "proc": proc}
    with _jobs_lock:
        JOBS[job["id"]] = job
        _persist(job)
    try:                                                            # keep the Streamlit app's job panel in step
        LEGACY.write_text(json.dumps({"pid": proc.pid, "label": title, "log": str(log), "started": job["started"]}))
    except OSError:
        pass
    threading.Thread(target=_watch_job, args=(job,), daemon=True).start()
    return job


_load_jobs()


@app.get("/api/jobs")
def list_jobs():
    with _jobs_lock:
        jobs = list(JOBS.values())
    views = []
    for job in jobs:
        if job["status"] == "running" and not job.get("proc") and not _alive(job["pid"]):
            job["status"] = "done"
        views.append(job_view(job))
    try:                                                            # a job the Streamlit app started
        info = json.loads(LEGACY.read_text())
        if info["pid"] not in {j["pid"] for j in jobs}:
            alive = _alive(info["pid"])
            views.append(job_view({"id": "legacy", "kind": "other", "title": info.get("label", "Job"),
                                   "pid": info["pid"], "log": info["log"], "started": info["started"],
                                   "status": "running" if alive else "done"}))
    except (OSError, ValueError, KeyError):
        pass
    views.sort(key=lambda j: -j["started"])
    return {"jobs": views}


@app.post("/api/jobs")
def new_job(body: dict = Body(...)):
    kind, model = body.get("kind"), body.get("model")
    py = sys.executable
    needs_login = (HERE / "auth.json").exists()
    if kind == "prepare":
        users = [u.strip().lstrip("@").strip("/").lower() for u in re.split(r"[\s,]+", str(body.get("users", ""))) if u.strip()]
        if not users:
            fail(400, "Enter at least one account.")
        if not needs_login:
            fail(400, "Log in first (top bar, Session).")
        cmd = [py, "random_post.py", *users, "--prepare"]
        if int(body.get("expand") or 0):
            cmd += ["--expand-carousels", str(int(body["expand"]))]
        job = start_job("prepare", "Preparing " + ", ".join(users), cmd, users[0], model)
    elif kind == "index":
        acct = str(body.get("account", "")).strip()
        if not acct:
            fail(400, "Pick an account.")
        if not needs_login:
            fail(400, "Log in first (top bar, Session).")
        workers = int(body.get("workers") or 1)
        cap = int(body.get("cap") or 10)
        cmd = [py, "random_post.py", acct, "--prepare"]
        cmd += ["--expand-all"] if body.get("untilDone") else ["--expand-carousels", str(cap)]
        if workers > 1:
            cmd += ["--workers", str(workers)]
        title = f"Indexing every image of {acct}" + ("" if body.get("untilDone") else f" ({cap} posts)") \
            + (f", {workers} windows" if workers > 1 else "")
        job = start_job("index", title, cmd, acct, model)
    elif kind == "import":
        name, folder = str(body.get("name", "")).strip(), str(body.get("path", "")).strip().strip("'\"")
        if not name or not folder:
            fail(400, "Give both a name and a folder.")
        if not Path(folder).expanduser().is_dir():
            fail(400, "That folder wasn't found.")
        job = start_job("import", f"Importing {name}", [py, "random_post.py", name, "--import-folder", folder],
                        rp.clean_name(name), model)
    elif kind == "import-new":
        names = [str(n) for n in body.get("names", []) if n]
        title = f"Importing new files into {names[0]}" if len(names) == 1 else "Importing new files from your folders"
        job = start_job("import-new", title, [py, "random_post.py", *names, "--import-new"],
                        names[0] if len(names) == 1 else None, model)
    elif kind == "import-many":
        pairs = [[str(a), str(b)] for a, b in body.get("pairs", [])]
        if not pairs:
            fail(400, "Nothing to import.")
        JOB_DIR.mkdir(parents=True, exist_ok=True)
        pf = JOB_DIR / f"pairs_{int(time.time())}.json"
        pf.write_text(json.dumps(pairs))
        job = start_job("import-many", f"Importing photos for {len(pairs)} categories",
                        [py, "random_post.py", "--import-many", str(pf)], None, model)
    elif kind == "pilot":
        n = int(body.get("n") or 400)
        job = start_job("pilot", f"Sorting {n} screenshots from Photos", [py, "photos_import.py", "--pilot", str(n)])
    elif kind in ("detect", "pose", "library"):
        acct = str(body.get("account", "")).strip()
        if not acct:
            fail(400, "Pick an account.")
        if kind == "detect":
            if not needs_login:
                fail(400, "Log in first (top bar, Session).")
            job = start_job("detect", f"Detect carousels · {acct}", [py, "random_post.py", acct, "--detect-carousels"], acct, model)
        elif kind == "pose":
            job = start_job("pose", f"Pose index · {acct}", [py, "random_post.py", acct, "--build-pose"], acct, model)
        else:
            job = start_job("library", f"Library folders · {acct}",
                            [py, "random_post.py", acct, "--build-library", "--min-conf", str(float(body.get("conf") or 0.5))],
                            acct, model)
    elif kind == "index-videos":
        names = [rp.clean_name(str(n)) for n in (body.get("names") or [body.get("name", "")])]
        names = [n for n in dict.fromkeys(names) if n]
        if not names or not all(rp.watch_path(n).exists() for n in names):
            fail(400, "Pick video folders that are being watched.")
        if not shutil.which("ffmpeg"):
            fail(400, "ffmpeg is needed to read videos:  brew install ffmpeg")
        every = max(1, min(60, int(body.get("every") or 5)))
        label = f"a frame every {every} s" if every < 60 else "a frame every minute"
        if len(names) == 1:
            folder = rp.load_watch(names[0])["folder"]
            job = start_job("index-videos", f"Making {names[0]} searchable ({label})",
                            [py, "random_post.py", names[0], "--import-videos", folder, "--frame-every", str(every)], names[0], model)
        else:
            JOB_DIR.mkdir(parents=True, exist_ok=True)
            pf = JOB_DIR / f"vpairs_{int(time.time())}.json"
            pf.write_text(json.dumps([[n, rp.load_watch(n)["folder"]] for n in names]))
            job = start_job("index-videos", f"Making {len(names)} video folders searchable ({label})",
                            [py, "random_post.py", "--index-videos-many", str(pf), "--frame-every", str(every)], None, model)
    elif kind == "login":
        job = start_job("login", "Instagram login", [py, "login.py", "--timeout", "180"])
    else:
        fail(400, "Unknown job type.")
    return job_view(job)


@app.post("/api/jobs/{jid}/stop")
def stop_job(jid: str):
    job = JOBS.get(jid)
    pid = job["pid"] if job else None
    if jid == "legacy":
        try:
            pid = json.loads(LEGACY.read_text())["pid"]
        except (OSError, ValueError, KeyError):
            pass
    if not pid:
        fail(404, "No such job.")
    if job:
        job["stopped"] = True
    try:
        os.killpg(pid, signal.SIGTERM)                      # the job and the browser it started
    except (ProcessLookupError, PermissionError):
        pass
    return {"ok": True}


@app.post("/api/jobs/{jid}/dismiss")
def dismiss_job(jid: str):
    with _jobs_lock:
        job = JOBS.pop(jid, None)
        if job:
            job["dismissed"] = True
            _persist(job)
    if jid == "legacy" or (job and LEGACY.exists()):
        try:
            info = json.loads(LEGACY.read_text())
            if jid == "legacy" or info.get("pid") == job["pid"]:
                LEGACY.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError):
            pass
    return {"ok": True}


# =====================================================================================
# Image folders, watched video folders, settings
# =====================================================================================
def read_settings() -> dict:
    try:
        return json.loads((CACHE / "settings.json").read_text())
    except (OSError, ValueError):
        return {}


def write_settings(update: dict) -> dict:
    data = read_settings()
    data.update(update)
    (CACHE / "settings.json").write_text(json.dumps(data))
    return data


def auto_import_on() -> bool:
    return bool(read_settings().get("auto_import"))


@app.post("/api/settings/auto-import")
def set_auto_import(body: dict = Body(...)):
    return {"autoImport": bool(write_settings({"auto_import": bool(body.get("on"))})["auto_import"])}


@app.get("/api/imports")
def get_imports():
    rows = [{"name": n, "folders": rp.load_folders(n)["folders"], "pending": len(rp.pending_files(n)),
             "indexed": len(local_sources(n)) or None} for n in rp.imported_collections()]
    return {"collections": rows, "autoImport": auto_import_on()}


@app.post("/api/imports/auto-run")
def auto_run_imports(body: dict = Body(default={})):
    """Called once when the page opens: imports new files from the folders, if the setting is on."""
    if not auto_import_on() or heavy_running():
        return {"started": False}
    pending = sum(len(rp.pending_files(n)) for n in rp.imported_collections())
    if not pending:
        return {"started": False}
    start_job("import-new", "Importing new files from your folders",
              [sys.executable, "random_post.py", "--import-new"], None, body.get("model"))
    return {"started": True, "pending": pending}


def video_view(name: str, vid: str, v: dict, indexed: set | None = None) -> dict:
    poster = rp.poster_file(name, vid)
    return {"id": vid, "file": v["file"], "indexed": bool(indexed and v["file"] in indexed), "name": Path(v["file"]).name, "duration": v["duration"],
            "added": v.get("added", 0), "poster": media_url(poster, 480) if poster.exists() else None,
            "url": media_url(v["file"])}


@app.get("/api/watch")
def get_watch(limit: int = 60):
    out = []
    for name in rp.watched_collections():
        try:
            with _watch_lock:
                rp.scan_watched(name)
        except Exception as e:                                      # a bad file must never stop the panel
            out.append({"name": name, "folder": "", "attached": False, "count": 0, "videos": [], "error": str(e)})
            continue
        d = rp.load_watch(name)
        vids = sorted(d["videos"].items(), key=lambda kv: kv[1]["added"], reverse=True)
        iv = rp.load_videos(name)
        indexed = {v["file"] for v in iv["videos"].values()}
        out.append({"name": name, "folder": d["folder"], "attached": d["attached"], "count": len(vids),
                    "frames": len(iv["frames"]), "indexedVideos": len(indexed & {v["file"] for _, v in vids}),
                    "todoSeconds": int(sum(v["duration"] for _, v in vids if v["file"] not in indexed)),
                    "videos": [video_view(name, vid, v, indexed) for vid, v in vids[:limit]]})
    return {"folders": out}


@app.post("/api/watch")
def add_watch(body: dict = Body(...)):
    try:
        name = rp.start_watching(str(body.get("name", "")), str(body.get("folder", "")).strip().strip("'\""))
        rp.scan_watched(rp.clean_name(name))
    except rp.ScrapeError as e:
        fail(400, str(e))
    return {"name": name}


@app.delete("/api/watch/{name}")
def stop_watch(name: str):
    rp.watch_path(name).unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/watch/bulk")
def bulk_watch(body: dict = Body(...)):
    rows = [(str(r.get("name", "")), str(r.get("folder", ""))) for r in body.get("rows", [])]
    report = rp.create_collections(rows)
    todo = [[r["name"], r["folder"]] for r in report if r["status"] == "created" and r["photos"]]
    started, note = False, ""
    if todo:
        if heavy_running():
            note = "Photos were not imported because another job is running; import them from Image folders once it ends."
        else:
            pf = JOB_DIR / f"pairs_{int(time.time())}.json"
            JOB_DIR.mkdir(parents=True, exist_ok=True)
            pf.write_text(json.dumps(todo))
            start_job("import-many", f"Importing photos for {len(todo)} categories",
                      [sys.executable, "random_post.py", "--import-many", str(pf)], None, body.get("model"))
            started = True
    return {"report": report, "started": started, "note": note}


@app.post("/api/watch/{name}/random")
def random_clip(name: str, body: dict = Body(default={})):
    secs = int(body.get("secs", 15))
    pick = rp.random_segment(name, secs)
    if not pick:
        fail(404, "There are no videos in that folder yet.")
    file, start, clip = pick
    return {"url": media_url(clip or file), "start": 0 if clip else int(start), "name": Path(file).name,
            "from": int(start), "file": str(file)}


# --- Finding new folders and new videos automatically ---------------------------------
_watch_lock = threading.Lock()
DEFAULT_ROOT = "library"


def library_root(raw) -> Path:
    p = Path(str(raw or DEFAULT_ROOT)).expanduser()
    p = (p if p.is_absolute() else HERE / p)
    if not p.is_dir():
        fail(400, f"{p} isn't a folder.")
    return p


def _same(a: Path, b: Path) -> bool:
    """Same folder on disk, even if one path is spelled library/ and the other Library/."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def count_media(folder: Path) -> tuple:
    v = p = 0
    for _, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in rp.VIDEO_SUFFIXES:
                v += 1
            elif ext in rp.IMAGE_SUFFIXES:
                p += 1
    return v, p


def known_names() -> set:
    return account_names() | set(rp.watched_collections())


def discover(root: Path) -> dict:
    """Sub-folders of `root` that hold videos not being watched, or photos not imported yet."""
    watched = [Path(rp.load_watch(n)["folder"]) for n in rp.watched_collections()]
    imported = [Path(f) for n in rp.imported_collections() for f in rp.load_folders(n)["folders"]]
    known = known_names()
    rows, total = [], 0
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        total += 1
        v, ph = count_media(d)
        name = rp.clean_name(d.name)
        is_watched = any(_same(d, w) for w in watched)
        is_imported = any(_same(d, i) for i in imported)
        # a folder named like an account that is already indexed is usually that account's generated library view
        indexed = name in known or d.name.lower() in known
        add_v = v > 0 and not is_watched
        add_p = ph > 0 and not is_imported and not indexed
        if add_v or add_p:
            clash = rp.watch_path(name).exists() and not _same(d, Path(rp.load_watch(name)["folder"]))
            rows.append({"name": name, "dir": d.name, "folder": str(d), "videos": v, "photos": ph,
                         "addVideos": add_v, "addPhotos": add_p, "attaches": add_v and name in known,
                         "clash": rp.load_watch(name)["folder"] if clash and add_v else None})
    return {"root": str(root), "rows": rows, "total": total}


def add_found(rows: list, model) -> dict:
    """Start watching the chosen folders (videos are registered at once) and import their new photos."""
    report, pairs = [], []
    for r in rows:
        name, folder = rp.clean_name(str(r.get("name", ""))), str(r.get("folder", "")).strip()
        row = {"name": name, "folder": folder, "status": "", "videos": 0, "photos": 0}
        report.append(row)
        if not name or not Path(folder).is_dir():
            row["status"] = "folder not found" if name else "needs a name"
            continue
        status = []
        if r.get("videos", True):
            existing = rp.load_watch(name)["folder"] if rp.watch_path(name).exists() else None
            if existing and not _same(Path(folder), Path(existing)):
                status.append(f"already watching {existing} (press Stop there first)")
            else:
                try:
                    with _watch_lock:
                        rp.start_watching(name, folder)
                        rp.scan_watched(name)
                    row["videos"] = len(rp.load_watch(name)["videos"])
                    status.append("watching")
                except rp.ScrapeError as e:
                    status.append(str(e))
        if r.get("photos"):
            pairs.append([name, folder])
            row["photos"] = int(r.get("photoCount") or 0)
            status.append("photos queued")
        row["status"] = ", ".join(status) or "nothing to do"
    started, note = False, ""
    if pairs:
        if heavy_running():
            note = "Photos were not imported because another job is running; use Image folders > Import once it ends."
        else:
            JOB_DIR.mkdir(parents=True, exist_ok=True)
            pf = JOB_DIR / f"pairs_{int(time.time())}.json"
            pf.write_text(json.dumps(pairs))
            start_job("import-many", f"Importing photos for {len(pairs)} categories",
                      [sys.executable, "random_post.py", "--import-many", str(pf)], None, model)
            started = True
    return {"report": report, "started": started, "note": note}


@app.get("/api/watch/discover")
def discover_folders(root: Optional[str] = None):
    s = read_settings()
    r = library_root(root or s.get("library_root"))
    out = discover(r)
    out["autoAdd"] = bool(s.get("auto_add_folders"))
    out["savedRoot"] = s.get("library_root") or DEFAULT_ROOT
    return out


@app.post("/api/watch/add-found")
def add_found_folders(body: dict = Body(...)):
    return add_found(body.get("rows", []), body.get("model"))


@app.post("/api/watch/rescan")
def rescan_watched():
    """Look for new videos in every watched folder right now."""
    before = {n: len(rp.load_watch(n)["videos"]) for n in rp.watched_collections()}
    added = {}
    with _watch_lock:
        for n in before:
            try:
                rp.scan_watched(n)
            except Exception:
                continue
            gain = len(rp.load_watch(n)["videos"]) - before[n]
            if gain:
                added[n] = gain
    return {"added": added, "total": sum(added.values()), "folders": len(before)}


@app.post("/api/settings/library")
def set_library_settings(body: dict = Body(...)):
    update = {}
    if "root" in body:
        library_root(body["root"])                      # must be a real folder
        update["library_root"] = str(body["root"]).strip() or DEFAULT_ROOT
    if "auto" in body:
        update["auto_add_folders"] = bool(body["auto"])
    s = write_settings(update)
    return {"root": s.get("library_root") or DEFAULT_ROOT, "autoAdd": bool(s.get("auto_add_folders"))}


def _watch_loop() -> None:
    """Every 30 seconds register new videos in watched folders; with the setting on, also add new sub-folders."""
    time.sleep(8)
    tick = 0
    while True:
        try:
            with _watch_lock:
                for n in rp.watched_collections():
                    rp.scan_watched(n)
            s = read_settings()
            if s.get("auto_add_folders") and tick % 2 == 0:
                found = discover(library_root(s.get("library_root")))
                rows = [{"name": r["name"], "folder": r["folder"], "videos": r["addVideos"], "photos": r["addPhotos"],
                         "photoCount": r["photos"]} for r in found["rows"] if not r["clash"]]
                if rows:
                    add_found(rows, None)
        except Exception:
            pass
        tick += 1
        time.sleep(30)


# =====================================================================================
# Automatic analysis: a new video in the library gets frames, a model pass, sections and a position index entry
# =====================================================================================
CLIP_DIR = Path(os.environ.get("CLIP_TRAINING_DIR") or HERE / "CLIP Training")      # the env var is for testing only
CLIP_PY = CLIP_DIR / ".venv" / "bin" / "python"
AUTO_ANALYSE = CLIP_DIR / "scripts" / "auto_analyse.py"
AUTO_OFF = CLIP_DIR / "auto_pipeline_off"
_analysis = {"pending": None, "checked": 0}


def _analysis_running() -> bool:
    with _jobs_lock:
        return any(j["kind"] == "analyse" and j["status"] == "running" and _alive(j["pid"]) for j in JOBS.values())


def _analysis_pending() -> dict:
    r = subprocess.run([str(CLIP_PY), str(AUTO_ANALYSE), "--pending"], capture_output=True, text=True, timeout=120)
    info = json.loads(r.stdout.strip().splitlines()[-1])
    _analysis.update(pending=info.get("count", 0), checked=time.time())
    return info


def _start_analysis(count: int):
    return start_job("analyse", f"Analysing {count} new video{'s' if count != 1 else ''} (frames, model, sections)",
                     [str(CLIP_PY), str(AUTO_ANALYSE), "--once"])


def _analysis_loop() -> None:
    """Every 45 seconds: if videos are waiting in the library and nothing is analysing, start analysing them."""
    time.sleep(25)
    while True:
        try:
            if CLIP_PY.exists() and AUTO_ANALYSE.exists() and not AUTO_OFF.exists() and not _analysis_running():
                info = _analysis_pending()
                if info.get("count", 0) > 0:
                    _start_analysis(info["count"])
        except Exception:
            pass
        time.sleep(45)


def _aa():
    """The auto_analyse module (it lives with the model code and uses only the standard library)."""
    sd = str(CLIP_DIR / "scripts")
    if sd not in sys.path:
        sys.path.insert(0, sd)
    import auto_analyse
    return auto_analyse


def _pretty_creator(raw: str) -> str:
    return re.sub(r"[-_]+", " ", raw).strip().title()


def analysis_rows() -> dict:
    """Every library video (and every draft) with where it stands: verified, up to date, outdated, waiting, failed..."""
    aa = _aa()
    drafts_dir = Path(aa.DRAFTS)
    pkl = CLIP_DIR / "models" / "position_clf.pkl"
    model_t = pkl.stat().st_mtime if pkl.exists() else 0
    tv = aa.read_json(str(CLIP_DIR / "models" / "trained_videos.json"), {})
    idx = aa.read_json(str(CLIP_DIR / "position_index.json"), {"videos": {}, "sections": []})
    secs: dict = {}
    for sec in idx.get("sections", []):
        if sec.get("is_position"):
            secs.setdefault(sec["video"], []).append([sec["position"], sec["start_s"], sec["end_s"]])
    lib: dict = {}
    if os.path.isdir(aa.LIBRARY):
        for dp, _, files in os.walk(aa.LIBRARY):
            for f in files:
                stem, ext = os.path.splitext(f)
                if f.startswith(".") or ext.lower() not in aa.VIDEO_EXT or f.lower().endswith(aa.PARTIAL):
                    continue
                lib.setdefault(aa.norm(f), {"path": os.path.join(dp, f), "stem": stem,
                                            "creator": os.path.relpath(dp, aa.LIBRARY).split(os.sep)[0]})
    drafts: dict = {}
    if drafts_dir.is_dir():
        for d in sorted(os.listdir(drafts_dir)):
            if (drafts_dir / d / "segments.csv").exists() or (drafts_dir / d / "segments_corrected.csv").exists():
                drafts.setdefault(aa.norm(d), d)
    state = aa.read_json(aa.STATE, {})
    status = aa.read_json(aa.STATUS, {})
    queue = aa.queue_list()
    qpos = {q["name"]: i + 1 for i, q in enumerate(queue)}
    running = _analysis_running()
    current = status.get("current") if running else None
    rows = []
    for key in set(lib) | set(drafts):
        L, dn = lib.get(key), drafts.get(key)
        name = dn or L["stem"]
        row = {"name": name, "title": _nice_title(name), "hasFile": bool(L), "path": L["path"] if L else None,
               "creator": (idx.get("videos", {}).get(dn or "", {}).get("creator")
                           or (_pretty_creator(L["creator"]) if L and L["creator"] != "." else "Unknown creator")),
               "verified": False, "completed": False, "confidence": None, "sections": 0, "draftedAt": None,
               "outdated": False, "duration": None, "timeline": [], "error": None, "queuePos": qpos.get(name)}
        if dn:
            d = drafts_dir / dn
            corrected = (d / "segments_corrected.csv").exists()
            row["verified"] = corrected
            row["completed"] = bool(aa.read_json(str(d / "status.json"), {}).get("completed"))
            seg = d / "segments.csv"
            try:
                src = seg if seg.exists() else d / "segments_corrected.csv"
                with open(src, newline="") as fh:
                    rr = list(csv.DictReader(fh))
                row["sections"] = len(rr)
                confs = [float(r["confidence"]) for r in rr if r.get("confidence")]
                row["confidence"] = round(sum(confs) / len(confs), 2) if confs else None
                total = int(rr[-1]["end_frame"]) if rr else 0
                row["duration"] = idx.get("videos", {}).get(dn, {}).get("duration_s") or total * 5
            except Exception:
                pass
            if seg.exists():
                row["draftedAt"] = int(seg.stat().st_mtime * 1000)
                row["outdated"] = seg.stat().st_mtime < model_t
            row["timeline"] = secs.get(dn, [])
            fail_rec = state.get("redo", {}).get(name, {})
            if fail_rec.get("last_error") and fail_rec.get("failed_at", 0) > (seg.stat().st_mtime if seg.exists() else 0):
                row["error"] = fail_rec["last_error"][-200:]
        else:
            rec = state.get("files", {}).get(L["path"], {}) if L else {}
            if rec.get("last_error"):
                row["error"] = rec["last_error"][-200:]
        if name == current:
            st = "running"
        elif name in qpos:
            st = "queued"
        elif row["verified"]:
            st = "completed" if row["completed"] else "saved"
        elif dn:
            st = "outdated" if row["outdated"] else "current"
        else:
            st = "failed" if row["error"] else "waiting"
        row["status"] = st
        rows.append(row)
    counts: dict = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"videos": rows, "counts": counts, "running": running, "current": current, "queued": len(queue),
            "done": status.get("done", 0), "failedNow": status.get("failed", 0), "paused": (CLIP_DIR / "auto_pipeline_off").exists(),
            "model": {"trainedAt": int(model_t * 1000), "videos": len(tv.get("videos", [])), "frames": tv.get("frames")},
            "colours": aa.read_json(str(CLIP_DIR / "labels.json"), {}).get("colours", {})}


@app.get("/api/analysis/videos")
def analysis_videos():
    if not (CLIP_PY.exists() and AUTO_ANALYSE.exists()):
        fail(404, "The model tools were not found.")
    return analysis_rows()


@app.post("/api/analysis/queue")
def analysis_queue(body: dict = Body(...)):
    """Queue videos for the model: explicit names, or a scope. Nothing you verified is ever overwritten:
    for those videos only the model's own draft is replaced, and your saved version, completed mark,
    excluded frames and the training data are left exactly as they are."""
    aa = _aa()
    data = analysis_rows()
    rows = {r["name"]: r for r in data["videos"]}
    scope, names = body.get("scope"), body.get("names")
    if names:
        chosen = [rows[n] for n in names if n in rows]
    elif scope == "todo":
        chosen = [r for r in rows.values() if r["status"] in ("waiting", "failed", "outdated")]
    elif scope == "unverified":
        chosen = [r for r in rows.values() if r["status"] in ("waiting", "failed", "outdated", "current")]
    elif scope == "all":
        chosen = list(rows.values())
    else:
        fail(400, "Say which videos.")
    chosen = [r for r in chosen if r["status"] not in ("queued", "running") and (r["path"] or r["status"] not in ("waiting", "failed"))]
    added = aa.queue_add([{"name": r["name"], "path": r["path"]} for r in chosen])
    started = False
    if added and not _analysis_running():
        _start_queue_job(len(aa.queue_list()))
        started = True
    return {"added": added, "started": started, "skipped": len(chosen) - added}


def _start_queue_job(count: int):
    return start_job("analyse", f"Analysing {count} video{'s' if count != 1 else ''} (frames, model, sections)",
                     [str(CLIP_PY), str(AUTO_ANALYSE), "--once", "--queue-only"])


@app.post("/api/analysis/cancel")
def analysis_cancel():
    """Empty the queue and stop after the video being analysed right now."""
    aa = _aa()
    n = aa.queue_clear()
    stopped = False
    with _jobs_lock:
        for j in JOBS.values():
            if j["kind"] == "analyse" and j["status"] == "running" and j.get("proc"):
                try:
                    j["proc"].terminate()
                    stopped = True
                except OSError:
                    pass
    return {"cleared": n, "stopping": stopped}


@app.get("/api/analysis/status")
def analysis_status():
    st = {}
    try:
        st = json.loads((CLIP_DIR / "pipeline_status.json").read_text())
    except (OSError, ValueError):
        pass
    return {"enabled": not AUTO_OFF.exists(), "installed": CLIP_PY.exists() and AUTO_ANALYSE.exists(),
            "running": _analysis_running(), "pending": _analysis["pending"], "status": st}


@app.post("/api/analysis/enabled")
def analysis_enabled(body: dict = Body(...)):
    if body.get("enabled"):
        AUTO_OFF.unlink(missing_ok=True)
    else:
        AUTO_OFF.write_text("pause automatic analysis by keeping this file; delete it to resume\n")
    return {"enabled": not AUTO_OFF.exists()}


@app.post("/api/analysis/run")
def analysis_run():
    if _analysis_running():
        return {"started": False, "reason": "already running"}
    info = _analysis_pending()
    if not info.get("count"):
        return {"started": False, "reason": "nothing is waiting"}
    AUTO_OFF.unlink(missing_ok=True)
    _start_analysis(info["count"])
    return {"started": True, "count": info["count"]}


@app.on_event("startup")
def _start_watch_loop() -> None:
    threading.Thread(target=_watch_loop, daemon=True).start()
    threading.Thread(target=_analysis_loop, daemon=True).start()


# =====================================================================================
# Photos pilot
# =====================================================================================
PILOT_DIR = HERE / "pilot"


def load_overrides() -> dict:
    try:
        return json.loads((PILOT_DIR / "overrides.json").read_text())
    except (OSError, ValueError):
        return {}


@app.get("/api/pilot")
def get_pilot():
    try:
        results = json.loads((PILOT_DIR / "results.json").read_text())
    except (OSError, ValueError):
        results = []
    items = []
    for it in results:
        crop = PILOT_DIR / "crops" / f"{it['uuid']}.jpg"
        prev = Path(it.get("preview", ""))
        items.append({"id": it["uuid"], "file": it.get("filename", ""), "date": it.get("date"),
                      "score": it["p_keep"], "body": bool(it["body"]), "prompt": it.get("best_prompt", ""),
                      "crop": media_url(crop, 420) if crop.exists() else None,
                      "screenshot": media_url(prev, 600) if prev.is_file() else None})
    return {"items": items, "overrides": load_overrides()}


@app.post("/api/pilot/pile")
def set_pile(body: dict = Body(...)):
    """Your decision for one screenshot: keep, review or junk; 'auto' removes it."""
    uid, pile = str(body["id"]), str(body["pile"])
    if pile not in ("keep", "review", "junk", "auto"):
        fail(400, "Bad pile")
    ov = load_overrides()
    if pile == "auto":
        ov.pop(uid, None)
    else:
        ov[uid] = pile
    PILOT_DIR.mkdir(exist_ok=True)
    (PILOT_DIR / "overrides.json").write_text(json.dumps(ov))
    return {"overrides": ov}


# =====================================================================================
# Session and storage
# =====================================================================================
@app.get("/api/session")
def get_session():
    f = HERE / "auth.json"
    if not f.exists():
        return {"authFile": False, "loggedIn": False, "userId": None}
    try:
        cookies = json.loads(f.read_text()).get("cookies", [])
    except (OSError, ValueError):
        cookies = []
    return {"authFile": True, "userId": next((c["value"] for c in cookies if c["name"] == "ds_user_id"), None),
            "loggedIn": any(c["name"] == "sessionid" and c["value"] for c in cookies)}


@app.post("/api/session/check")
def check_session():
    out = subprocess.run([sys.executable, "whoami.py"], cwd=HERE, capture_output=True, text=True)
    text = clean_lines(out.stdout + "\n" + out.stderr)
    m = re.search(r"Logged in as: (\S+)", text)
    return {"ok": out.returncode == 0, "text": text, "user": m.group(1) if m else None}


def _size(path) -> int:
    total = 0
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if e.is_symlink() or e.name == "node_modules":
                        continue
                    total += _size(e.path) if e.is_dir(follow_symlinks=False) else e.stat(follow_symlinks=False).st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


_storage: dict = {"at": 0, "data": None}


@app.get("/api/storage")
def get_storage(refresh: bool = False):
    if refresh or time.time() - _storage["at"] > 60 or _storage["data"] is None:
        top = {}
        for e in os.scandir(HERE):
            if (e.name.startswith(".") and e.name != ".streamlit") or e.name == "node_modules":
                continue
            top[e.name] = _size(e.path) if e.is_dir(follow_symlinks=False) else e.stat(follow_symlinks=False).st_size
        thumbs = {}
        if rp.THUMB_DIR.exists():
            for e in os.scandir(rp.THUMB_DIR):
                if e.is_dir():
                    thumbs[f"cache/thumbs/{e.name}"] = _size(e.path)
        _storage.update(at=time.time(), data={"top": top, "thumbs": thumbs})
    data = _storage["data"]
    disk = shutil.disk_usage(HERE)
    big = lambda d, n: [{"name": k, "bytes": v} for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:n] if v >= 1e6]
    return {"free": disk.free, "used": disk.used, "total": disk.total, "mine": sum(data["top"].values()),
            "biggest": big(data["top"], 8), "thumbs": big(data["thumbs"], 5)}


# =====================================================================================
# Links: the scrape / sort / download tool, run as its own small server and shown inside this interface
# =====================================================================================
LINKS_DIR = Path("/Users/hugodyson/Links-3-embedded")     # a copy of Links-3, so the original is never touched
LINKS_PORT = 8791
LINKS_NEEDS = ("requests", "pyautogui", "bs4", "cv2", "numpy")      # what the Links scraper and downloader import


def _links_python() -> str:
    """First Python that has everything Links needs. Every script it launches runs under the same one."""
    for cand in (sys.executable, "/usr/bin/python3", "/Library/Developer/CommandLineTools/usr/bin/python3",
                 "/opt/homebrew/bin/python3"):
        if cand and os.path.exists(cand):
            code = "import importlib.util as u,sys;sys.exit(any(u.find_spec(m) is None for m in %r))" % (LINKS_NEEDS,)
            if subprocess.run([cand, "-c", code], capture_output=True).returncode == 0:
                return cand
    return sys.executable
_links: dict = {"proc": None}


def _links_up() -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", LINKS_PORT), timeout=0.4):
            return True
    except OSError:
        return False


@app.get("/api/links/status")
def links_status():
    return {"running": _links_up(), "url": f"http://127.0.0.1:{LINKS_PORT}", "dir": str(LINKS_DIR),
            "exists": (LINKS_DIR / "ui" / "server.py").exists()}


@app.post("/api/links/start")
def links_start():
    if _links_up():
        return {"running": True, "url": f"http://127.0.0.1:{LINKS_PORT}"}
    if not (LINKS_DIR / "ui" / "server.py").exists():
        raise HTTPException(404, f"Links isn't installed at {LINKS_DIR}.")
    py = _links_python()
    log = open(LINKS_DIR / "ui" / "embedded_server.log", "ab")
    _links["proc"] = subprocess.Popen([py, str(LINKS_DIR / "ui" / "server.py"), "--port", str(LINKS_PORT), "--no-open"],
                                      cwd=str(LINKS_DIR), stdout=log, stderr=log, start_new_session=True)
    for _ in range(40):
        if _links_up():
            return {"running": True, "url": f"http://127.0.0.1:{LINKS_PORT}"}
        if _links["proc"].poll() is not None:
            raise HTTPException(500, "Links stopped right after starting. See ui/embedded_server.log in " + str(LINKS_DIR))
        time.sleep(0.25)
    raise HTTPException(500, "Links did not start in time.")


@app.post("/api/links/stop")
def links_stop():
    p = _links.get("proc")
    if p and p.poll() is None:
        p.terminate()
    return {"running": _links_up()}


# =====================================================================================
# Positions: ask for a position ("Doggystyle, 10 videos, 30 second clips") and get clips from the right parts of videos
# =====================================================================================
_pidx: dict = {"mtime": 0, "data": None}


def _position_index() -> dict:
    p = CLIP_DIR / "position_index.json"
    if not p.exists():
        fail(404, "There is no position index yet. Analyse some videos first.")
    m = p.stat().st_mtime
    if m != _pidx["mtime"]:
        _pidx.update(mtime=m, data=json.loads(p.read_text()))
    return _pidx["data"]


def _nice_title(name: str) -> str:
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", name).strip()


@app.get("/api/positions")
def positions_list():
    idx = _position_index()
    by: dict = {}

    def add(key, s):
        b = by.setdefault(key, {"name": key, "videos": set(), "verified": set(), "seconds": 0})
        b["videos"].add(s["video"])
        b["seconds"] += s["end_s"] - s["start_s"]
        if s["source"] == "verified":
            b["verified"].add(s["video"])

    for s in idx["sections"]:
        if not s["is_position"]:
            continue
        add(s["search_as"], s)
        if s.get("sub"):                                    # also searchable as "Parent - Sub-type"
            add(f"{s['position']} - {s['sub']}", s)
    rows = [{"name": b["name"], "videos": len(b["videos"]), "verified": len(b["verified"]),
             "minutes": round(b["seconds"] / 60)} for b in by.values()]
    parents = sorted((r for r in rows if " - " not in r["name"]), key=lambda r: -r["videos"])
    subs: dict = {}
    for r in rows:
        if " - " in r["name"]:
            subs.setdefault(r["name"].split(" - ", 1)[0], []).append(r)
    rows = []
    for r in parents:                                       # each position followed by its sub-types
        rows.append(r)
        rows += sorted(subs.pop(r["name"], []), key=lambda x: -x["videos"])
    for rest in subs.values():
        rows += rest
    vids = idx["videos"].values()
    return {"positions": rows, "built": idx["built"], "videos": len(idx["videos"]),
            "verifiedVideos": sum(1 for v in vids if v["verified"]), "missingFiles": sum(1 for v in vids if not v["path"])}


@app.get("/api/positions/videos")
def positions_videos(position: str, creator: str = ""):
    """Which analysed videos have this position and which do not."""
    idx = _position_index()
    sys.path.insert(0, str(CLIP_DIR / "scripts"))
    import query_positions as qp
    has_secs: dict = {}
    for s in idx["sections"]:
        if s["is_position"] and qp.matches(s, position):
            has_secs[s["video"]] = has_secs.get(s["video"], 0) + (s["end_s"] - s["start_s"])
    withp, without = [], []
    for name, v in idx["videos"].items():
        if creator and creator.lower() not in v["creator"].lower():
            continue
        row = {"name": name, "title": _nice_title(name), "creator": v["creator"], "verified": v["verified"],
               "seconds": round(has_secs.get(name, 0)), "hasFile": bool(v["path"])}
        (withp if name in has_secs else without).append(row)
    withp.sort(key=lambda r: -r["seconds"])
    without.sort(key=lambda r: (r["creator"].lower(), r["title"].lower()))
    return {"with": withp, "without": without}


@app.post("/api/positions/clips")
def positions_clips(body: dict = Body(...)):
    import concurrent.futures
    sys.path.insert(0, str(CLIP_DIR / "scripts"))
    import query_positions as qp
    position = str(body.get("position", "")).strip()
    if not position:
        fail(400, "Pick a position.")
    secs = max(0, min(int(body.get("seconds", 30)), 1800))
    count = max(1, min(int(body.get("count", 10)), 60))
    idx = _position_index()
    picks = qp.pick_clips(idx, position, videos=count, clip=secs, margin=5,
                          verified_only=bool(body.get("verifiedOnly")), min_conf=float(body.get("minConf") or 0),
                          video=(body.get("video") or None), allow_short=bool(body.get("allowShort")),
                          seed=body.get("seed"), per_video=max(1, int(body.get("perVideo") or 1)),
                          exclude=set(body.get("excludeVideos") or []), need_path=True)

    def cut(c):
        info = idx["videos"][c["video"]]
        length = max(1, int(round(c["end_s"] - c["start_s"])))
        if not Path(c["path"]).exists():
            return {**c, "error": "The video file is no longer where it was."}
        key = hashlib.md5(f"{c['path']}|{c['start_s']}|{length}".encode()).hexdigest()[:14]
        dest = rp.CLIPS_DIR / f"pos_{key}.mp4"
        if dest.exists() and dest.stat().st_size:
            got = (c["start_s"], dest)
        else:
            got = rp.cut_window({"file": c["path"], "duration": info["duration_s"] or 10**6}, length, dest, c["start_s"])
        if got[1]:
            return {**c, "url": media_url(got[1]), "offset": 0}
        return {**c, "url": media_url(c["path"]), "offset": int(c["start_s"])}      # play the original from that time

    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        cut_clips = list(pool.map(cut, picks))
    out = []
    for c in cut_clips:
        if c.get("error"):
            continue
        out.append({"id": f"{c['video']}|{c['start_s']}", "video": c["video"], "title": _nice_title(c["video"]),
                    "creator": c["creator"], "position": c["position"], "startS": c["start_s"], "endS": c["end_s"],
                    "sectionStart": c["section"][0], "sectionEnd": c["section"][1], "source": c["source"],
                    "confidence": c["confidence"], "url": c["url"], "offset": c["offset"], "file": c["path"]})
    return {"clips": out, "requested": count, "found": len(out)}


# =====================================================================================
# The interface itself
# =====================================================================================
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
else:
    @app.get("/")
    def no_ui():
        return Response("The interface hasn't been built. Run: python3 server.py --rebuild", media_type="text/plain")
