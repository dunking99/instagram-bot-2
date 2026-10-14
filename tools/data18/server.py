#!/usr/bin/env python3
"""Tiny dashboard: type a performer name, see their videos with categories.   .venv/bin/python server.py  ->  http://127.0.0.1:8790"""
import csv
import hashlib
import json
import queue
import random
import re
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

import scraper

HERE = Path(__file__).parent
CACHE = HERE / "data" / "results"
IMG_CACHE = HERE / "data" / "imgcache"
PORT = 8790
MAX_IMG_BYTES = 25 * 1024 * 1024

scrape_lock = threading.Lock()   # one scrape at a time, keeps us polite to the site
jobs = {}                        # slug -> job dict
jobs_lock = threading.Lock()


def save_result(result):
    if not result["videos"]:     # never overwrite a good file with an empty result
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    result["total"] = len(result["videos"])
    path = CACHE / f"{result['slug']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    tmp.replace(path)


def missing_details(result):
    return sum(1 for v in result["videos"] if "categories" not in v or "galleries" not in v or "tags" not in v)


def run_job(job, name, refresh):
    """Background thread: listing (unless cached), then categories for any video that lacks them."""
    try:
        with scrape_lock:
            slug = job["slug"]
            cached = CACHE / f"{slug}.json"
            if cached.exists() and not refresh:
                result = json.loads(cached.read_text())
                job["cached"] = True
            else:
                job["phase"] = "listing"
                result = {"slug": slug, "total": 0, "videos": []}
                job["result"] = result
                listing = scraper.scrape_listing(
                    name, progress=lambda page, n: job.update(listing_page=page, listing_count=n))
                result.update(listing)
                job["cached"] = False
                save_result(result)
            job["result"] = result
            if result["videos"]:
                scraper.apply_cached_details(result)
                job["details_total"] = len(result["videos"])
                job["details_done"] = job["details_total"] - missing_details(result)
                if missing_details(result):
                    job["phase"] = "details"

                    def prog(done, total):
                        job["details_done"], job["details_total"] = done, total
                        if done % 25 == 0:
                            save_result(result)
                    scraper.enrich(result, scraper.load_session(), prog)
                save_result(result)
            job["phase"] = "done"
            if (not job.get("cached") or refresh) and auto_settings()["enabled"]:
                try:
                    auto_enqueue(slug)
                except Exception:
                    pass
    except scraper.SessionError as e:
        job.update(phase="error", error=str(e), needs_setup=True)
    except LookupError as e:
        job.update(phase="error", error=str(e), status=404)
    except Exception as e:
        job.update(phase="error", error=f"{type(e).__name__}: {e}")


def start_job(name, refresh):
    slug = scraper.slugify(name)
    if not slug:
        raise ValueError("empty name")
    with jobs_lock:
        job = jobs.get(slug)
        if job and job["phase"] in ("queued", "listing", "details"):
            return job                       # already running: just follow it
        job = {"slug": slug, "phase": "queued", "result": None, "error": None}
        jobs[slug] = job
    threading.Thread(target=run_job, args=(job, name, refresh), daemon=True).start()
    return job


_tag_index = {"key": None, "by_tag": {}}


def tag_index():
    """tag slug -> {scene_id: video} across every saved performer. Rebuilt only when a results file changes."""
    files = sorted(CACHE.glob("*.json")) if CACHE.exists() else []
    key = tuple((f.name, f.stat().st_mtime_ns) for f in files)
    if _tag_index["key"] == key:
        return _tag_index["by_tag"]
    by_tag = {}
    for f in files:
        try:
            result = json.loads(f.read_text())
        except Exception:
            continue
        for v in result.get("videos", []):
            for slug in v.get("tags", []):
                rec = by_tag.setdefault(slug, {}).get(v["scene_id"])
                if rec is None:
                    rec = by_tag[slug][v["scene_id"]] = {
                        "scene_id": v["scene_id"], "title": v["title"], "url": v["url"], "date": v.get("date", ""),
                        "number": v.get("number", ""), "thumbnail": v.get("thumbnail", ""), "studio": v.get("studio", ""),
                        "performers": v.get("performers", []), "scraped_from": []}
                if result["slug"] not in rec["scraped_from"]:
                    rec["scraped_from"].append(result["slug"])
    _tag_index.update(key=key, by_tag=by_tag)
    return by_tag


studios_job = {"phase": "idle", "page": 0, "count": 0, "error": None}


def run_studios_job():
    try:
        with scrape_lock:
            scraper.scrape_studios(progress=lambda page, n: studios_job.update(page=page, count=n))
        studios_job["phase"] = "done"
    except scraper.SessionError as e:
        studios_job.update(phase="error", error=str(e), needs_setup=True)
    except Exception as e:
        studios_job.update(phase="error", error=f"{type(e).__name__}: {e}")


stars_job = {"phase": "idle", "page": 0, "count": 0, "error": None, "started": 0}


def run_stars_job():
    try:
        with scrape_lock:
            scraper.scrape_pornstars(progress=lambda page, n: stars_job.update(page=page, count=n))
        stars_job["phase"] = "done"
    except scraper.SessionError as e:
        stars_job.update(phase="error", error=str(e), needs_setup=True)
    except Exception as e:
        stars_job.update(phase="error", error=f"{type(e).__name__}: {e}")


def snapshot(job):
    result = job["result"]
    out = {k: v for k, v in job.items() if k != "result"}
    out["videos"] = list(result["videos"]) if result else []
    out["total"] = len(out["videos"])
    return out


def fetch_image(url):
    """(bytes, content_type) for an image on a *.dt18.com host. The image servers refuse requests that don't
    come from data18 itself, so the server adds that referrer and keeps a copy on disk."""
    u = urlparse(url)
    if u.scheme != "https" or not (u.hostname or "").endswith(".dt18.com"):
        raise ValueError("only https://*.dt18.com images are served")
    key = hashlib.sha1(url.encode()).hexdigest()
    IMG_CACHE.mkdir(parents=True, exist_ok=True)
    cached = next(iter(IMG_CACHE.glob(key + ".*")), None)
    if cached:
        return cached.read_bytes(), "image/" + cached.suffix.lstrip(".")
    r = requests.get(url, timeout=25, headers={"Referer": "https://www.data18.com/", "User-Agent": scraper.DEFAULT_UA})
    ctype = r.headers.get("Content-Type", "").split(";")[0]
    if r.status_code != 200 or not ctype.startswith("image/") or len(r.content) > MAX_IMG_BYTES:
        raise LookupError(f"image unavailable ({r.status_code})")
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(ctype, "img")
    tmp = IMG_CACHE / f"{key}.tmp{threading.get_ident()}"
    tmp.write_bytes(r.content)
    tmp.replace(IMG_CACHE / f"{key}.{ext}")
    return r.content, ctype


# ---- position models: run them on one video's stills and photosets (each model runs in ITS OWN python, as a subprocess)
CLIP_DIR = Path(__file__).resolve().parents[2] / "CLIP Training"
MODEL_PY = CLIP_DIR / ".venv" / "bin" / "python"
MODEL_SCRIPT = CLIP_DIR / "scripts" / "classify_images.py"
MODELS = {                       # id -> label shown in the dashboard, and the file whose date is the model's version
    "b32": {"label": "Yours (B/32)", "pkl": CLIP_DIR / "models" / "position_clf.pkl", "has_sub": True},
    "l14": {"label": "New (L/14)", "pkl": CLIP_DIR / "models" / "experimental" / "l14_clf.pkl", "has_sub": False},
}
ACTIVE = ["b32"]                 # the models that are run and shown (the L/14 entry above is kept but switched off)
PRED_FILE = HERE / "data" / "predictions.json"
pred_jobs = {}                   # scene_id -> job dict
pred_lock = threading.Lock()     # guards pred_jobs and the predictions file
model_lock = threading.Lock()    # one model run at a time (they are heavy)
KIND_RE = [("stills", re.compile(r"^video\s?stills", re.I)), ("photoset", re.compile(r"^photoset", re.I))]   # Primary and Trailer are skipped
RUNNING = ("queued", "galleries", "downloading", "model")


def gallery_kind(label):
    return next((k for k, rx in KIND_RE if rx.match(label)), None)


def model_version(mid):
    pkl = MODELS[mid]["pkl"]
    return time.strftime("trained %Y-%m-%d %H:%M", time.localtime(pkl.stat().st_mtime)) if pkl.exists() else "missing"


def load_predictions():
    """{"models": {id: {"meta": {...}, "images": {url: prediction}}}}. Migrates the first single-model file format."""
    try:
        d = json.loads(PRED_FILE.read_text())
    except Exception:
        d = {}
    if "images" in d and "models" not in d:                      # old format: everything was the L/14 model
        meta = dict(d.get("model", {}))
        if str(meta.get("version", "")).startswith("ViT-L/14"):      # the old version string was "<name>, trained <date>"
            meta["version"] = meta["version"].split(", ", 1)[-1]
        d = {"models": {"l14": {"meta": meta, "images": d["images"]}}}
    d.setdefault("models", {})
    for mid in MODELS:
        d["models"].setdefault(mid, {"meta": {}, "images": {}})
    return d


def save_predictions(mid, new_images):
    with pred_lock:                                    # merge, never overwrite: partial runs accumulate
        d = load_predictions()
        m = d["models"][mid]
        m["meta"] = {"name": MODELS[mid]["label"], "version": model_version(mid), "run_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        m["images"].update(new_images)
        tmp = PRED_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False))
        tmp.replace(PRED_FILE)


def scene_items(sid):
    """[(url, gallery label, kind)] for the stills and photosets of one scene (full-size addresses, fetched on demand)."""
    galleries = scraper.scene_galleries(sid)
    if galleries is None:
        if scraper.fetch_scene_details(scraper.load_session(), sid, scraper.BASE + "/") is None:
            raise RuntimeError("data18 didn't answer, try again in a moment")
        galleries = scraper.scene_galleries(sid)
    return [(im["f"], g["label"], gallery_kind(g["label"])) for g in galleries or [] if gallery_kind(g["label"])
            for im in g["images"]]


def run_predict(job, sid, refresh, only=None):
    try:
        job["phase"] = "galleries"
        items = scene_items(sid)
        if only is not None:                                           # a hand-picked set of images
            items = [it for it in items if it[0] in only]
        if not items:
            raise LookupError("This video has no Video Stills or Photosets to run the models on.")
        for mid in ACTIVE:
            if not MODELS[mid]["pkl"].exists():
                raise RuntimeError(f"The {MODELS[mid]['label']} model file is missing ({MODELS[mid]['pkl'].name}).")
        if not MODEL_PY.exists():
            raise RuntimeError("The model environment is missing (CLIP Training/.venv).")
        saved = load_predictions()["models"]
        todo = {mid: (items if refresh else [it for it in items if it[0] not in saved[mid]["images"]]) for mid in ACTIVE}
        need = {it[0]: it for mid in ACTIVE for it in todo[mid]}          # every image at least one model still has to judge
        job.update(total=len(need), done=0)
        paths = {}                                                          # image url -> cached file on disk
        if need:
            job["phase"] = "downloading"
            def get_one(url):
                key = hashlib.sha1(url.encode()).hexdigest()
                if not next(iter(IMG_CACHE.glob(key + ".*")), None):
                    _img_wait()                                             # same 8 per second cap as the batch, shared by every download
                    try:
                        fetch_image(url)
                    except Exception:
                        job["failed"] = job.get("failed", 0) + 1
                cached = next((c for c in IMG_CACHE.glob(key + ".*") if c.suffix != ".tmp"), None)
                job["done"] = job.get("done", 0) + 1
                return url, (str(cached) if cached else None)
            with ThreadPoolExecutor(IMG_WORKERS) as pool:
                for url, path in pool.map(get_one, list(need)):
                    if path:
                        paths[url] = path
            if not paths:
                raise RuntimeError("None of the images could be downloaded.")
            for mid in ACTIVE:
                mine = [it for it in todo[mid] if it[0] in paths]
                if not mine:
                    continue
                job.update(phase="model", model=MODELS[mid]["label"])
                by_path = {paths[it[0]]: it for it in mine}
                out, files = {}, list(by_path)
                with model_lock:
                    for i in range(0, len(files), 300):
                        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
                            csv_path = tf.name
                        r = subprocess.run([str(MODEL_PY), str(MODEL_SCRIPT), *files[i:i + 300], "--model", mid, "--top", "3",
                                            "--unsure-below", "0.5", "--csv", csv_path], capture_output=True, text=True, timeout=1800)
                        if r.returncode:
                            raise RuntimeError(f"The {MODELS[mid]['label']} model failed: " + (r.stderr or r.stdout)[-300:])
                        with open(csv_path, newline="") as fh:
                            for row in csv.DictReader(fh):
                                url, label, kind = by_path[row["file"]]
                                top = [[g.rsplit(" ", 1)[0], float(g.rsplit(" ", 1)[1])] for k, g in row.items() if k.startswith("guess") and g]
                                out[url] = {"scene_id": sid, "gallery": label, "gallery_type": kind, "label": row["answer"],
                                            "sub": row.get("sub") or None, "sub_conf": float(row["sub_conf"]) if row.get("sub_conf") else None,
                                            "best": top[0][0], "confidence": top[0][1], "top": top}
                        Path(csv_path).unlink(missing_ok=True)
                save_predictions(mid, out)
        job["phase"] = "done"
    except scraper.SessionError as e:
        job.update(phase="error", error=str(e), needs_setup=True)
    except Exception as e:
        job.update(phase="error", error=str(e) if isinstance(e, (LookupError, RuntimeError)) else f"{type(e).__name__}: {e}")


def start_predict(sid, refresh, only=None):
    if not re.fullmatch(r"\d+", sid):
        raise ValueError("bad scene id")
    with pred_lock:
        job = pred_jobs.get(sid)
        if job and job["phase"] in RUNNING:
            return job
        job = {"scene_id": sid, "phase": "queued", "error": None}
        pred_jobs[sid] = job
    threading.Thread(target=run_predict, args=(job, sid, refresh, only), daemon=True).start()
    return job


def prediction_results(sid):
    """Stills and photosets of one video; each image carries every model's prediction. complete = no model is missing on any image."""
    saved = load_predictions()["models"]
    galleries = (scraper._load_details().get(sid) or {}).get("galleries", [])
    out, complete = [], True
    for g in galleries:
        k = gallery_kind(g["label"])
        if not k:
            continue
        imgs = []
        for im in g.get("images", []):
            have = {mid: saved[mid]["images"][im["f"]] for mid in ACTIVE if im["f"] in saved[mid]["images"]}
            complete = complete and len(have) == len(ACTIVE)
            if have:
                imgs.append({"f": im["f"], "models": have})
        if imgs:
            out.append({"label": g["label"], "kind": k, "count": g["count"], "images": imgs})
    models = {mid: {"label": MODELS[mid]["label"], "has_sub": MODELS[mid]["has_sub"], "version": saved[mid]["meta"].get("version"),
                    "current_version": model_version(mid)} for mid in ACTIVE}
    return {"galleries": out, "models": models, "complete": bool(out) and complete}

def creators_list():
    """Every performer that has been scraped (the saved results files), with how many videos and how many have model results."""
    stars = {x["slug"]: x["name"] for x in (scraper.load_pornstars() or {}).get("stars", [])}
    predicted = {v.get("scene_id") for m in ACTIVE for v in load_predictions()["models"][m]["images"].values()}
    out = []
    for f in sorted(CACHE.glob("*.json")) if CACHE.exists() else []:
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        vids = r.get("videos", [])
        slug = r.get("slug") or f.stem
        out.append({"slug": slug, "name": stars.get(slug) or slug.replace("-", " ").title(), "videos": len(vids),
                    "with_model": sum(1 for v in vids if v.get("scene_id") in predicted),
                    "thumbnail": next((v.get("thumbnail") for v in vids if v.get("thumbnail")), ""),
                    "scraped": int(f.stat().st_mtime)})
    out.sort(key=lambda c: c["scraped"], reverse=True)
    return out


# ============================ run the model on many videos of one creator ============================
TMP = HERE / "data" / "tmp_batch"            # images for a batch are kept here only until the model has seen them (not in the image cache)
IMG_RATE = 8                                 # image downloads per second, all workers together (the brief for this tool: a few per second, politely)
CHUNK = 400                                  # images the model looks at per call (one call loads the model once)
IMG_WORKERS = 10                             # downloads in flight; the 8 per second cap above still applies to all of them together (6 workers could not reach it: each image takes about a second)
_img_lock, _img_next = threading.Lock(), [0.0]
_dl = threading.local()
BATCH = {"job": None}                        # one batch at a time


def _img_wait():
    with _img_lock:
        now = time.monotonic()
        t = max(now, _img_next[0])
        _img_next[0] = t + 1.0 / IMG_RATE
    if t > now:
        time.sleep(t - now)


def download_to(url, dest):
    """Save one image (only from *.dt18.com). Returns True if it worked."""
    u = urlparse(url)
    if u.scheme != "https" or not (u.hostname or "").endswith(".dt18.com"):
        return False
    if not hasattr(_dl, "s"):
        _dl.s = requests.Session()
        _dl.s.headers.update({"Referer": "https://www.data18.com/", "User-Agent": scraper.DEFAULT_UA})
    for _ in range(2):
        _img_wait()
        try:
            r = _dl.s.get(url, timeout=25)
        except requests.RequestException:
            continue
        if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/") and len(r.content) <= MAX_IMG_BYTES:
            dest.write_bytes(r.content)
            return True
    return False


def classify_paths(mid, by_path):
    """Run one model over image files. by_path: {file path: (url, gallery label, kind, scene_id)}. Returns {url: prediction}."""
    out = {}
    files = list(by_path)
    with model_lock:
        for i in range(0, len(files), 300):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
                csv_path = tf.name
            r = subprocess.run([str(MODEL_PY), str(MODEL_SCRIPT), *files[i:i + 300], "--model", mid, "--top", "3", "--unsure-below", "0.5",
                                "--csv", csv_path], capture_output=True, text=True, timeout=3600)
            if r.returncode:
                raise RuntimeError(f"The {MODELS[mid]['label']} model failed: " + (r.stderr or r.stdout)[-300:])
            with open(csv_path, newline="") as fh:
                for row in csv.DictReader(fh):
                    url, label, kind, sid = by_path[row["file"]]
                    top = [[g.rsplit(" ", 1)[0], float(g.rsplit(" ", 1)[1])] for k, g in row.items() if k.startswith("guess") and g]
                    out[url] = {"scene_id": sid, "gallery": label, "gallery_type": kind, "label": row["answer"],
                                "sub": row.get("sub") or None, "sub_conf": float(row["sub_conf"]) if row.get("sub_conf") else None,
                                "best": top[0][0], "confidence": top[0][1], "top": top}
            Path(csv_path).unlink(missing_ok=True)
    return out


def pick_scenes(slug, mode, count, kinds, only_new):
    path = CACHE / f"{slug}.json"
    if not path.exists():
        raise LookupError(f"'{slug}' has not been scraped yet.")
    videos = json.loads(path.read_text()).get("videos", [])
    done = {v.get("scene_id") for v in load_predictions()["models"]["b32"]["images"].values()}
    pool = [v for v in videos if any(gallery_kind(g["label"]) in kinds for g in v.get("galleries", []))]
    if only_new:
        pool = [v for v in pool if v["scene_id"] not in done]
    if mode == "random":
        pool = random.sample(pool, min(count, len(pool)))
    return pool


def run_batch(job, scenes, kinds):
    TMP.mkdir(parents=True, exist_ok=True)
    pending = {}                                   # file path -> (url, gallery label, kind, scene id)
    temp_files = []
    model_pool = ThreadPoolExecutor(1)             # the model works on one chunk in the background while the next images download
    inflight = []

    def classify_chunk(batch, files):
        try:
            save_predictions("b32", classify_paths("b32", batch))
            job["images_done"] += len(batch)
        finally:
            for f in files:
                Path(f).unlink(missing_ok=True)

    def wait_model():
        if inflight:
            fut = inflight.pop()
            if not fut.done():
                job["stage"] = "model"
            fut.result()                           # raises here if the model failed
            job["stage"] = "downloading"

    def flush():
        if not pending:
            return
        wait_model()                               # at most one chunk with the model at a time
        batch, files = dict(pending), list(temp_files)
        pending.clear()
        temp_files.clear()
        inflight.append(model_pool.submit(classify_chunk, batch, files))
    try:
        seen = set(load_predictions()["models"]["b32"]["images"])
        for n, v in enumerate(scenes, 1):
            if job["cancel"]:
                break
            sid = v["scene_id"]
            job.update(current=v.get("title", sid), stage="listing")
            try:
                items = [it for it in scene_items(sid) if it[2] in kinds]
            except scraper.SessionError:
                raise
            except Exception as e:
                job["failed_videos"] += 1
                job["last_error"] = f"{v.get('title', sid)}: {e}"
                job["videos_done"] = n
                continue
            todo = [it for it in items if it[0] not in seen]
            job["images_skipped"] += len(items) - len(todo)
            job["stage"] = "downloading"

            def fetch(it):
                url = it[0]
                key = hashlib.sha1(url.encode()).hexdigest()
                cached = next((c for c in IMG_CACHE.glob(key + ".*") if c.suffix != ".tmp"), None)
                if cached:
                    return str(cached), False
                dest = TMP / (key + ".jpg")
                return (str(dest), True) if download_to(url, dest) else (None, False)
            with ThreadPoolExecutor(IMG_WORKERS) as pool:
                got = list(pool.map(fetch, todo))
            for it, (path, temp) in zip(todo, got):
                if path is None:
                    job["failed_images"] += 1
                    continue
                pending[path] = (it[0], it[1], it[2], sid)
                seen.add(it[0])
                if temp:
                    temp_files.append(path)
            job["videos_done"] = n
            el = time.time() - job["started"]
            job["eta_seconds"] = round(el / n * (len(scenes) - n)) if n >= 2 else None
            if len(pending) >= CHUNK:
                flush()
        flush()
        wait_model()
        job["phase"] = "cancelled" if job["cancel"] else "done"
    except scraper.SessionError as e:
        job.update(phase="error", error=str(e), needs_setup=True)
    except Exception as e:
        job.update(phase="error", error=str(e) if isinstance(e, (LookupError, RuntimeError)) else f"{type(e).__name__}: {e}")
    finally:
        try:
            for fut in inflight:
                fut.result()                       # let a chunk the model is still working on finish (it removes its own files)
        except Exception:
            pass
        model_pool.shutdown(wait=False)
        for f in temp_files:
            Path(f).unlink(missing_ok=True)
        job["finished"] = time.time()


def start_batch(slug, mode, count, photosets, only_new):
    kinds = {"stills", "photoset"} if photosets else {"stills"}
    with pred_lock:
        cur = BATCH["job"]
        if cur and cur["phase"] == "running":
            raise RuntimeError(f"A batch for {cur['slug']} is already running. Cancel it or wait for it to finish.")
    scenes = pick_scenes(slug, mode, max(1, int(count or 1)), kinds, only_new)
    if not scenes:
        raise LookupError("No videos to run: every video of this creator with photos has already been analysed (untick 'only new videos' to run them again), or none has Video Stills.")
    job = {"slug": slug, "phase": "running", "stage": "listing", "mode": mode, "photosets": photosets, "videos_total": len(scenes), "videos_done": 0,
           "images_done": 0, "images_skipped": 0, "failed_videos": 0, "failed_images": 0, "current": "", "eta_seconds": None,
           "started": time.time(), "cancel": False, "error": None}
    with pred_lock:
        BATCH["job"] = job
    threading.Thread(target=run_batch, args=(job, scenes, kinds), daemon=True).start()
    return job


# ============================ the images grouped by the position the model found ============================
_idx_cache = {"scenes": (None, {}), "thumbs": (None, {})}


def scene_index():
    """scene id -> {title, url, creators[]} from every saved performer."""
    files = sorted(CACHE.glob("*.json")) if CACHE.exists() else []
    key = tuple((f.name, f.stat().st_mtime_ns) for f in files)
    if _idx_cache["scenes"][0] == key:
        return _idx_cache["scenes"][1]
    idx = {}
    for f in files:
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        for v in r.get("videos", []):
            e = idx.setdefault(v["scene_id"], {"title": v.get("title", ""), "url": v.get("url", ""), "date": v.get("date", ""), "creators": []})
            if (r.get("slug") or f.stem) not in e["creators"]:
                e["creators"].append(r.get("slug") or f.stem)
    _idx_cache["scenes"] = (key, idx)
    return idx


def thumb_map():
    """full image address -> its small thumbnail address."""
    det = scraper._load_details()
    key = (len(det), sum(len(d.get("galleries", [])) for d in det.values()))
    if _idx_cache["thumbs"][0] == key:
        return _idx_cache["thumbs"][1]
    m = {im["f"]: im.get("t") or im["f"] for d in det.values() for g in d.get("galleries", []) for im in g.get("images", [])}
    _idx_cache["thumbs"] = (key, m)
    return m


def kinds_of(t):
    return {"stills": {"stills"}, "photoset": {"photoset"}}.get(t, {"stills", "photoset"})


def grouped(creator, t, minconf, submin):
    """[(url, prediction, parent, sub, scene)] with every image placed in one group. Under minconf the parent is 'Unsure'."""
    saved = load_predictions()["models"]["b32"]["images"]
    idx, kinds, rows = scene_index(), kinds_of(t), []
    for url, p in saved.items():
        if p.get("gallery_type") not in kinds:
            continue
        sc = idx.get(p.get("scene_id"), {"title": "", "url": "", "creators": []})
        if creator and creator not in sc["creators"]:
            continue
        if p["confidence"] < minconf:
            parent, sub = "Unsure", None
        else:
            parent = p["best"]
            sub = None
            if p.get("sub"):
                sub = p["sub"] if (p.get("sub_conf") or 0) >= submin else "(no clear sub-type)"
        rows.append((url, p, parent, sub, sc))
    return rows


def position_groups(creator, t, minconf, submin):
    rows = grouped(creator, t, minconf, submin)
    thumbs = thumb_map()
    tree = {}
    for url, p, parent, sub, sc in rows:
        node = tree.setdefault(parent, {"name": parent, "count": 0, "subs": {}, "sample": []})
        node["count"] += 1
        if sub:
            node["subs"][sub] = node["subs"].get(sub, 0) + 1
        if len(node["sample"]) < 4 and p["confidence"] >= 0.8:
            node["sample"].append(thumbs.get(url, url))
    out = []
    for node in sorted(tree.values(), key=lambda n: (n["name"] == "Unsure", -n["count"])):
        node["subs"] = [{"name": k, "count": v} for k, v in sorted(node["subs"].items(), key=lambda kv: (kv[0].startswith("("), -kv[1]))]
        out.append(node)
    return {"total": len(rows), "positions": out, "videos": len({p.get("scene_id") for _, p, *_ in rows})}


def position_images(creator, t, minconf, submin, position, sub, sort, offset, limit):
    rows = [r for r in grouped(creator, t, minconf, submin) if r[2] == position and (not sub or r[3] == sub)]
    if sort == "random":
        random.Random(7).shuffle(rows)
    elif sort == "video":
        rows.sort(key=lambda r: (r[4].get("title", ""), -r[1]["confidence"]))
    else:
        rows.sort(key=lambda r: -r[1]["confidence"])
    thumbs = thumb_map()
    page = [{"f": url, "t": thumbs.get(url, url), "scene_id": p.get("scene_id"), "title": sc.get("title", ""), "scene_url": sc.get("url", ""),
             "creators": sc.get("creators", []), "gallery": p.get("gallery"), "kind": p.get("gallery_type"), "best": p["best"],
             "confidence": p["confidence"], "sub": p.get("sub"), "sub_conf": p.get("sub_conf"), "top": p.get("top")}
            for url, p, parent, sb, sc in rows[offset:offset + limit]]
    return {"total": len(rows), "images": page}


# ---- favourite frames: a heart on any image; the Favourites tab lists them. Stored as data/favourites.json {image address: {scene_id, added}}
FAV_FILE = HERE / "data" / "favourites.json"
fav_lock = threading.Lock()


def load_favs():
    try:
        d = json.loads(FAV_FILE.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_favs(d):
    tmp = FAV_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False))
    tmp.replace(FAV_FILE)


def favourites_list():
    favs = load_favs()
    preds = load_predictions()["models"]["b32"]["images"]
    idx, thumbs = scene_index(), thumb_map()
    out = []
    for url, f in favs.items():
        p = preds.get(url) or {}
        sid = f.get("scene_id") or p.get("scene_id")
        sc = idx.get(sid, {"title": "", "url": "", "creators": []})
        out.append({"f": url, "t": thumbs.get(url, url), "scene_id": sid, "title": sc.get("title", ""), "scene_url": sc.get("url", ""),
                    "creators": sc.get("creators", []), "best": p.get("best"), "confidence": p.get("confidence"), "sub": p.get("sub"),
                    "sub_conf": p.get("sub_conf"), "added": f.get("added", 0)})
    out.sort(key=lambda x: -x["added"])
    return out


FINDER_DIR = Path(__file__).resolve().parents[1] / "video-finder"
FINDER_URL = "http://127.0.0.1:8792"


def ensure_finder():
    """Video Finder is its own tool (~/video-finder). Start it if it is not answering; -> its address, or None."""
    def up():
        try:
            return requests.get(FINDER_URL + "/", timeout=2).status_code == 200
        except requests.RequestException:
            return False
    if up():
        return FINDER_URL
    script = FINDER_DIR / "start.sh"
    if not script.exists():
        return None
    subprocess.Popen(["/bin/bash", str(script)], env=dict(__import__("os").environ, NO_OPEN="1"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(20):
        time.sleep(0.5)
        if up():
            return FINDER_URL
    return None


STREAM_DIR = Path(__file__).resolve().parents[1] / "stream-test"
STREAM_URL = "http://127.0.0.1:8793"


def ensure_stream():
    """Stream test is its own tool (~/stream-test): plays a video straight from its site and takes frames from it. Start it if it is not answering; -> its address, or None."""
    def up():
        try:
            return requests.get(STREAM_URL + "/", timeout=2).status_code == 200
        except requests.RequestException:
            return False
    if up():
        return STREAM_URL
    script = STREAM_DIR / "start.sh"
    if not script.exists():
        return None
    subprocess.Popen(["/bin/zsh", str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(20):
        time.sleep(0.5)
        if up():
            return STREAM_URL
    return None


# ---- download a chosen Finder result with the Links tool, then let the existing pipeline run the model on it
LINKS_URL = "http://127.0.0.1:8791"
BOT = Path(__file__).resolve().parents[2]
DRAFTS = BOT / "CLIP Training" / "drafts"
fdl = {}                         # scene_id -> what the download of the chosen result is doing
fdl_lock = threading.Lock()


def library_dir():
    try:
        with open(Path(__file__).resolve().parents[2] / "tools" / "links" / "ui" / "data" / "settings.json") as f:
            return Path(json.load(f).get("library_dir") or (BOT / "library"))
    except (OSError, ValueError):
        return BOT / "library"


def norm_name(name):
    """Same rule the model pipeline (auto_analyse.py) uses to match a video to its draft: no extension, no trailing [id], lowercase."""
    base = re.sub(r"\.(mp4|mov|mkv|avi|webm|m4v|wmv|flv)$", "", name or "", flags=re.I)
    base = re.sub(r"\s*\[[^\]]*\]\s*$", "", base)
    return re.sub(r"\s+", " ", base).strip().lower()


def draft_exists(file_name):
    key = norm_name(file_name)
    try:
        return any(norm_name(d.name) == key for d in DRAFTS.iterdir() if d.is_dir())
    except OSError:
        return False


def creator_slug(scene_id):
    """Which saved creator this scene belongs to (that is the library folder its video goes into)."""
    for path in sorted(CACHE.glob("*.json")) if CACHE.exists() else []:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for v in (data.get("videos") if isinstance(data, dict) else data) or []:
            if str(v.get("scene_id")) == str(scene_id):
                return path.stem
    return ""


def still_info(scene_id, image_url):
    """Which video still this image is -> {k (1 = the first, at 0:00), n (how many video stills the scene has)} or None (not a video still).
    data18 names the gallery "Video Stills" or "Videostills", and long scenes split it into "Video Stills 1", "Video Stills 2": those are counted as one list, in that order."""
    det = scraper._load_details().get(str(scene_id)) or {}
    galleries = [g for g in det.get("galleries", []) if re.match(r"video\s?stills", g.get("label") or "", re.I)]
    galleries.sort(key=lambda g: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", g.get("label") or "")])
    imgs = [i["f"] for g in galleries for i in g.get("images", [])]
    if image_url in imgs:
        return {"k": imgs.index(image_url) + 1, "n": len(imgs), "split": len(galleries) > 1}
    return None


def library_folder_for(name):
    """The library folder for a creator: an existing folder whose name matches ignoring case, '-', '_' and spaces (same rule as the Links tool)."""
    key = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    try:
        for d in library_dir().iterdir():
            if d.is_dir() and key(d.name) == key(name):
                return d.name
    except OSError:
        pass
    return re.sub(r"[ _]+", "-", name).strip("-").lower() or "unsorted"


def await_model(st):
    """The model pipeline (auto_analyse) finds a new video in the library by itself; say when its draft appears."""
    for _ in range(600):
        time.sleep(3)
        if draft_exists(st["file"]):
            return st.update(state="analysed", message="Analysed by the model. The sections are in the Analysis page.")
    st.update(message="Saved. The model has not started on it yet (it waits until the file has stopped changing).")


def run_finder_clip(st):
    """Save only a clip around the chosen still (remote_clip.py reads just that part of the video). `st` is the download's record."""
    status_file = HERE / "data" / ("tmp_clip_%s.json" % uuid.uuid4().hex[:8])
    out_dir = library_dir() / library_folder_for(st["folder"])
    cmd = ["/usr/bin/python3", str(BOT / "remote_clip.py"), "--url", st["url"], "--out-dir", str(out_dir), "--name", st["title"] or "video", "--k", str(st["k"]),
           "--count", str(st["n"]), "--d18-seconds", str(int(st["d18"] or 0)), "--window", str(int(st.get("window") or 180)), "--status", str(status_file)]
    st.update(state="downloading", message="Finding the video…")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except OSError as e:
        return st.update(state="failed", message="Couldn't start the clip tool: %s" % e)
    def read():
        try:
            return json.loads(status_file.read_text())
        except (OSError, ValueError):
            return {}
    while proc.poll() is None:
        d = read()
        st.update(pct=d.get("progress"), mb=d.get("mb"), message=d.get("message") or st["message"], part=[d.get("start"), d.get("end")] if d.get("start") is not None else None)
        time.sleep(1)
    out = proc.stdout.read() if proc.stdout else ""
    d = read()
    status_file.unlink(missing_ok=True)
    if d.get("phase") != "done" or not d.get("file"):
        return st.update(state="failed", message=d.get("error") or ("The clip tool failed. " + out.strip()[-200:]))
    st.update(state="downloaded", file=Path(d["file"]).name, dest=d["file"], pct=100, mb=d.get("mb"), part=[d.get("start"), d.get("end")],
              message="Saved the clip %s. Waiting for the model: it starts by itself within a couple of minutes." % d.get("message", "").replace("Saved the clip ", "").rstrip("."))
    threading.Thread(target=await_model, args=(st,), daemon=True).start()      # (does not hold up the next clip in a queue)


# ---- what the page remembers about each video: which Video Finder search belongs to it, and which result you chose
FL_FILE = HERE / "data" / "finder_links.json"
fl_lock = threading.Lock()


def load_fl():
    try:
        d = json.loads(FL_FILE.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_fl(d):
    tmp = FL_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False))
    tmp.replace(FL_FILE)


def fl_update(sid, **fields):
    with fl_lock:
        d = load_fl()
        d.setdefault(str(sid), {}).update(fields)
        save_fl(d)


def finder_job(jid):
    try:
        r = requests.get(FINDER_URL + "/api/job", params={"id": jid}, timeout=15)
        return r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def summarize_job(job):
    """A short summary of a finished search (what the buttons on the image tiles show)."""
    rank = {"confident": 0, "possible": 1}
    hits = [(rank[d["verdict"]], -d["ranked"][0]["score"], site, d["ranked"][0], d["verdict"]) for site, d in job["sites"].items() if d.get("verdict") in rank and d.get("ranked")]
    hits.sort(key=lambda h: h[:3])
    best = None
    if hits:
        _, _, site, c, v = hits[0]
        best = {"site": site, "verdict": v, "score": c["score"], "title": c["title"], "duration": c.get("duration")}
    return {"sites": len(job["sites"]), "confident": sum(1 for h in hits if h[4] == "confident"), "possible": sum(1 for h in hits if h[4] == "possible"), "best": best}


def watch_finder_job(sid, jid):
    """Wait for a search to finish (even if the page is closed) and record its summary."""
    for _ in range(400):
        time.sleep(2)
        job = finder_job(jid)
        if not job:
            return
        if job.get("state") == "done":
            return fl_update(sid, summary=summarize_job(job), done=int(time.time()))


# ---- automatic video search: after a creator is scraped, find each video's link with Video Finder, one video at a time (it is polite to the sites and each search already runs them side by side)
AUTO_FILE = HERE / "data" / "autofind.json"
AUTO_DEFAULTS = {"enabled": True, "streamable_only": True, "auto_select": True}
AUTO = {"queue": [], "running": False, "slug": "", "total": 0, "done": 0, "found": 0, "chosen": 0, "none": 0, "failed": 0, "current": "", "paused": False, "stop": False, "started": 0, "error": ""}
auto_lock = threading.Lock()


def auto_settings():
    try:
        d = json.loads(AUTO_FILE.read_text())
    except (OSError, ValueError):
        d = {}
    return {k: bool(d.get(k, v)) for k, v in AUTO_DEFAULTS.items()}


def auto_save_settings(**changes):
    d = auto_settings()
    d.update({k: bool(v) for k, v in changes.items() if k in AUTO_DEFAULTS})
    AUTO_FILE.write_text(json.dumps(d))
    return d


def auto_one(sid, cfg):
    """Search the sites for one video, wait for the result, remember it (and choose the match when it is confident). -> 'chosen' | 'found' | 'none'"""
    base = ensure_finder()
    if not base:
        raise RuntimeError("Video Finder could not be started (is ~/video-finder there?).")
    r = requests.post(base + "/api/search", json={"input": "https://www.data18.com/scenes/" + sid, "streamable_only": cfg["streamable_only"]}, timeout=60)
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", "Video Finder refused the search."))
    jid = data["id"]
    fl_update(sid, job=jid, summary=None, sel=None, started=int(time.time()), auto=True)
    job = None
    for _ in range(450):                                     # up to 15 minutes
        time.sleep(2)
        job = finder_job(jid)
        if job is None:
            raise RuntimeError("Video Finder stopped answering.")
        if job.get("state") == "done":
            break
    else:
        raise RuntimeError("the search took too long")
    summary = summarize_job(job)
    fl_update(sid, summary=summary, done=int(time.time()))
    best = summary["best"]
    if not best:
        return "none"
    if cfg["auto_select"] and best["verdict"] == "confident":
        d = job["sites"][best["site"]]["ranked"][0]
        fl_update(sid, sel={"site": best["site"], "url": d["url"], "title": d["title"], "duration": int(d.get("duration") or 0)}, auto=True)
        return "chosen"
    return "found"


def auto_worker():
    while True:
        with auto_lock:
            if AUTO["stop"] or not AUTO["queue"]:
                AUTO.update(running=False, current="", stop=False)
                return
            paused = AUTO["paused"]
            sid, title = (None, "") if paused else AUTO["queue"].pop(0)
        if paused:
            time.sleep(2)
            continue
        AUTO["current"] = title or sid
        try:
            res = auto_one(sid, auto_settings())
            AUTO["found" if res in ("found", "chosen") else "none"] += 1
            if res == "chosen":
                AUTO["chosen"] += 1
            AUTO["error"] = ""
        except Exception as e:
            AUTO["failed"] += 1
            AUTO["error"] = "%s: %s" % (title or sid, e)
            if "Video Finder" in str(e):                     # the Finder is down: stop instead of failing every video
                with auto_lock:
                    AUTO.update(running=False, queue=[], current="")
                return
        AUTO["done"] += 1


def auto_enqueue(slug, again=False):
    """Queue every video of a saved creator that has not been searched yet. -> number queued"""
    path = CACHE / ("%s.json" % slug)
    if not path.exists():
        raise LookupError("'%s' has not been scraped yet." % slug)
    videos = json.loads(path.read_text()).get("videos", [])
    saved = load_fl()
    todo = [(v["scene_id"], v.get("title", "")) for v in videos if v.get("scene_id") and (again or not (saved.get(str(v["scene_id"])) or {}).get("job"))]
    with auto_lock:
        queued = {sid for sid, _ in AUTO["queue"]}
        todo = [t for t in todo if t[0] not in queued]
        if not todo:
            return 0
        if not AUTO["running"]:
            AUTO.update(queue=[], total=0, done=0, found=0, chosen=0, none=0, failed=0, error="", slug=slug, started=time.time(), paused=False, stop=False)
        elif AUTO["slug"] != slug:
            AUTO["slug"] = AUTO["slug"] + " + " + slug
        AUTO["queue"].extend(todo)
        AUTO["total"] += len(todo)
        if not AUTO["running"]:
            AUTO["running"] = True
            threading.Thread(target=auto_worker, daemon=True).start()
    return len(todo)


def clip_window(raw):
    try:
        return max(10, min(900, int(float(raw))))
    except (TypeError, ValueError):
        return 180


# ---- many clips at once: a queue, a few at a time (each reads from a site, so not too many together)
clip_queue = queue.Queue()
clip_batches = {}
clip_workers = []
CLIP_WORKERS = 2


def clip_worker():
    while True:
        item = clip_queue.get()
        try:
            if item["state"] == "queued":
                run_finder_clip(item)
        except Exception as e:
            item.update(state="failed", message="Unexpected error: %s" % e)


def start_clip_batch(items, window, test_folder):
    if not clip_workers:
        for _ in range(CLIP_WORKERS):
            t = threading.Thread(target=clip_worker, daemon=True)
            t.start()
            clip_workers.append(t)
    bid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    jobs, out = {}, []
    for raw in items[:300]:
        sid, still, link, jid = str(raw.get("scene_id", "")), str(raw.get("still", "")), str(raw.get("url", "")), str(raw.get("job", ""))
        it = dict(id=uuid.uuid4().hex[:8], scene_id=sid, still=still, url=link, state="queued", mode="part", window=window, message="Waiting in line…",
                  pct=None, mb=None, file="", dest="", site="", title="", k=0, n=0, d18=0, folder="", part=None)
        def bad(msg):
            it.update(state="failed", message=msg)
        out.append(it)
        if not re.fullmatch(r"\d{4,}", sid) or not re.fullmatch(r"[\w-]+", jid):
            bad("Bad request."); continue
        if jid not in jobs:
            jobs[jid] = finder_job(jid)
        job = jobs[jid]
        found = next(((site, c) for site, d in ((job or {}).get("sites") or {}).items() for c in d.get("ranked", []) if c.get("url") == link), None)
        if not found:
            bad("That link is not one of the results Video Finder found for this video."); continue
        info = still_info(sid, still)
        if not info:
            bad("This image is not one of the video stills."); continue
        it.update(site=found[0], title=found[1].get("title", ""), k=info["k"], n=info["n"], d18=int((job.get("want") or {}).get("duration") or 0),
                  folder=test_folder if re.fullmatch(r"zz-test-[a-z0-9-]{1,30}", test_folder) else (creator_slug(sid) or "unsorted"))
    batch = {"id": bid, "window": window, "items": out, "created": time.time()}
    clip_batches[bid] = batch
    for old in sorted(clip_batches)[:-20]:
        del clip_batches[old]
    for it in out:
        if it["state"] == "queued":
            clip_queue.put(it)
    return batch


def run_finder_download(sid):
    st = fdl[sid]

    def fail(msg):
        st.update(state="failed", message=msg)

    # 1. hand the link to the Links tool (it runs one job at a time: wait while it is busy)
    for _ in range(600):
        try:
            r = requests.post(LINKS_URL + "/api/download", json={"mode": "manual", "manual": st["url"], "manual_folder": st["folder"], "n": 1},
                              headers={"X-UI": "1"}, timeout=30)    # the Links tool only takes requests marked as coming from its own interface
        except requests.RequestException as e:
            return fail("The Links tool didn't answer (is it running on port 8791?): %s" % e)
        if r.status_code == 200:
            break
        msg = ""
        try:
            msg = r.json().get("error", "")
        except ValueError:
            pass
        if r.status_code == 409 and "already running" in msg.lower():
            st.update(state="queued", message="Waiting for another Links download to finish…")
            time.sleep(3)
            continue
        return fail(msg or "The Links tool refused the download (HTTP %d)." % r.status_code)
    else:
        return fail("The Links tool stayed busy for 30 minutes.")
    st.update(state="downloading", message="Downloading…")

    # 2. follow it
    item = None
    for _ in range(3600):
        try:
            j = requests.get(LINKS_URL + "/api/job", timeout=15).json()
        except (requests.RequestException, ValueError):
            time.sleep(2)
            continue
        item = next((i for i in (j.get("items") or []) if i.get("url") == st["url"]), None)
        if item:
            st.update(pct=item.get("pct"), mb=item.get("mb"))
        job = j.get("job") or {}
        if job.get("status") in ("done", "failed", "stopped"):
            break
        time.sleep(1.5)
    if not item or item.get("status") != "done" or not item.get("file"):
        reason = (item or {}).get("reason") or "The Links tool could not download this video."
        return fail("Download failed: %s" % reason)
    folder = item.get("folder") or st["folder"]
    dest = library_dir() / folder / Path(item["file"]).name
    st.update(state="downloaded", file=Path(item["file"]).name, dest=str(dest), pct=100, message="Downloaded. Waiting for the model: it starts by itself within a couple of minutes.")

    # 3. the model pipeline (auto_analyse) finds the new file by itself; say when its draft appears
    await_model(st)



class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            return self.send(200, (HERE / "static" / "index.html").read_bytes(), "text/html")
        if u.path == "/api/favourites":
            favs = favourites_list()
            return self.send(200, {"total": len(favs), "favourites": favs})
        if u.path == "/api/favourites/urls":
            return self.send(200, {"urls": list(load_favs())})
        if u.path == "/api/favourites/toggle":
            url, sid = (q.get("url") or [""])[0], (q.get("scene_id") or [""])[0]
            known = load_predictions()["models"]["b32"]["images"]
            if not url.startswith("http") or (url not in known and url not in thumb_map()):
                return self.send(400, {"error": "That is not one of the saved data18 images."})
            with fav_lock:
                favs = load_favs()
                if url in favs:
                    del favs[url]
                    now = False
                else:
                    favs[url] = {"scene_id": sid or (known.get(url) or {}).get("scene_id") or "", "added": int(time.time())}
                    now = True
                save_favs(favs)
            return self.send(200, {"favourite": now, "count": len(favs)})
        if u.path == "/api/autofind/status":   # progress of the automatic video search, and its settings
            with auto_lock:
                st = {k: v for k, v in AUTO.items() if k != "queue"}
                st["queued"] = len(AUTO["queue"])
            return self.send(200, {"settings": auto_settings(), "state": st})
        if u.path == "/api/autofind/config":
            return self.send(200, auto_save_settings(**{k: (q.get(k) or [""])[0] == "1" for k in AUTO_DEFAULTS if k in q}))
        if u.path == "/api/autofind/start":    # search the videos of one saved creator that have not been searched yet
            slug = (q.get("slug") or [""])[0]
            try:
                n = auto_enqueue(slug, (q.get("again") or [""])[0] == "1")
            except LookupError as e:
                return self.send(404, {"error": str(e)})
            return self.send(200, {"queued": n})
        if u.path in ("/api/autofind/pause", "/api/autofind/resume", "/api/autofind/stop"):
            with auto_lock:
                if u.path.endswith("pause"):
                    AUTO["paused"] = True
                elif u.path.endswith("resume"):
                    AUTO["paused"] = False
                else:
                    AUTO.update(queue=[], stop=True, paused=False)
            return self.send(200, {"ok": True})
        if u.path == "/api/stream/ensure":   # make sure Stream test is running, hand back its address
            base = ensure_stream()
            if not base:
                return self.send(503, {"error": "Stream test could not be started (is ~/stream-test there?)."})
            return self.send(200, {"url": base})
        if u.path == "/api/finder/start":    # search the other sites for one data18 scene with Video Finder (a separate tool); hands back its search
            sid = (q.get("scene_id") or [""])[0]
            if not re.fullmatch(r"\d{4,}", sid):
                return self.send(400, {"error": "no scene number"})
            base = ensure_finder()
            if not base:
                return self.send(503, {"error": "Video Finder could not be started (is ~/video-finder there?)."})
            saved = load_fl().get(sid) or {}
            if saved.get("job") and (q.get("force") or [""])[0] != "1":      # this video was searched before: show that, do not search again
                job = finder_job(saved["job"])
                if job:
                    job["finder_url"] = base
                    job["reused"] = True
                    job["sel"] = saved.get("sel")
                    return self.send(200, job)
            try:
                r = requests.post(base + "/api/search", json={"input": "https://www.data18.com/scenes/" + sid, "all_sites": (q.get("all") or [""])[0] == "1"}, timeout=60)
                data = r.json()
            except (requests.RequestException, ValueError) as e:
                return self.send(502, {"error": "Video Finder didn't answer: %s" % e})
            if r.status_code != 200:
                return self.send(r.status_code, {"error": data.get("error", "Video Finder refused the search.")})
            data["finder_url"] = base
            fl_update(sid, job=data["id"], summary=None, sel=None, started=int(time.time()))
            threading.Thread(target=watch_finder_job, args=(sid, data["id"]), daemon=True).start()
            return self.send(200, data)
        if u.path == "/api/finder/links":    # every video that has been searched, with a short summary and the result chosen for it
            return self.send(200, {"links": load_fl()})
        if u.path == "/api/finder/select":   # remember which result is the right one for a video (empty url = forget the choice)
            sid, link = (q.get("scene_id") or [""])[0], (q.get("url") or [""])[0]
            if not re.fullmatch(r"\d{4,}", sid) or sid not in load_fl():
                return self.send(400, {"error": "unknown video"})
            sel = {"site": (q.get("site") or [""])[0], "url": link, "title": (q.get("title") or [""])[0], "duration": int(float((q.get("duration") or ["0"])[0] or 0))} if link.startswith("http") else None
            fl_update(sid, sel=sel)
            return self.send(200, {"ok": True})
        if u.path == "/api/finder/clips/status":
            b = clip_batches.get((q.get("batch") or [""])[0])
            if not b:
                return self.send(404, {"error": "no such batch"})
            return self.send(200, {"id": b["id"], "window": b["window"], "items": b["items"]})
        if u.path == "/api/finder/stillinfo":  # where in the video is this still? (video stills are one per minute, the first at 0:00)
            sid, still, jid = (q.get("scene_id") or [""])[0], (q.get("still") or [""])[0], (q.get("job") or [""])[0]
            info = still_info(sid, still)
            if not info:
                return self.send(200, {"ok": False, "why": "This image is not one of the video stills, so it cannot be placed in the video."})
            d18 = 0
            if re.fullmatch(r"[\w-]+", jid):
                try:
                    d18 = int(requests.get(FINDER_URL + "/api/job", params={"id": jid}, timeout=15).json().get("want", {}).get("duration") or 0)
                except (requests.RequestException, ValueError):
                    d18 = 0
            k, n = info["k"], info["n"]
            out = {"ok": True, "k": k, "n": n, "d18": d18, "verified": bool(d18), "split": info.get("split", False)}
            if d18 and abs(n - d18 / 60.0) > 2.5:
                out.update(ok=False, why="This scene has %d video stills for %d minutes, so they are not one per minute and a clip cannot be placed reliably." % (n, round(d18 / 60.0)))
            w = clip_window((q.get("window") or ["180"])[0])
            start = max(0, (k - 1) * 60 - w // 2); end = start + w
            if d18 and end > d18:
                start, end = max(0, d18 - w), d18
            out.update(start=start, end=end, window=w)
            return self.send(200, out)
        if u.path == "/api/finder/download":   # download one chosen result (it must be one the Finder really found for this scene)
            sid, jid, link = (q.get("scene_id") or [""])[0], (q.get("job") or [""])[0], (q.get("url") or [""])[0]
            test_folder = (q.get("test_folder") or [""])[0]
            if not re.fullmatch(r"\d{4,}", sid) or not re.fullmatch(r"[\w-]+", jid) or not link.startswith("http"):
                return self.send(400, {"error": "bad request"})
            try:
                job = requests.get(FINDER_URL + "/api/job", params={"id": jid}, timeout=15).json()
            except (requests.RequestException, ValueError):
                return self.send(502, {"error": "Video Finder didn't answer."})
            found = next(((site, c) for site, d in (job.get("sites") or {}).items() for c in d.get("ranked", []) if c.get("url") == link), None)
            if not found:
                return self.send(400, {"error": "That link is not one of the results Video Finder found."})
            folder = test_folder if re.fullmatch(r"zz-test-[a-z0-9-]{1,30}", test_folder) else (creator_slug(sid) or "unsorted")
            still = (q.get("still") or [""])[0]
            part = None
            if still:                                       # only a clip around this video still
                info = still_info(sid, still)
                if not info:
                    return self.send(400, {"error": "That image is not one of this scene's video stills."})
                part = dict(k=info["k"], n=info["n"], d18=int((job.get("want") or {}).get("duration") or 0), window=clip_window((q.get("window") or ["180"])[0]))
            with fdl_lock:
                cur = fdl.get(sid)
                if cur and cur["state"] in ("queued", "downloading"):
                    return self.send(409, {"error": "A download for this video is already running."})
                fdl[sid] = dict(state="queued", mode="part" if part else "whole", site=found[0], url=link, title=found[1].get("title", ""), folder=folder, message="Starting…",
                                pct=None, mb=None, file="", dest="", **(part or {}))
            threading.Thread(target=run_finder_clip if part else run_finder_download, args=(fdl[sid] if part else sid,), daemon=True).start()
            return self.send(200, fdl[sid])
        if u.path == "/api/finder/dlstatus":
            return self.send(200, fdl.get((q.get("scene_id") or [""])[0]) or {"state": "none"})
        if u.path == "/api/finder/job":      # progress and results of that search
            jid = (q.get("id") or [""])[0]
            if not re.fullmatch(r"[\w-]+", jid):
                return self.send(400, {"error": "bad id"})
            try:
                r = requests.get(FINDER_URL + "/api/job", params={"id": jid}, timeout=15)
                return self.send(r.status_code, r.json())
            except (requests.RequestException, ValueError) as e:
                return self.send(502, {"error": "Video Finder didn't answer: %s" % e})
        if u.path == "/api/finder/img":      # a result's thumbnail (fetched by the Finder, which knows each site's rules)
            jid, link = (q.get("id") or [""])[0], (q.get("u") or [""])[0]
            if not re.fullmatch(r"[\w-]+", jid) or not link:
                return self.send(400, {"error": "bad request"})
            try:
                r = requests.get(FINDER_URL + "/img", params={"id": jid, "u": link}, timeout=30)
            except requests.RequestException:
                return self.send(502, {"error": "no image"})
            if r.status_code != 200:
                return self.send(404, {"error": "no image"})
            self.send_response(200)
            self.send_header("Content-Type", r.headers.get("Content-Type", "image/jpeg"))
            self.send_header("Content-Length", str(len(r.content)))
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            return self.wfile.write(r.content)
        if u.path == "/api/status":
            saved = sorted(p.stem for p in CACHE.glob("*.json")) if CACHE.exists() else []
            return self.send(200, {"session": scraper.SESSION_FILE.exists(), "saved": saved})
        if u.path == "/api/scrape":          # start (or follow) a job
            try:
                job = start_job((q.get("name") or [""])[0], q.get("refresh") == ["1"])
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            return self.send(200, {"slug": job["slug"]})
        if u.path == "/api/job":             # poll a job
            slug = (q.get("slug") or [""])[0]
            job = jobs.get(slug)
            if not job:
                return self.send(404, {"error": "no such job"})
            return self.send(200, snapshot(job))
        if u.path == "/api/studios":         # saved studio list
            return self.send(200, scraper.load_studios() or {"studios": [], "total": 0, "scraped_at": None})
        if u.path == "/api/studios/refresh":  # re-scrape the list from data18 in the background
            with jobs_lock:
                if studios_job["phase"] != "running":
                    studios_job.update(phase="running", page=0, count=0, error=None, needs_setup=False)
                    threading.Thread(target=run_studios_job, daemon=True).start()
            return self.send(200, dict(studios_job))
        if u.path == "/api/studios/job":
            return self.send(200, dict(studios_job))
        if u.path == "/api/tags":            # the tag list, with how many scraped videos each one has
            data = scraper.load_tags() or {"tags": [], "total": 0, "scraped_at": None}
            idx = tag_index()
            known = {t["slug"] for t in data["tags"]}
            return self.send(200, {**data,
                                   "tags": [{**t, "videos": len(idx.get(t["slug"], {}))} for t in data["tags"]],
                                   "unlisted": sorted(sl for sl in idx if sl not in known)})
        if u.path == "/api/tag-videos":      # the scraped videos that have one tag
            vids = list(tag_index().get((q.get("slug") or [""])[0], {}).values())
            vids.sort(key=lambda v: int(v["scene_id"]), reverse=True)
            return self.send(200, {"videos": vids})
        if u.path == "/api/pornstars":       # compact rows: [slug, name, picture, scenes, movies, rank]
            d = scraper.load_pornstars()
            if not d:
                return self.send(200, {"stars": [], "total": 0, "scraped_at": None})
            return self.send(200, {"total": d["total"], "scraped_at": d["scraped_at"],
                                   "stars": [[x["slug"], x["name"], x["picture"], x["scenes"], x["movies"], x["rank"]] for x in d["stars"]]})
        if u.path == "/api/pornstars/refresh":
            with jobs_lock:
                if stars_job["phase"] != "running":
                    stars_job.update(phase="running", page=0, count=0, error=None, needs_setup=False, started=time.time())
                    threading.Thread(target=run_stars_job, daemon=True).start()
            return self.send(200, dict(stars_job))
        if u.path == "/api/pornstars/job":
            return self.send(200, dict(stars_job))
        if u.path == "/api/photos":          # galleries (with image addresses) for one video
            galleries = scraper.scene_galleries((q.get("scene_id") or [""])[0])
            if galleries is None:
                return self.send(404, {"error": "photos not fetched yet"})
            return self.send(200, {"galleries": galleries})
        if u.path == "/api/batch/status":    # the running (or last) batch
            j = BATCH["job"]
            return self.send(200, {"job": ({k: v for k, v in j.items() if k != "cancel"} | {"cancelling": j["cancel"] and j["phase"] == "running"}) if j else None})
        if u.path in ("/api/position-groups", "/api/position-images"):
            def num(k, d):
                try:
                    return float((q.get(k) or [d])[0])
                except ValueError:
                    return float(d)
            creator, t = (q.get("creator") or [""])[0], (q.get("type") or ["stills"])[0]
            if u.path == "/api/position-groups":
                return self.send(200, position_groups(creator, t, num("min", 0.5), num("submin", 0)))
            return self.send(200, position_images(creator, t, num("min", 0.5), num("submin", 0), (q.get("position") or [""])[0], (q.get("sub") or [""])[0],
                                                  (q.get("sort") or ["conf"])[0], int(num("offset", 0)), min(300, int(num("limit", 120)))))
        if u.path == "/api/creators":        # every performer scraped so far
            return self.send(200, {"creators": creators_list()})
        if u.path == "/api/predict":         # start (or follow) a model run on one video
            try:
                job = start_predict((q.get("scene_id") or [""])[0], q.get("refresh") == ["1"])
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            return self.send(200, dict(job))
        if u.path == "/api/predictions":     # the run's progress + any saved predictions for one video
            sid = (q.get("scene_id") or [""])[0]
            return self.send(200, {"job": dict(pred_jobs.get(sid) or {"phase": "idle"}), **prediction_results(sid)})
        if u.path == "/img":                 # image proxy: /img?u=https://i5.dt18.com/...
            try:
                body, ctype = fetch_image((q.get("u") or [""])[0])
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            except Exception as e:
                return self.send(502, {"error": str(e)})
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send(404, {"error": "not found"})


    def do_POST(self):
        u = urlparse(self.path)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self.send(400, {"error": "bad request"})
        if u.path == "/api/predict-images":  # run the model on a hand-picked set of images of one video
            urls = [x for x in body.get("urls", []) if isinstance(x, str)][:2000]
            if not urls:
                return self.send(400, {"error": "no images selected"})
            try:
                job = start_predict(str(body.get("scene_id", "")), False, set(urls))
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            return self.send(200, dict(job))
        if u.path == "/api/finder/clips":    # download a clip for each of many chosen frames (queued, a couple at a time)
            items = body.get("items")
            if not isinstance(items, list) or not items:
                return self.send(400, {"error": "no frames chosen"})
            tf = str(body.get("test_folder") or "")
            b = start_clip_batch(items, clip_window(body.get("window")), tf)
            return self.send(200, {"id": b["id"], "window": b["window"], "items": b["items"]})
        if u.path == "/api/batch/start":     # run the model on many of one creator's videos
            try:
                job = start_batch(str(body.get("slug", "")), "random" if body.get("mode") == "random" else "all", body.get("count") or 50,
                                  bool(body.get("photosets")), body.get("only_new", True) is not False)
            except (LookupError, RuntimeError, ValueError) as e:
                return self.send(409 if isinstance(e, RuntimeError) else 400, {"error": str(e)})
            return self.send(200, {"started": True, "videos_total": job["videos_total"]})
        if u.path == "/api/batch/cancel":
            if BATCH["job"] and BATCH["job"]["phase"] == "running":
                BATCH["job"]["cancel"] = True
            return self.send(200, {"ok": True})
        self.send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"data18 scraper dashboard: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
