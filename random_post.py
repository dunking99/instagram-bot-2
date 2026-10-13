"""
STEP 2 - Pick a random post from an Instagram profile (headless).

Requires auth.json from login.py (run `python login.py` first).

Run:
    python random_post.py some_username
    python random_post.py some_username --max-scrolls 300 --no-open

What it does:
  1. Loads auth.json so the profile is viewed as a logged-in user.
  2. Reads the profile's total post count from its header metadata.
  3. Scrolls the grid to lazy-load older posts, collecting every /p/ and /reel/
     link (re-collected after each scroll in case the grid recycles DOM nodes).
  4. Picks one link uniformly at random, prints it, opens it in your default browser.

Note: the pick is uniform over the posts that were actually loaded. If scrolling
stops early (rate limiting, --max-scrolls) the script warns you that the pool is
only a partial sample of the catalog.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import sys
import time
import webbrowser
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

AUTH_FILE = Path(__file__).with_name("auth.json")
CACHE_DIR = Path(__file__).with_name("cache")
BASE = os.environ.get("RPP_BASE", "https://www.instagram.com")   # env override is for local tests only


def cache_path(username: str) -> Path:
    return CACHE_DIR / f"{username.lower()}.json"

# Matches /p/<id>/, /reel/<id>/, /reels/<id>/ (optionally prefixed by /<username>/).
POST_PATH = re.compile(r"^/(?:[^/]+/)?(?:p|reel|reels)/[\w-]+/?$")


class ScrapeError(Exception):
    """A user-facing, expected failure (bad session, private account, ...)."""


def parse_count(text: str) -> int:
    """'1,234' -> 1234, '12.5K' -> 12500, '1.2M' -> 1200000."""
    text = text.strip().replace(",", "")
    mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(text[-1:].lower(), 1)
    return int(float(text[:-1] if mult != 1 else text) * mult)


def read_post_count(page) -> int | None:
    """Parse '... 123 Posts' from the og:description / description meta tag."""
    for sel in ('meta[property="og:description"]', 'meta[name="description"]'):
        el = page.query_selector(sel)
        content = el.get_attribute("content") if el else None
        m = content and re.search(r"([\d.,]+[KkMmBb]?)\s+Posts", content)
        if m:
            return parse_count(m.group(1))
    return None


def check_page_state(page, username: str) -> None:
    """Raise ScrapeError for login walls, missing profiles, and private accounts."""
    if "/accounts/login" in page.url or page.query_selector('input[name="username"]'):
        raise ScrapeError("Session expired or invalid. Re-run `python login.py` to refresh auth.json.")
    body = page.inner_text("body")
    if "isn't available" in body or "Page Not Found" in body:
        raise ScrapeError(f"Profile '{username}' does not exist (or has been removed).")
    if "This account is private" in body or "This Account is Private" in body:
        raise ScrapeError(f"'{username}' is private and your account doesn't follow it.")
    if "Try again later" in body or "Please wait a few minutes" in body:
        raise ScrapeError("Instagram is rate limiting this session. Wait a while and retry.")


def collect_links(page) -> dict[str, tuple[str, str]]:
    """Return {post path: (thumbnail URL, kind)} for every post visible in the grid.

    kind comes from the small icon on the tile: 'carousel' (several images), 'video' (reels and
    videos) or 'photo' (a single image).
    """
    rows = page.eval_on_selector_all("a[href]", """els => els.map(e => [
        e.getAttribute('href'),
        (e.querySelector('img') || {}).src || '',
        [...e.querySelectorAll('svg[aria-label]')].map(s => s.getAttribute('aria-label')).join('|')])""")
    out: dict[str, tuple[str, str]] = {}
    for href, src, labels in rows:
        path = (href or "").split("?")[0]
        if POST_PATH.match(path):
            kind = ("carousel" if re.search(r"carousel", labels, re.I)
                    else "video" if re.search(r"clip|video|reel", labels, re.I) or is_video_path(path)
                    else "photo")
            out[path] = (src or (out[path][0] if path in out else ""), kind)
    return out


_network_calls = 0  # number of Instagram scrapes so far this run
KNOWN_STOP = 15  # incremental mode: stop after seeing this many already-cached posts


def gather_posts(page, total: int | None, max_scrolls: int,
                 known: set[str] | None = None) -> tuple[set[str], dict[str, str], dict[str, str]]:
    """Scroll until we've seen `total` posts, or progress stalls, or max_scrolls is hit.

    With `known` (incremental mode) we stop as soon as we've scrolled past the new
    posts: the grid is newest-first, so once KNOWN_STOP cached posts are on screen
    (more than the 3 pinned posts that can sit at the top), nothing newer is left.
    """
    links: set[str] = set()
    thumbs: dict[str, str] = {}
    kinds: dict[str, str] = {}
    stalls = 0
    for i in range(max_scrolls):
        before = len(links)
        seen = collect_links(page)
        links |= seen.keys()
        for path, (src, kind) in seen.items():
            if src or path not in thumbs:
                thumbs[path] = src
            kinds[path] = kind
        if known and len(links & known) >= min(KNOWN_STOP, len(known)):
            break
        if not known and total and len(links) >= total:
            break
        # Stop after several scrolls with no new posts (end of grid / throttled).
        stalls = stalls + 1 if len(links) == before and i > 0 else 0
        if stalls >= 6:
            break
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(random.randint(900, 1600))  # let lazy loading finish; human-ish pacing
        if i and i % 10 == 0:
            print(f"  ...{len(links)} posts loaded" + (f" / {total}" if total else ""))
    return links, thumbs, kinds


def load_cache(username: str, max_age_hours: float, announce: bool = True) -> list[str] | None:
    """Return cached post paths if the cache exists, is readable and is fresh enough."""
    try:
        data = json.loads(cache_path(username).read_text())
        age_h = (time.time() - data["fetched_at"]) / 3600
        if age_h <= max_age_hours and data["links"]:
            if announce:
                print(f"Using cache: {len(data['links'])} posts, {age_h:.1f}h old "
                      f"(--refresh fetches new posts only, --full rescrapes everything).")
            return data["links"]
    except (OSError, ValueError, KeyError, TypeError):
        pass  # missing/corrupt cache: fall back to the photo index, else rescrape
    have = load_embeddings(username)
    if have and max_age_hours == float("inf"):         # an index lists every post it covers
        posts = [p for p in have[0] if not is_slide(p)]
        if posts:
            if announce:
                print(f"Using the photo index as the post list ({len(posts)} posts).")
            return posts
    return None


def save_cache(username: str, links: set[str]) -> None:
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        cache_path(username).write_text(
            json.dumps({"fetched_at": time.time(), "links": sorted(links)}))
    except OSError as e:
        print(f"Warning: couldn't write cache ({e}).")


def kinds_path(username: str) -> Path:
    return CACHE_DIR / f"{username.lower()}.kinds.json"


def load_kinds(username: str) -> dict[str, str]:
    """{post path: 'carousel' | 'video' | 'photo'}; empty if we haven't recorded them yet."""
    try:
        return json.loads(kinds_path(username).read_text())["kinds"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def record_kinds(username: str, kinds: dict[str, str]) -> None:
    """Merge what this scrape saw into the stored post types, and say what was found."""
    counts = {k: sum(1 for v in kinds.values() if v == k) for k in ("carousel", "video", "photo")}
    print(f"Post types seen: {counts['carousel']} carousels, {counts['video']} reels/videos, "
          f"{counts['photo']} single photos.")
    if kinds and counts["carousel"] == 0 and counts["video"] == 0 and len(kinds) > 50:
        print("Warning: no carousel or video icons were found at all; Instagram's layout may have "
              "changed, so the post types may be wrong.")
    merged = {**load_kinds(username), **kinds}
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        kinds_path(username).write_text(json.dumps({"updated": time.time(), "kinds": merged}))
    except OSError as e:
        print(f"Warning: couldn't write post types ({e}).")


def fetch_links(username: str, max_scrolls: int,
                known: set[str] | None = None) -> tuple[list[str], dict[str, str]]:
    """Scrape the profile with a headless browser (slow path).

    Returns (all post paths, {path: thumbnail URL} for the posts seen this session).
    If `known` (the cached posts) is given, only the new posts are fetched and
    merged into it.
    """
    global _network_calls
    if not AUTH_FILE.exists():
        raise ScrapeError(f"{AUTH_FILE.name} not found. Run `python login.py` first.")
    _network_calls += 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            try:
                context = browser.new_context(storage_state=str(AUTH_FILE),
                                              viewport={"width": 1280, "height": 900})
            except PlaywrightError as e:
                raise ScrapeError(f"{AUTH_FILE.name} is unreadable/corrupt ({e}). Re-run login.py.")
            page = context.new_page()
            try:
                page.goto(f"{BASE}/{username}/", wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(3000)  # let the SPA render the header + grid
            except PlaywrightTimeout:
                raise ScrapeError("Timed out loading the profile. Check your connection.")

            check_page_state(page, username)

            total = read_post_count(page)
            print(f"Profile reports {total} posts." if total is not None
                  else "Couldn't read post count; will scroll until the grid stops growing.")
            if total == 0:
                raise ScrapeError(f"'{username}' has no posts.")

            links, thumbs, kinds = gather_posts(page, total, max_scrolls, known)
            record_kinds(username, kinds)
            if not links:
                raise ScrapeError("No post links found (account may be restricted or the layout changed).")
            if known:
                new = links - known
                merged = known | links
                print(f"Found {len(new)} new post(s); cache now has {len(merged)}.")
                if total and len(merged) != total:
                    print(f"Note: profile reports {total} posts. Posts may have been deleted "
                          f"or missed; use --full for an exact rescrape.")
                save_cache(username, merged)
                return sorted(merged), thumbs
            if total and len(links) < total:
                print(f"Warning: loaded {len(links)} of {total} posts; selection is from this partial pool.")
            else:
                save_cache(username, links)  # only cache complete pools
            return sorted(links), thumbs
        finally:
            browser.close()


# --- Photo search (--find): free, local CLIP model ---------------------------------
# CLIP maps images and text into the same vector space, so a text query like
# "a dog on a beach" can be compared against every thumbnail by cosine similarity.
# Thumbnail vectors are computed once and stored in cache/<username>.clip.npz.

# Two photo-search models are supported. Each keeps its own index file per account, so switching
# never overwrites the other: cache/<account>.siglip.npz and cache/<account>.clip.npz.
MODELS = {
    "siglip": {"name": "google/siglip-base-patch16-224", "file": "siglip", "size": "~800 MB"},
    "clip": {"name": "openai/clip-vit-base-patch32", "file": "clip", "size": "~600 MB"},
}
ACTIVE_MODEL = os.environ.get("RPP_MODEL", "siglip")      # change with --model or the page's setting
if ACTIVE_MODEL not in MODELS:
    ACTIVE_MODEL = "siglip"
_models: dict = {}        # loaded models: key -> (model, processor, device)


def set_model(key: str) -> None:
    global ACTIVE_MODEL
    ACTIVE_MODEL = key if key in MODELS else "siglip"


def index_file(username: str, key: str | None = None) -> Path:
    return CACHE_DIR / f"{username.lower()}.{MODELS[key or ACTIVE_MODEL]['file']}.npz"


def embed_path(username: str) -> Path:
    return index_file(username)


def load_clip():
    """Load the active photo-search model once. Returns (model, processor, device)."""
    key = ACTIVE_MODEL
    if key not in _models:
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
        except ImportError:
            raise ScrapeError("--find needs extra packages: "
                              "python3 -m pip install torch transformers pillow numpy sentencepiece")
        info = MODELS[key]
        print(f"Loading the {key} model (first time downloads {info['size']})...")
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        model = AutoModel.from_pretrained(info["name"]).to(device).eval()
        _models[key] = (model, AutoProcessor.from_pretrained(info["name"]), device)
    return _models[key]


def image_features(imgs):
    """Unit-length vectors (N x D numpy array) for a list of PIL images, with the active model."""
    import torch
    model, processor, device = load_clip()
    inputs = processor(images=[i.convert("RGB") for i in imgs], return_tensors="pt").to(device)
    with torch.no_grad():
        f = torch.nn.functional.normalize(model.get_image_features(**inputs), dim=-1)
    return f.cpu().numpy()


def logit_scale() -> float:
    """The model's own temperature for turning similarities into label probabilities."""
    model = load_clip()[0]
    try:
        return float(model.logit_scale.exp().item())
    except AttributeError:
        return 100.0


def load_embeddings(username: str):
    """Return (paths list, vectors matrix) or None if nothing usable is stored."""
    try:
        import numpy as np
        data = np.load(embed_path(username), allow_pickle=False)
        return [str(p) for p in data["paths"]], data["vecs"]
    except (OSError, ValueError, KeyError, ImportError):
        return None


def save_embeddings(username: str, paths: list[str], vecs) -> None:
    import numpy as np
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        np.savez(embed_path(username), paths=np.array(paths), vecs=vecs)
    except OSError as e:
        print(f"Warning: couldn't write embeddings ({e}).")


# --- Pose search (--pose): MediaPipe body landmarks ----------------------------------
# A pose is described by the directions of 12 body segments (upper arms, forearms, torso,
# shoulder line, hip line, thighs, shins, neck). Directions are unit vectors, so the result
# doesn't depend on how big the person is or where she is in the frame, but it does tell
# standing from lying down. Poses are compared by the average cosine of matching segments.

SAVED_MAX = 1350          # longest side of images we keep (Instagram's own 1080 x 1350)
SAVED_QUALITY = 82        # JPEG quality of those copies
THUMB_DIR = CACHE_DIR / "thumbs"          # thumbnails are kept so new analyses never need a rescrape
VIS_MIN = 0.5                             # landmark visibility needed to trust a segment
MIN_SHARED = 4                            # segments two poses must share to be comparable
# (start landmarks, end landmarks, weight); several landmarks = their midpoint
POSE_SEGMENTS = [
    ((11,), (13,), 1.0), ((12,), (14,), 1.0),            # upper arms
    ((13,), (15,), 1.0), ((14,), (16,), 1.0),            # forearms
    ((11, 12), (23, 24), 2.0),                           # torso
    ((11,), (12,), 1.0), ((23,), (24,), 1.0),            # shoulder line, hip line
    ((23,), (25,), 1.5), ((24,), (26,), 1.5),            # thighs
    ((25,), (27,), 1.0), ((26,), (28,), 1.0),            # shins
    ((11, 12), (0,), 1.0),                               # neck / head direction
]
SEG_W = None                              # numpy array of the weights (set on first use)
_MIRROR = list(range(33))
for _l, _r in [(1, 4), (2, 5), (3, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18),
               (19, 20), (21, 22), (23, 24), (25, 26), (27, 28), (29, 30), (31, 32)]:
    _MIRROR[_l], _MIRROR[_r] = _r, _l
_pose_model = None


def pose_path(username: str) -> Path:
    return CACHE_DIR / f"{username.lower()}.pose.npz"


def thumb_file(username: str, path: str) -> Path:
    """Where a post's image lives on disk. Carousel slides use keys like /p/CODE/@3."""
    m = re.search(r"/(?:p|reel|reels)/([\w-]+)", path)
    code = m.group(1) if m else path.strip("/").split("/")[-1]
    slide = re.search(r"/@(\d+)$", path)
    return THUMB_DIR / username.lower() / f"{code}{'@' + slide.group(1) if slide else ''}.jpg"


def get_pose_model():
    global _pose_model
    if _pose_model is None:
        try:
            import mediapipe as mp
            model = mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1)
        except (ImportError, AttributeError):
            raise ScrapeError("Pose search needs MediaPipe 0.10: python3 -m pip install mediapipe==0.10.14")
        _pose_model = model
    return _pose_model


def segment_directions(pts, vis, mirror: bool = False):
    """(S x 2 unit vectors, S visibility flags) for 33 landmark points given in pixels."""
    import numpy as np
    global SEG_W
    if SEG_W is None:
        SEG_W = np.array([w for _, _, w in POSE_SEGMENTS], dtype="float32")
    if mirror:                                          # swap left/right and flip x
        pts, vis = pts[_MIRROR] * np.array([-1.0, 1.0], dtype="float32"), vis[_MIRROR]
    segs = np.zeros((len(POSE_SEGMENTS), 2), dtype="float32")
    ok = np.zeros(len(POSE_SEGMENTS), dtype="float32")
    for i, (a, b, _) in enumerate(POSE_SEGMENTS):
        if min(vis[list(a)].min(), vis[list(b)].min()) < VIS_MIN:
            continue
        d = pts[list(b)].mean(axis=0) - pts[list(a)].mean(axis=0)
        n = float(np.hypot(*d))
        if n < 2.0:                                     # (almost) zero length: direction is noise
            continue
        segs[i], ok[i] = d / n, 1.0
    return segs, ok


def pose_landmarks(img):
    """(points in pixels, visibilities) for the main person, or None if no body is found."""
    import numpy as np
    arr = np.ascontiguousarray(np.array(img.convert("RGB")))
    res = get_pose_model().process(arr)
    if not res.pose_landmarks:
        return None
    h, w = arr.shape[:2]
    lm = res.pose_landmarks.landmark
    return (np.array([[l.x * w, l.y * h] for l in lm], dtype="float32"),
            np.array([l.visibility for l in lm], dtype="float32"))


def pose_features(img):
    """Segment directions for an image; all-zero if no person was detected."""
    import numpy as np
    found = pose_landmarks(img)
    if found is None:
        return np.zeros((len(POSE_SEGMENTS), 2), dtype="float32"), np.zeros(len(POSE_SEGMENTS), dtype="float32")
    return segment_directions(*found)


def pose_similarity(refs, segs, vis):
    """Score every row of (segs, vis) against the reference(s). Range -1..1, higher = closer.

    Averages the cosine of the segments both poses show, weighted by importance, then scales
    by the square root of how much of the reference pose is covered (a pose seen through only
    two segments can't score as high as one that matches on all of them).
    """
    import numpy as np
    best = None
    for rs, rv in refs:
        both = (vis > 0) & (rv[None, :] > 0)
        w = both * SEG_W[None, :]
        wsum = w.sum(axis=1)
        cos = (segs * rs[None]).sum(axis=-1)
        mean_cos = (w * cos).sum(axis=1) / np.maximum(wsum, 1e-9)
        coverage = wsum / max(float((SEG_W * (rv > 0)).sum()), 1e-9)
        sc = np.where(both.sum(axis=1) >= MIN_SHARED, mean_cos * np.sqrt(coverage), -1.0)
        best = sc if best is None else np.maximum(best, sc)
    return best


def load_pose(username: str):
    """Return (paths, segs, vis) or None."""
    try:
        import numpy as np
        d = np.load(pose_path(username), allow_pickle=False)
        return [str(p) for p in d["paths"]], d["segs"], d["vis"]
    except (OSError, ValueError, KeyError, ImportError):
        return None


def save_pose(username: str, paths, segs, vis) -> None:
    import numpy as np
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        np.savez(pose_path(username), paths=np.array(paths), segs=segs, vis=vis)
    except OSError as e:
        print(f"Warning: couldn't write pose index ({e}).")


def merge_pose(old, new):
    """Combine two (paths, segs, vis) triples; entries in `new` win."""
    import numpy as np
    if old is None:
        return new
    paths = old[0] + new[0]
    segs, vis = np.concatenate([old[1], new[1]]), np.concatenate([old[2], new[2]])
    last = {p: i for i, p in enumerate(paths)}
    keep = sorted(last.values())
    return [paths[i] for i in keep], segs[keep], vis[keep]


def download_image(url: str):
    """Fetch one thumbnail (CDN URLs are signed, so no login needed). None on failure."""
    from PIL import Image
    import io
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return Image.open(io.BytesIO(resp.read())).convert("RGB")
    except Exception:
        return None


def get_thumb(username: str, path: str, url: str):
    """Thumbnail from disk if we have it, otherwise download it and keep a copy."""
    from PIL import Image
    f = thumb_file(username, path)
    if f.exists():
        try:
            return Image.open(f).convert("RGB")
        except OSError:
            pass
    img = download_image(url) if url else None
    if img is not None:
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            small = img.copy()
            small.thumbnail((SAVED_MAX, SAVED_MAX))
            small.save(f, "JPEG", quality=SAVED_QUALITY)
        except OSError:
            pass
    return img


def index_thumbs(username: str, thumbs: dict[str, str], do_clip: bool, do_pose: bool):
    """Download (or load from disk) thumbnails and compute CLIP vectors and/or poses.

    Returns ((clip paths, clip vectors) or None, (pose paths, segs, vis) or None).
    Works through the thumbnails in chunks so memory stays small.
    """
    import numpy as np
    import torch
    from concurrent.futures import ThreadPoolExecutor

    items = [(p, u) for p, u in thumbs.items() if u or thumb_file(username, p).exists()]
    if do_clip:
        load_clip()
    if do_pose:
        get_pose_model()
    clip_paths, clip_chunks = [], []
    pose_paths, pose_segs, pose_vis = [], [], []
    print(f"Processing {len(items)} thumbnails "
          f"({'photo vectors' if do_clip else ''}{' + ' if do_clip and do_pose else ''}"
          f"{'poses' if do_pose else ''}; one-off, later searches are instant)...")
    failed = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for start in range(0, len(items), 64):
            chunk = items[start:start + 64]
            imgs = list(pool.map(lambda pu: get_thumb(username, pu[0], pu[1]), chunk))
            ok = [(p, img) for (p, _), img in zip(chunk, imgs) if img is not None]
            failed += len(chunk) - len(ok)
            if do_clip and ok:
                for i in range(0, len(ok), 32):
                    batch = ok[i:i + 32]
                    clip_chunks.append(image_features([img for _, img in batch]))
                    clip_paths += [p for p, _ in batch]
            if do_pose:
                for p, img in ok:
                    sg, vs = pose_features(img)
                    pose_paths.append(p); pose_segs.append(sg); pose_vis.append(vs)
            done = start + len(chunk)
            if (start // 64) % 4 == 3 or done == len(items):
                print(f"  ...{done} / {len(items)}")
    if failed:
        print(f"  {failed} thumbnails failed to download and were skipped.")
    clip = (clip_paths, np.concatenate(clip_chunks)) if clip_chunks else None
    pose = (pose_paths, np.stack(pose_segs), np.stack(pose_vis)) if pose_paths else None
    return clip, pose


def embed_image(img):
    """Unit-length vector for a PIL image, with the active model."""
    return image_features([img])[0]


def embed_text(text: str):
    """Unit-length vector for a text description, with the active model."""
    import torch
    model, processor, device = load_clip()
    if ACTIVE_MODEL == "siglip":                       # SigLIP expects lower-case, padded to 64 tokens
        inputs = processor(text=[text.lower()], return_tensors="pt", padding="max_length", max_length=64)
    else:
        inputs = processor(text=[text], return_tensors="pt", padding=True)
    with torch.no_grad():
        f = torch.nn.functional.normalize(model.get_text_features(**inputs.to(device)), dim=-1)
    return f.cpu().numpy()[0]


def fetch_post_photo(url: str):
    """Download the main photo of an Instagram post URL (needs the saved login)."""
    from PIL import Image
    import io
    if not AUTH_FILE.exists():
        raise ScrapeError(f"{AUTH_FILE.name} not found. Run `python login.py` first.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=str(AUTH_FILE),
                                          viewport={"width": 1280, "height": 1000})
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_selector("article img, article video, main img", timeout=10_000)
            except PlaywrightTimeout:
                pass
            page.wait_for_timeout(1500)
            if "/accounts/login" in page.url:
                raise ScrapeError("Session expired. Re-run `python login.py`.")
            if page.evaluate(_IS_VIDEO_JS):
                raise ScrapeError("The reference post is a video; use a photo post.")
            got = fetch_image(context, page.evaluate(_MAIN_IMG_JS))
            if not got:
                raise ScrapeError("Couldn't get the photo from the reference post.")
            return Image.open(io.BytesIO(got[0]))
        finally:
            browser.close()


def load_reference(spec: str):
    """Load the --like reference: a local file, an image URL, or an Instagram post URL."""
    from PIL import Image
    try:
        if re.match(r"https?://", spec):
            if "instagram.com/" in spec and re.search(r"/(?:p|reel|reels)/", spec):
                return fetch_post_photo(spec)
            img = download_image(spec)
            if img is None:
                raise ScrapeError(f"Couldn't download the reference image from {spec}")
            return img
        return Image.open(Path(spec).expanduser())
    except (OSError, ValueError) as e:
        raise ScrapeError(f"Couldn't open the reference image '{spec}': {e}")


class Query:
    """What to search for: a text description, a reference image (--like), or a blend of both.

    Everything is turned into one CLIP vector; posts are ranked by similarity to it.
    With both, `weight` is how much the image counts (0 = text only, 1 = image only).
    """

    def __init__(self, text: str | None = None, like: str | None = None, weight: float = 0.5,
                 pose: str | None = None, mirror: bool = True, scene_top: float = 0.3):
        self.text, self.like, self.weight = (text or "").strip() or None, like, weight
        self.pose_ref, self.mirror, self.scene_top = pose, mirror, scene_top
        self._vec = None
        self._pose_refs = None

    @property
    def has_scene(self) -> bool:
        return bool(self.text or self.like)

    def __str__(self) -> str:
        return " + ".join(x for x in (
            f"pose of '{Path(self.pose_ref).name}'" + (" (mirror ok)" if self.mirror else "")
            if self.pose_ref else None,
            f"image '{Path(self.like).name}'" if self.like else None,
            f"'{self.text}'" if self.text else None) if x)

    def pose_refs(self):
        """[(segments, visibility)] for the reference pose (plus its mirror image)."""
        if self._pose_refs is None:
            found = pose_landmarks(load_reference(self.pose_ref))
            if found is None:
                raise ScrapeError("No person found in the pose reference image.")
            refs = [segment_directions(*found)]
            if self.mirror:
                refs.append(segment_directions(*found, mirror=True))
            if refs[0][1].sum() < MIN_SHARED:
                raise ScrapeError("Too little of the body is visible in the pose reference.")
            self._pose_refs = refs
        return self._pose_refs

    def prepare(self) -> None:
        """Load everything up front so mistakes show before any scraping starts."""
        if self.has_scene:
            self.vec()
        if self.pose_ref:
            self.pose_refs()

    def vec(self):
        if self._vec is None:
            import numpy as np
            parts = []
            if self.like:
                parts.append((self.weight if self.text else 1.0, embed_image(load_reference(self.like))))
            if self.text:
                parts.append(((1 - self.weight) if self.like else 1.0, embed_text(self.text)))
            v = sum(w * x for w, x in parts)
            self._vec = v / np.linalg.norm(v)
        return self._vec


def rank_by_vec(qvec, paths: list[str], vecs) -> list[tuple[float, str]]:
    """Return [(similarity, path)] sorted best-first."""
    scores = vecs @ qvec
    return sorted(zip(scores.tolist(), paths), reverse=True)


# --- Categories / tags (--tag, --list-tags) -------------------------------------------
# Scene, outfit and shot-type tags come from zero-shot CLIP: each label in labels.json has a
# description, and a post gets the label whose description its photo matches best, if the match
# is confident enough. Pose tags come from simple geometry rules on the pose index.

LABELS_FILE = Path(__file__).with_name("labels.json")
# (tag odds use the active model's own temperature: see logit_scale())
POSE_CLASSES = ["standing", "sitting", "kneeling", "lying down", "on all fours",
                "bending over", "leaning", "upper body only"]


def load_labels() -> dict[str, dict[str, str]]:
    """{facet: {label: description}} from labels.json."""
    try:
        data = json.loads(LABELS_FILE.read_text())
        return {f: dict(labels) for f, labels in data.items()}
    except (OSError, ValueError, TypeError) as e:
        raise ScrapeError(f"Couldn't read {LABELS_FILE.name}: {e}")


def known_tags() -> dict[str, list[str]]:
    """Every facet and its labels, including the built-in pose facets."""
    tags = {f: list(labels) for f, labels in load_labels().items()}
    tags["pose"] = POSE_CLASSES
    tags["arms"] = ["arms up"]
    return tags


def parse_tags(specs: list[str] | None) -> list[tuple[str, str]]:
    """Turn 'beach' or 'setting:beach' into (facet, label); errors on unknown/ambiguous tags."""
    out = []
    table = known_tags()
    for spec in specs or []:
        facet_hint, _, name = spec.rpartition(":")
        name = name.strip().lower()
        hits = [(f, l) for f, labels in table.items() for l in labels
                if l.lower() == name and (not facet_hint or f == facet_hint.strip().lower())]
        if not hits:
            raise ScrapeError(f"Unknown tag '{spec}'. Run with --list-tags to see the tags, "
                              f"or add it to {LABELS_FILE.name}.")
        if len(hits) > 1:
            raise ScrapeError(f"Tag '{spec}' is ambiguous ({', '.join(f'{f}:{l}' for f, l in hits)}); "
                              f"write it as facet:label.")
        out.append(hits[0])
    return out


def pose_class(segs, vis):
    """Coarse pose label from segment directions (image y points down), or None if unclear.

    Directions only, so these are rough 2D rules: they mostly work for standing / sitting /
    lying, and are less reliable for kneeling and on-all-fours from unusual angles.
    """
    import numpy as np

    def avg(idx):
        vs = [segs[i] for i in idx if vis[i] > 0]
        return np.mean(vs, axis=0) if vs else None

    if vis[4] == 0:
        return None
    tx, ty = segs[4]                                    # torso: shoulders -> hips
    thigh, shin, uarm = avg([7, 8]), avg([9, 10]), avg([0, 1])
    if ty < -0.5:
        return None                                     # upside down / sideways crop
    if thigh is None:
        return "upper body only"
    if abs(tx) >= 0.7:                                  # torso is roughly horizontal
        if abs(thigh[0]) >= 0.6:
            return "lying down"
        if uarm is not None and uarm[1] >= 0.6 and thigh[1] >= 0.5:
            return "on all fours"
        return "bending over"
    if abs(tx) >= 0.4:                                  # leaning 25-45 degrees or more
        return "bending over" if (uarm is not None and uarm[1] >= 0.5) else "leaning"
    if thigh[1] >= 0.75:                                # upright, thighs pointing down
        return "kneeling" if (shin is not None and abs(shin[1]) <= 0.5) else "standing"
    return "sitting" if abs(thigh[1]) <= 0.55 else "standing"


def arms_up(segs, vis) -> bool:
    ups = [segs[i][1] for i in (0, 1, 2, 3) if vis[i] > 0]
    return bool(ups) and min(ups) <= -0.5 and sum(u <= -0.5 for u in ups) >= 2


def compute_tags(paths, vecs, pose, min_conf: float):
    """{path: {facet: (label, confidence)}} for every post."""
    import numpy as np
    tags = {p: {} for p in paths}
    for facet, labels in load_labels().items():
        names = list(labels)
        T = np.stack([embed_text(labels[n]) for n in names])
        logits = logit_scale() * (vecs @ T.T)
        logits -= logits.max(axis=1, keepdims=True)
        probs = np.exp(logits)
        probs /= probs.sum(axis=1, keepdims=True)
        best = probs.argmax(axis=1)
        for i, p in enumerate(paths):
            conf = float(probs[i, best[i]])
            if conf >= min_conf:
                tags[p][facet] = (names[best[i]], conf)
    if pose:
        ppaths, psegs, pvis = pose
        for p, sg, vs in zip(ppaths, psegs, pvis):
            if p not in tags:
                continue
            cls = pose_class(sg, vs)
            if cls:
                tags[p]["pose"] = (cls, 1.0)
            if arms_up(sg, vs):
                tags[p]["arms"] = ("arms up", 1.0)
    return tags


def tagged_posts(specs, paths, vecs, pose, min_conf: float) -> dict[str, float]:
    """{path: weakest confidence} for posts that carry ALL the requested tags."""
    tags = compute_tags(paths, vecs, pose, min_conf)
    out = {}
    for p, t in tags.items():
        confs = []
        for facet, label in specs:
            got = t.get(facet)
            if not got or got[0] != label:
                break
            confs.append(got[1])
        else:
            out[p] = min(confs) if confs else 1.0
    return out


def specs_need_pose(specs) -> bool:
    return any(f in ("pose", "arms") for f, _ in specs)


def tag_counts(username: str, min_conf: float, max_scrolls: int) -> dict:
    """How many photo posts carry each tag. Reels are left out (they're never picked by default)."""
    pose = load_pose(username)
    paths, vecs, pose = ensure_indexes(username, pose is not None, max_scrolls, False, False)
    keep = [i for i, p in enumerate(paths) if not is_video_path(p)]
    photos = [paths[i] for i in keep]
    n_slides = sum(1 for p in photos if is_slide(p))
    kinds = load_kinds(username)
    tags = compute_tags(photos, vecs[keep], pose, min_conf)
    facets = {}
    for facet, labels in known_tags().items():
        if facet in ("pose", "arms") and not pose:
            continue
        counts = {l: sum(1 for t in tags.values() if t.get(facet, ("",))[0] == l) for l in labels}
        facets[facet] = {"counts": counts,
                         "untagged": None if facet == "arms" else sum(1 for t in tags.values() if facet not in t)}
    items = {p: {f: [t[f][0], round(t[f][1], 2)] for f in t} for p, t in tags.items()}
    return {"account": username, "items": items,
            "photos": len(photos) - n_slides, "slides": n_slides,
            "carousels": (sum(1 for p in photos if kinds.get(p) == "carousel") if kinds else None),
            "expanded": len(load_expanded(username)), "reels": len(paths) - len(photos),
            "pose_ready": bool(pose), "min_conf": min_conf, "facets": facets}


def list_tags(username: str, min_conf: float, max_scrolls: int, as_json: bool = False) -> None:
    """Print how many posts carry each tag (a quick tour of the account)."""
    info = tag_counts(username, min_conf, max_scrolls)
    if as_json:
        print("@@JSON@@" + json.dumps(info))
        return
    print(f"\n{username}: {info['photos']} photo posts + {info['reels']} reels"
          + (f"; {info['carousels']} of the photo posts are carousels ({info['expanded']} looked inside, "
             f"{info['slides']} extra slide images indexed)" if info["carousels"] is not None
             else "; carousels not detected yet (run --detect-carousels)")
          + f"\n(counts below cover photos only, tags at confidence >= {min_conf:.0%})")
    for facet in known_tags():
        if facet not in info["facets"]:
            print(f"\n{facet}: no pose index yet (build it with --build-pose, or the first --pose / pose tag)")
            continue
        data = info["facets"][facet]
        print(f"\n{facet}:")
        for l, n in sorted(data["counts"].items(), key=lambda kv: -kv[1]):
            print(f"  {n:5d}  {l}")
        if data["untagged"] is not None:
            print(f"  {data['untagged']:5d}  (no confident tag)")


# --- Looking inside carousels (--expand-carousels) -------------------------------------
# The main index holds only each post's FIRST image. For the carousels that look promising
# (their first image ranks well for your search), we open the post, save every photo slide,
# analyse them and add them to the indexes under keys like /p/CODE/@3 (slide 3). From then on
# those slides compete in searches like any other image, and are never fetched again.

def is_slide(path: str) -> bool:
    return bool(re.search(r"/@\d+$", path))


def base_post(path: str) -> str:
    return re.sub(r"/@\d+$", "/", path)          # /p/CODE/@3 -> /p/CODE/


def slide_no(path: str) -> int:
    m = re.search(r"/@(\d+)$", path)
    return int(m.group(1)) if m else 1


def fmt_date(iso: str | None) -> str:
    d = (iso or "")[:10]                                  # YYYY-MM-DD -> DD-MM-YYYY
    return "-".join(reversed(d.split("-"))) if len(d) == 10 else "unknown-date"


def expanded_path(username: str) -> Path:
    return CACHE_DIR / f"{username.lower()}.expanded.json"


def worker_notes_files(username: str) -> list:
    return sorted(CACHE_DIR.glob(f"{username.lower()}.expanded.w*.json"))


def load_expanded(username: str) -> dict:
    """{post path: {'date': ISO date, 'slides': n}} for carousels already looked inside.

    Includes the notes of parallel workers that haven't been consolidated yet.
    """
    merged: dict = {}
    for f in [expanded_path(username), *worker_notes_files(username)]:
        try:
            merged.update(json.loads(f.read_text())["posts"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return merged


def save_expanded(username: str, posts: dict, worker: int | None = None) -> None:
    """Save carousel notes. Parallel workers each write their own file so they never collide."""
    path = expanded_path(username) if worker is None else \
        CACHE_DIR / f"{username.lower()}.expanded.w{worker}.json"
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        path.write_text(json.dumps({"posts": posts}))
    except OSError as e:
        print(f"Warning: couldn't write carousel notes ({e}).")


def consolidate_expanded(username: str) -> None:
    """Fold the workers' notes into the main notes file (only call when no worker is running)."""
    files = worker_notes_files(username)
    if not files:
        return
    save_expanded(username, load_expanded(username))
    for f in files:
        f.unlink(missing_ok=True)


def merge_clip(old, new):
    """Combine two (paths, vectors) pairs; entries in `new` win."""
    import numpy as np
    if old is None:
        return new
    paths = old[0] + new[0]
    vecs = np.concatenate([old[1], new[1]])
    keep = sorted({p: i for i, p in enumerate(paths)}.values())
    return [paths[i] for i in keep], vecs[keep]


def carousel_candidates(username: str, ordered_paths: list[str], n: int) -> list[str]:
    """The first n posts (in the given order) still to be opened to look for more photos.

    A post qualifies if it is a carousel, or if we don't know its type yet (opening it settles
    that). Single photos, videos and reels are skipped, as are posts already looked inside.
    """
    kinds = load_kinds(username)
    done = load_expanded(username)
    return [p for p in ordered_paths
            if not is_slide(p) and not is_video_path(p) and kinds.get(p, "carousel") == "carousel"
            and p not in done][:n]


# JSON blobs the page embeds in its HTML (they hold the post's data, including every carousel photo).
_PAGE_JSON_JS = """() => [...document.querySelectorAll('script[type="application/json"]')]
    .map(s => s.textContent).filter(t => t && t.length > 500)"""


def parse_slide_urls(texts: list[str], shortcode: str):
    """Read a carousel's photo links out of the page's embedded JSON.

    Returns ([(slide number, photo URL)], ISO date or '') or None if this post's data isn't there.
    Videos are left out (their numbers are skipped). Understands the current format
    (`carousel_media`) and the older one (`edge_sidecar_to_children`).
    """
    def walk(node):
        if isinstance(node, dict):
            yield node
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    def iso(ts):
        try:
            return time.strftime("%Y-%m-%d", time.gmtime(int(ts)))
        except (TypeError, ValueError, OverflowError):
            return ""

    for text in texts:
        if shortcode not in text or not ("carousel_media" in text or "edge_sidecar_to_children" in text):
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        for d in walk(data):
            media = d.get("carousel_media")
            if d.get("code") == shortcode and isinstance(media, list) and media:
                out = []
                for i, m in enumerate(media, 1):
                    cands = (m.get("image_versions2") or {}).get("candidates") or []
                    if m.get("media_type") == 2 or m.get("video_versions") or not cands:
                        continue
                    out.append((i, max(cands, key=lambda c: c.get("width", 0))["url"]))
                return out, iso(d.get("taken_at"))
            side = d.get("edge_sidecar_to_children")
            if d.get("shortcode") == shortcode and isinstance(side, dict) and side.get("edges"):
                out = []
                for i, e in enumerate(side["edges"], 1):
                    node = e.get("node", {})
                    if node.get("is_video") or not node.get("display_url"):
                        continue
                    res = node.get("display_resources") or []
                    best = max(res, key=lambda r: r.get("config_width", 0))["src"] if res else node["display_url"]
                    out.append((i, best))
                return out, iso(d.get("taken_at_timestamp"))
    return None


def download_bytes(url: str):
    """Fetch an image from the CDN (signed URLs: no login needed). None on failure."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.read()
    except Exception:
        return None


def save_slide_image(username: str, path: str, number: int, data: bytes) -> str:
    """Store one slide photo on disk (max 1800 px) and return its index key."""
    from PIL import Image
    import io
    key = f"{path.rstrip('/')}/@{number}"
    f = thumb_file(username, key)
    f.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((SAVED_MAX, SAVED_MAX))             # plenty for search; keeps disk use sane
    img.save(f, "JPEG", quality=SAVED_QUALITY)
    return key


def fetch_carousel_slides(username: str, targets: list[str], worker: int | None = None,
                          start_delay: float = 0.0) -> tuple[list[str], int]:
    """Open each post and save its photos (slide 2 and up) to disk.

    The fast route reads every slide's link from the data the page already holds, then downloads
    them side by side: no clicking. If that data isn't found, it falls back to clicking through
    the carousel. Returns (slide keys, number of posts that failed to load); failed posts aren't
    marked as done, so a later run retries them. Progress is saved after every post.
    """
    from concurrent.futures import ThreadPoolExecutor
    if not AUTH_FILE.exists():
        raise ScrapeError(f"{AUTH_FILE.name} not found. Run `python login.py` first.")
    time.sleep(start_delay)                           # stagger parallel workers
    notes = load_expanded(username)
    keys: list[str] = []
    failed = 0
    with sync_playwright() as p, ThreadPoolExecutor(max_workers=6) as pool:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=str(AUTH_FILE),
                                          viewport={"width": 1280, "height": 1000})
            page = context.new_page()
            for n, path in enumerate(targets, 1):
                tag = f"  [{'w' + str(worker) + ' ' if worker else ''}{n}/{len(targets)}] {path}"
                try:
                    code = re.search(r"/(?:p|reel|reels)/([\w-]+)", path).group(1)
                    page.goto(BASE + path, wait_until="domcontentloaded", timeout=30_000)
                    if "/accounts/login" in page.url:
                        raise ScrapeError("Session expired. Re-run `python login.py`.")

                    found = None
                    for attempt in range(2):                      # data is usually there at once
                        page.wait_for_timeout(700 if attempt == 0 else 2500)
                        found = parse_slide_urls(page.evaluate(_PAGE_JSON_JS), code)
                        if found is not None:
                            break
                    slides, date, method = [], "", ""
                    if found is not None:                         # fast route: links already in the page
                        urls, date = found
                        todo = [(num, u) for num, u in urls if num >= 2]
                        blobs = list(pool.map(lambda nu: download_bytes(nu[1]), todo))
                        slides = [(num, b) for (num, _), b in zip(todo, blobs) if b]
                        method = "page data"
                        if todo and not slides:                   # every download failed
                            failed += 1
                            print(f"{tag}: downloads failed, will retry later")
                            continue
                    else:                                         # fallback: click through the carousel
                        try:
                            page.wait_for_selector("article img, article video, main img", timeout=10_000)
                        except PlaywrightTimeout:
                            pass
                        page.wait_for_timeout(1000)
                        date = (page.evaluate(_POST_DATE_JS) or "")[:10]
                        if page.evaluate(_IS_VIDEO_JS):           # opens on a video: leave it alone
                            notes[path] = {"date": date, "slides": 1}
                            save_expanded(username, notes, worker)
                            print(f"{tag}: starts with a video, skipped")
                            continue
                        src = page.evaluate(_MAIN_IMG_JS)
                        if not src:                               # page didn't show a photo: retry later
                            failed += 1
                            print(f"{tag}: no photo found, will retry later")
                            continue
                        slides = [(num, data) for num, data, _, _ in
                                  collect_slides(page, context, src, None, None, 0.0)]
                        method = "clicked through"
                    if not date:
                        date = (page.evaluate(_POST_DATE_JS) or "")[:10]
                    for number, data in slides:
                        keys.append(save_slide_image(username, path, number, data))
                    notes[path] = {"date": date, "slides": 1 + len(slides)}
                    save_expanded(username, notes, worker)
                    print(f"{tag}: {1 + len(slides)} photo(s) [{method}]")
                except PlaywrightTimeout:
                    failed += 1
                    print(f"{tag}: page timed out, will retry later")
                page.wait_for_timeout(random.randint(500, 1200))
        finally:
            browser.close()
            save_expanded(username, notes, worker)
    return keys, failed


def add_slides_to_index(username: str, keys: list[str]) -> None:
    """Analyse saved slide images and add them to the photo (and pose) indexes."""
    old_pose = load_pose(username)
    clip, pose = index_thumbs(username, {k: "" for k in keys}, True, old_pose is not None)
    if clip:
        save_embeddings(username, *merge_clip(load_embeddings(username), clip))
    if pose:
        save_pose(username, *merge_pose(old_pose, pose))


def shrink_saved_images(min_age_seconds: int = 120) -> None:
    """Recompress the saved thumbnails and slides to SAVED_MAX / SAVED_QUALITY (one way).

    Only touches cache/thumbs. Files written in the last couple of minutes are skipped (a job
    may still be using them), and every file is replaced atomically, so stopping part-way is safe.
    """
    from PIL import Image
    files = sorted(THUMB_DIR.glob("*/*.jpg"))
    before = sum(f.stat().st_size for f in files)
    changed = skipped = 0
    for i, f in enumerate(files, 1):
        try:
            if time.time() - f.stat().st_mtime < min_age_seconds:
                skipped += 1
                continue
            with Image.open(f) as im:
                big = max(im.size) > SAVED_MAX
                old_size = f.stat().st_size
                if not big and old_size < 200_000:               # already small
                    continue
                img = im.convert("RGB")
            img.thumbnail((SAVED_MAX, SAVED_MAX))
            tmp = f.with_suffix(".tmp")
            img.save(tmp, "JPEG", quality=SAVED_QUALITY)
            if tmp.stat().st_size < old_size:
                os.replace(tmp, f)
                changed += 1
            else:
                tmp.unlink()
        except OSError:
            continue
        if i % 1000 == 0:
            print(f"  ...{i} / {len(files)}")
    after = sum(f.stat().st_size for f in THUMB_DIR.glob("*/*.jpg"))
    print(f"Shrunk {changed} image(s) ({skipped} skipped as still in use). "
          f"{before / 1e6:.0f} MB -> {after / 1e6:.0f} MB (saved {(before - after) / 1e6:.0f} MB).")


def index_orphan_slides(username: str) -> int:
    """Index slide photos that were saved to disk but never made it into the index.

    This happens if a job is stopped after a batch was fetched and before it was analysed.
    Returns how many were added.
    """
    have = load_embeddings(username)
    if have is None:
        return 0
    indexed = set(have[0])
    orphans = []
    for path, meta in load_expanded(username).items():
        for n in range(2, int(meta.get("slides", 1)) + 1):
            key = f"{path.rstrip('/')}/@{n}"
            if key not in indexed and thumb_file(username, key).exists():
                orphans.append(key)
    if orphans:
        print(f"Found {len(orphans)} saved slide photo(s) that were never indexed; indexing them now.")
        add_slides_to_index(username, orphans)
    return len(orphans)


def expand_carousels(username: str, targets: list[str], batch: int = 25, workers: int = 1) -> int:
    """Look inside the given posts and index their photos. Returns how many slide images were added.

    Works in batches, with a short break between them. While one batch is being analysed (photo
    vectors and poses), the browser already starts on the next. Progress is saved after every
    post, so stopping at any point loses almost nothing and the next run carries on. Stops early
    if many pages fail to load (a sign Instagram is slowing us down).

    With workers > 1, each batch is split over that many separate browser windows (same login)
    working side by side. Faster, but Instagram sees proportionally more activity.
    """
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
    from multiprocessing import get_context
    workers = max(1, min(workers, 3))
    consolidate_expanded(username)
    index_orphan_slides(username)
    started, added, total = time.time(), 0, len(targets)
    print(f"Looking inside {total} post(s) for more photos"
          + (f", {workers} browser windows at once" if workers > 1 else "") + "...")

    def run_batch(chunk):
        if workers == 1:
            return fetch_carousel_slides(username, chunk)
        parts = [chunk[k::workers] for k in range(workers) if chunk[k::workers]]
        with ProcessPoolExecutor(max_workers=len(parts), mp_context=get_context("spawn")) as ex:
            futures = [ex.submit(fetch_carousel_slides, username, part, k + 1, k * 2.5)
                       for k, part in enumerate(parts)]
            results = [f.result() for f in futures]
        consolidate_expanded(username)
        return [k for r in results for k in r[0]], sum(r[1] for r in results)

    pending = None                                    # the analysis of the previous batch, if running
    with ThreadPoolExecutor(max_workers=1) as analyser:
        for i in range(0, total, batch):
            chunk = targets[i:i + batch]
            keys, failed = run_batch(chunk)
            if pending is not None:
                pending.result()                      # never two analyses writing the indexes at once
            if keys:
                pending = analyser.submit(add_slides_to_index, username, keys)
                added += len(keys)
            else:
                pending = None
            done = i + len(chunk)
            per = (time.time() - started) / done
            print(f"Progress: {done} / {total} posts opened, {added} extra photos indexed so far "
                  f"(~{int(per * (total - done) / 60)} min left).")
            if failed >= max(3, len(chunk) // 2):
                print("Instagram seems to be slowing down (many pages failed to load). Stopping here; "
                      "run it again later and it will carry on where it left off.")
                break
            if done < total:
                time.sleep(random.uniform(20, 40))    # a breather between batches
        if pending is not None:
            pending.result()
    print(f"Added {added} slide image(s) to the index.")
    return added


# --- Library: browsable folders by tag (--build-library) ---------------------------------
# Every image lives once, in cache/thumbs/<account>/. The library holds one folder per tag group
# (by-setting, by-outfit, by-shot, by-pose, by-arms), each with a sub-folder per tag, filled with
# shortcuts (symlinks) to those images, so one image shows up under all four of its tags without
# any copies. Shortcut names start with the tag's confidence (087_CODE.jpg) so a folder sorts by it.

LIBRARY_DIR = Path(__file__).with_name("library")


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip() or "unnamed"


def clear_views(root: Path) -> None:
    """Remove the old shortcuts (never real files) and any folders left empty."""
    for view in root.glob("by-*"):
        for dirpath, _, filenames in os.walk(view, topdown=False):
            for f in filenames:
                p = Path(dirpath) / f
                if p.is_symlink():
                    p.unlink()
            try:
                Path(dirpath).rmdir()
            except OSError:
                pass                                   # still has real files in it: leave alone


def build_library(username: str, min_conf: float, max_scrolls: int) -> Path | None:
    """(Re)build library/<account>/ from the saved thumbnails and indexes. Local only: no Instagram."""
    pose = load_pose(username)
    paths, vecs, pose = ensure_indexes(username, pose is not None, max_scrolls, False, False)
    keep = [i for i, p in enumerate(paths) if not is_video_path(p)]
    posts = [paths[i] for i in keep]
    tags = compute_tags(posts, vecs[keep], pose, min_conf)
    kinds = load_kinds(username)
    root = LIBRARY_DIR / username.lower()
    root.mkdir(parents=True, exist_ok=True)
    clear_views(root)

    facets = [f for f in known_tags() if f not in ("pose", "arms") or pose]
    rows, missing, links = [], 0, 0
    for p in posts:
        src = thumb_file(username, p)
        if not src.exists():
            missing += 1
            continue
        t = tags[p]
        row = {"post": base_post(p), "url": BASE + base_post(p),
               "type": "slide " + str(slide_no(p)) if is_slide(p) else kinds.get(p, ""),
               "file": os.path.relpath(src, root)}
        for facet in facets:
            got = t.get(facet)
            row[facet] = got[0] if got else ""
            row[f"{facet}_confidence"] = f"{got[1]:.2f}" if got else ""
            if facet == "arms" and not got:
                continue                               # by-arms only holds the posts with arms up
            folder = root / f"by-{facet}" / (safe_name(got[0]) if got else "unsorted")
            folder.mkdir(parents=True, exist_ok=True)
            link = folder / f"{int(round((got[1] if got else 0) * 100)):03d}_{src.name}"
            os.symlink(os.path.relpath(src, folder), link)
            links += 1
        rows.append(row)

    with open(root / "manifest.csv", "w", newline="") as fh:
        cols = ["post", "url", "type", "file"] + [c for f in facets for c in (f, f"{f}_confidence")]
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Library for {username}: {len(rows)} images in {len(facets)} views "
          f"({', '.join('by-' + f for f in facets)}) + manifest.csv -> {root}")
    if missing:
        print(f"  {missing} images have no saved thumbnail yet and were left out "
              f"(run --prepare to fetch them).")
    return root


# --- Importing your own folder of images (--import-folder) -------------------------------
DUP_SIM = 0.95   # two images this similar (cosine) are treated as the same photo
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def local_map_path(name: str) -> Path:
    return CACHE_DIR / f"{name.lower()}.local.json"


def load_local(name: str) -> dict:
    """{post key: original file path} for a collection made from a folder ({} for Instagram accounts)."""
    try:
        return json.loads(local_map_path(name).read_text())["source"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def folders_path(name: str) -> Path:
    return CACHE_DIR / f"{name.lower()}.folders.json"


def load_folders(name: str) -> dict:
    """{"folders": [paths imported into this collection], "seen": [files already looked at]}.

    Collections imported before this was tracked are picked up from their old records."""
    try:
        d = json.loads(folders_path(name).read_text())
        return {"folders": list(d.get("folders", [])), "seen": set(d.get("seen", []))}
    except (OSError, ValueError, TypeError):
        pass
    folders: list = []
    try:
        old = json.loads(local_map_path(name).read_text())
        if old.get("folder"):
            folders.append(old["folder"])
    except (OSError, ValueError, TypeError):
        pass
    seen = set(load_local(name).values()) | {v["file"] for v in load_videos(name)["videos"].values()}
    return {"folders": folders, "seen": seen}


def remember_folder(name: str, folder: Path, looked_at: list) -> None:
    d = load_folders(name)
    if str(folder) not in d["folders"]:
        d["folders"].append(str(folder))
    d["seen"] |= {str(f) for f in looked_at}
    CACHE_DIR.mkdir(exist_ok=True)
    folders_path(name).write_text(json.dumps({"folders": d["folders"], "seen": sorted(d["seen"])}))


SETTLE_SECONDS = 30      # a file changed this recently may still be copying; wait for the next check


def settled(f: Path) -> bool:
    try:
        return time.time() - f.stat().st_mtime > SETTLE_SECONDS
    except OSError:
        return False


def folder_media(folder: Path) -> list:
    """Image and video files in a folder (and sub-folders), skipping hidden ones."""
    if not folder.is_dir():
        return []
    return sorted(f for f in folder.rglob("*")
                  if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES | VIDEO_SUFFIXES
                  and not any(part.startswith(".") for part in f.relative_to(folder).parts))


def pending_files(name: str) -> list:
    """Files in the collection's imported folders that haven't been looked at yet."""
    d = load_folders(name)
    return [f for folder in d["folders"] for f in folder_media(Path(folder))
            if f.suffix.lower() in IMAGE_SUFFIXES and str(f) not in d["seen"] and settled(f)]


def imported_collections() -> list:
    names = {f.name.split(".")[0] for f in CACHE_DIR.glob("*.folders.json")}
    names |= {f.name.split(".")[0] for f in CACHE_DIR.glob("*.local.json")}
    return sorted(n for n in names if load_folders(n)["folders"])


def import_new(names: list | None = None) -> None:
    """Import whatever has been added to the already-imported folders since last time."""
    for name in names or imported_collections():
        todo = pending_files(name)
        if not todo:
            print(f"{name}: nothing new.")
            continue
        print(f"{name}: {len(todo)} new file(s).")
        for folder in load_folders(name)["folders"]:
            fp = Path(folder)
            if not fp.is_dir():
                print(f"  {folder} is no longer there; skipped.")
                continue
            if any(f.suffix.lower() in IMAGE_SUFFIXES for f in todo):
                import_folder(folder, name)


def import_folder(folder: str, name: str) -> None:
    """Add every image in `folder` (and its sub-folders) as a collection called `name`.

    Your files are only read. The tool keeps its own resized copies (max 1350 px) and builds the
    photo and pose indexes, so the collection behaves like an account. Running it again later
    adds only new files. Identical files are imported once.
    """
    import hashlib
    from PIL import Image
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    src = Path(folder).expanduser()
    if not src.is_dir():
        raise ScrapeError(f"'{folder}' is not a folder.")
    name = re.sub(r"[^\w.-]+", "_", name.strip().lower()).strip("_")
    if not name:
        raise ScrapeError("Give the collection a name.")
    files = sorted(f for f in src.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES
                   and not any(part.startswith(".") for part in f.relative_to(src).parts))
    waiting = [f for f in files if not settled(f)]       # still being copied: next time
    files = [f for f in files if f not in waiting]
    print(f"Found {len(files)} image file(s) in {src}." + (f" ({len(waiting)} still being copied; left for later.)" if waiting else ""))
    mapping = load_local(name)
    known_files = set(mapping.values())
    seen_hash = {Path(k.rstrip("/").split("/")[-1]).name for k in mapping}
    new_items, skipped, dupes = {}, 0, 0
    for i, f in enumerate(files, 1):
        if str(f) in known_files:
            continue
        try:
            h = hashlib.md5(f.read_bytes()).hexdigest()[:12]
            if h in seen_hash:
                dupes += 1
                continue
            with Image.open(f) as im:
                img = im.convert("RGB")
            img.thumbnail((SAVED_MAX, SAVED_MAX))
            key = f"/{name}/p/{h}/"
            dest = thumb_file(name, key)
            dest.parent.mkdir(parents=True, exist_ok=True)
            img.save(dest, "JPEG", quality=SAVED_QUALITY)
            seen_hash.add(h)
            mapping[key] = str(f)
            new_items[key] = ""
        except (OSError, ValueError):
            skipped += 1
        if i % 100 == 0:
            print(f"  ...{i} / {len(files)} read")
    print(f"{len(new_items)} new image(s) added; {dupes} duplicate(s) and {skipped} unreadable file(s) skipped.")
    if skipped and not len(new_items) and any(f.suffix.lower() in (".heic", ".heif") for f in files):
        print("Note: HEIC files need  python3 -m pip install pillow-heif")
    CACHE_DIR.mkdir(exist_ok=True)
    local_map_path(name).write_text(json.dumps({"source": mapping, "folder": str(src)}))
    remember_folder(name, src, files)
    if new_items:
        clip, pose = index_thumbs(name, new_items, True, True)
        # make sure the existing images are in the active model's index, so we merge rather than replace
        existing = load_embeddings(name) or convert_index(name)
        if clip and existing is not None and len(existing[0]):
            import numpy as np
            sims = (clip[1] @ existing[1].T).max(axis=1)
            dup = {p for p, v in zip(clip[0], sims) if v >= DUP_SIM}
            if dup:                                       # same photo already in this collection
                print(f"{len(dup)} image(s) look identical to ones already in '{name}' and were skipped.")
                for key in dup:
                    thumb_file(name, key).unlink(missing_ok=True)
                    mapping.pop(key, None)
                local_map_path(name).write_text(json.dumps({"source": mapping, "folder": str(src)}))
                keep = [i for i, p in enumerate(clip[0]) if p not in dup]
                clip = ([clip[0][i] for i in keep], clip[1][keep]) if keep else None
                if pose:
                    kp = [i for i, p in enumerate(pose[0]) if p not in dup]
                    pose = ([pose[0][i] for i in kp], pose[1][kp], pose[2][kp]) if kp else None
                new_items = {k: v for k, v in new_items.items() if k not in dup}
        if clip:
            save_embeddings(name, *merge_clip(existing, clip))
        if pose:
            save_pose(name, *merge_pose(load_pose(name), pose))
        kinds = {**load_kinds(name), **{k: "photo" for k in new_items}}
        kinds_path(name).write_text(json.dumps({"updated": time.time(), "kinds": kinds}))
    total = len(load_embeddings(name)[0]) if load_embeddings(name) else 0
    print(f"Collection '{name}' now holds {total} image(s). Pick it in the account box like any account.")


# --- Importing videos (--import-videos) -----------------------------------------------------
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
FRAME_EVERY = 2          # seconds between sampled frames
CLIP_SECONDS = 15        # length of a clip cut around a frame (0 = the whole video)
CLIPS_DIR = CACHE_DIR / "clips"


def videos_path(name: str) -> Path:
    return CACHE_DIR / f"{name.lower()}.videos.json"


def load_videos(name: str) -> dict:
    """{"videos": {id: {file, duration}}, "frames": {post key: {video, t}}} for a collection."""
    try:
        data = json.loads(videos_path(name).read_text())
        return {"videos": data.get("videos", {}), "frames": data.get("frames", {})}
    except (OSError, ValueError, TypeError):
        return {"videos": {}, "frames": {}}


def video_frame(name: str, key: str) -> dict | None:
    """{"file", "t", "duration"} if this index key is a frame of an imported video, else None."""
    data = load_videos(name)
    fr = data["frames"].get(key)
    vid = data["videos"].get(fr["video"]) if fr else None
    return {"file": vid["file"], "t": fr["t"], "duration": vid.get("duration", 0)} if vid else None


def video_duration(f: Path) -> float:
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(f)], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def make_clip(name: str, key: str, length: int | None = None, dest: Path | None = None) -> Path | None:
    """A clip of `length` seconds centred on the frame `key` (cached); length 0 means the whole video.

    With `dest` the result is written there. Without it, a cut clip is cached under cache/clips and
    the whole video is returned as the original file (nothing is copied). None if it can't be made.
    """
    import subprocess
    length = CLIP_SECONDS if length is None else length
    fr = video_frame(name, key)
    if not fr or not Path(fr["file"]).exists():
        return None
    if length <= 0:                                        # the full video
        if dest is None:
            return Path(fr["file"])
        shutil.copyfile(fr["file"], dest)
        return dest
    if not shutil.which("ffmpeg"):
        return None
    start = max(0.0, min(fr["t"] - length / 2, max(0.0, fr["duration"] - length)))
    if dest is None:
        CLIPS_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w-]", "", key)
        dest = CLIPS_DIR / f"{name.lower()}_{safe}_{length}.mp4"
    if dest.exists() and dest.stat().st_size:
        return dest
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", fr["file"],
                        "-t", str(length), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(dest)],
                       capture_output=True, text=True)
    if r.returncode or not dest.exists():
        dest.unlink(missing_ok=True)
        return None
    return dest


# --- Watched video folders ------------------------------------------------------------------
# A watched folder is its own small collection of videos. New files are noticed within seconds and
# registered with a preview picture only; no search model runs on them (they are watched, not searched).
POSTERS_DIR = CACHE_DIR / "posters"
WATCH_SETTLE = 4         # seconds a file must have been unchanged before it counts as fully copied


def watch_path(name: str) -> Path:
    return CACHE_DIR / f"{name.lower()}.watch.json"


def clean_name(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name.strip().lower()).strip("_")


def load_watch(name: str) -> dict:
    try:
        d = json.loads(watch_path(name).read_text())
        return {"folder": d["folder"], "videos": d.get("videos", {}), "dupes": d.get("dupes", []),
                "attached": has_photos(name)}          # decided live: a collection with photos gets videos mixed in
    except (OSError, ValueError, KeyError, TypeError):
        return {"folder": "", "videos": {}, "dupes": [], "attached": False}


def watched_collections() -> list:
    return sorted(f.name.split(".")[0] for f in CACHE_DIR.glob("*.watch.json"))


def has_photos(name: str) -> bool:
    """True if `name` is an account or collection with photos in the search index."""
    return any(CACHE_DIR.glob(f"{name}.*.npz")) or (CACHE_DIR / f"{name}.json").exists()


def start_watching(name: str, folder: str) -> str:
    """Watch `folder` for videos. A new name makes a videos-only collection; the name of an existing
    account or collection attaches the videos to it, so its searches bring up photos and some videos.
    Returns the cleaned name."""
    name = clean_name(name)
    if not name:
        raise ScrapeError("Give the collection a name.")
    if not Path(folder).expanduser().is_dir():
        raise ScrapeError("That folder wasn't found.")
    CACHE_DIR.mkdir(exist_ok=True)
    d = load_watch(name)
    d["folder"] = str(Path(folder).expanduser())
    watch_path(name).write_text(json.dumps({"folder": d["folder"], "videos": d["videos"], "dupes": d["dupes"]}))
    return name


def create_collections(rows: list) -> list:
    """Create many collections at once from [(name, folder path)].

    Videos in each folder (and its sub-folders) are registered right away, with no search model. Photos
    are not touched here; the returned report says which folders have photos so they can be imported.
    Returns one dict per row: name, folder, status, videos, photos.
    """
    report = []
    for raw_name, raw_path in rows:
        name, path = clean_name(raw_name or ""), (raw_path or "").strip().strip("'\"")
        row = {"name": name or (raw_name or "").strip(), "folder": path, "status": "", "videos": 0, "photos": 0}
        report.append(row)
        if not name and not path:
            row["status"] = "empty row, skipped"
            continue
        if not name or not path:
            row["status"] = "needs both a name and a folder"
            continue
        folder = Path(path).expanduser()
        if not folder.is_dir():
            row["status"] = "folder not found"
            continue
        if watch_path(name).exists() and load_watch(name)["folder"] != str(folder):
            row["status"] = f"already watching {load_watch(name)['folder']} (press Stop there first)"
            continue
        try:
            start_watching(name, str(folder))
            scan_watched(name)
        except ScrapeError as e:
            row["status"] = str(e)
            continue
        row["videos"] = len(load_watch(name)["videos"])
        row["photos"] = sum(1 for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES
                            and not any(part.startswith(".") for part in f.relative_to(folder).parts))
        row["status"] = "created"
    return report


def import_many(pairs_file: str) -> None:
    """Import the photos of several folders (a JSON list of [name, folder]); videos are not touched."""
    for name, folder in json.loads(Path(pairs_file).read_text()):
        print(f"\n##### {name}: {folder} #####")
        try:
            import_folder(folder, name)
        except ScrapeError as e:
            print(f"Error with {name}: {e}", file=sys.stderr)


def poster_file(name: str, vid: str) -> Path:
    """A watched video's preview picture. It lives with the other saved images so that results can show it."""
    return thumb_file(name, f"/{name.lower()}/p/{vid}/")


def is_watched(name: str) -> bool:
    return watch_path(name).exists()


def is_video_only(name: str) -> bool:
    """A watched folder that is a collection of its own (no photos)."""
    return watch_path(name).exists() and not load_watch(name)["attached"]


def is_attached(name: str) -> bool:
    return watch_path(name).exists() and load_watch(name)["attached"]


def is_video_post(name: str, path: str) -> bool:
    return watch_path(name).exists() and watched_video(name, path) is not None


VIDEO_SHARE = 0.2        # roughly this share of an account's picks are its attached videos (at least one)
ATTACHED_VIDEOS: dict = {}


def pick_mixed(photos: list, vids: list, n: int) -> list:
    """n picks of (score, path): mostly photos, with about VIDEO_SHARE of them videos when there are any."""
    k = min(len(vids), max(1, round(n * VIDEO_SHARE))) if vids else 0
    k = min(k, n)
    p = min(len(photos), n - k)
    k = min(len(vids), n - p)                       # too few photos: fill up with more videos
    out = random.sample(photos, p) + random.sample(vids, k)
    random.shuffle(out)
    return out


def watch_pool(name: str) -> list:
    """The watched videos as posts: [(0.0, '/name/p/<video id>/')]. They carry no search scores."""
    return [(0.0, f"/{name.lower()}/p/{vid}/") for vid, v in load_watch(name)["videos"].items()
            if Path(v["file"]).exists()]


def watched_video(name: str, path: str) -> dict | None:
    """{"id", "file", "duration", "start"} when `path` is a post key of a watched video. A key like
    /name/p/<id>_t120/ means 'the segment starting 120 s in'; "start" is None for a plain video key."""
    m = re.search(r"/p/([\w-]+)/?$", path)
    if not m:
        return None
    code, start = m.group(1), None
    if "_t" in code and code.rsplit("_t", 1)[1].isdigit():
        code, start = code.rsplit("_t", 1)[0], int(code.rsplit("_t", 1)[1])
    v = load_watch(name)["videos"].get(code)
    return {"id": code, **v, "start": start} if v else None


def video_segments(vids: list, k: int) -> list:
    """k picks of (user, post key) from the videos [(user, post key)]. Every pick is a segment of a video
    (key ..._t<start second>); videos are drawn independently at random, so any video can come up
    more than once (even in the same search), each time with a different, preferably non-overlapping, segment. A preview picture is made for each segment."""
    import subprocess
    length = CLIP_SECONDS if CLIP_SECONDS > 0 else 15
    order = random.choices(vids, k=k) if vids else []   # independent draws: a video can repeat, even back to back
    used: dict = {}
    out = []
    for user, path in order[:k]:
        wv = watched_video(user, path)
        if not wv:
            continue
        hi = max(0.0, wv["duration"] - length)
        starts = used.setdefault((user, wv["id"]), [])
        pick = None
        for _ in range(30):
            t = random.uniform(0, hi)
            pick = t if pick is None else pick
            if all(abs(t - x) >= length for x in starts):
                pick = t
                break
        starts.append(pick)
        t = int(pick)
        key = f"/{user}/p/{wv['id']}_t{t}/"
        poster = thumb_file(user, key)
        if not poster.exists():
            poster.parent.mkdir(parents=True, exist_ok=True)
            at = t + min(length, max(0.0, wv["duration"] - t)) / 2
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{at:.1f}", "-i", wv["file"], "-frames:v", "1",
                            "-vf", "scale='min(640,iw)':-2", "-q:v", "5", str(poster)], capture_output=True, stdin=subprocess.DEVNULL)
        out.append((user, key))
    return out


def cut_window(video: dict, length: int, dest: Path, start: float | None = None) -> tuple:
    """A window of `length` seconds from `video` (random start unless given). (start, file or None).
    length 0, or a video no longer than the window, returns (0, None): play the whole file."""
    import subprocess
    if length <= 0 or video["duration"] <= length:
        return 0.0, None
    if start is None:
        start = random.uniform(0, video["duration"] - length)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if _browser_safe(video["file"]):                 # copy the streams: near-instant, cuts snap to the keyframe before `start`
        r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", video["file"], "-t", str(length),
                            "-c", "copy", "-movflags", "+faststart", str(dest)], capture_output=True, stdin=subprocess.DEVNULL)
        if r.returncode == 0 and dest.exists() and dest.stat().st_size:
            return start, dest
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", video["file"], "-t", str(length),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-movflags", "+faststart", str(dest)], capture_output=True, stdin=subprocess.DEVNULL)
    return start, (dest if r.returncode == 0 and dest.exists() else None)


def _browser_safe(path: str) -> bool:
    """True when the file is H.264 video (with AAC or no audio) in an mp4/mov container, so a stream copy plays in a browser."""
    import subprocess
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,pix_fmt",
                              "-of", "csv=p=0", path], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL).stdout
    except Exception:
        return False
    names = [line.split(",")[0] for line in out.split() if line]
    return "h264" in names and "yuv420p" in out and all(n in ("h264", "aac", "mp3") for n in names)


def scan_watched(name: str) -> int:
    """Register videos that appeared in the watched folder (and its sub-folders). Returns how many were added."""
    import hashlib
    import subprocess
    d = load_watch(name)
    folder = Path(d["folder"])
    if not folder.is_dir():
        return 0
    gone = [vid for vid, v in d["videos"].items() if not Path(v["file"]).exists()]
    for vid in gone:                                             # deleted or moved out of the folder
        d["videos"].pop(vid)
        poster_file(name, vid).unlink(missing_ok=True)
    d["dupes"] = [x for x in d["dupes"] if Path(x).exists()]
    known = {v["file"] for v in d["videos"].values()} | set(d["dupes"])
    added, changed = 0, bool(gone)
    for f in sorted(folder.rglob("*")):
        if (not f.is_file() or f.suffix.lower() not in VIDEO_SUFFIXES or str(f) in known
                or any(part.startswith(".") for part in f.relative_to(folder).parts)):
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        if time.time() - st.st_mtime < WATCH_SETTLE:             # still being copied
            continue
        with f.open("rb") as fh:
            vid = hashlib.md5(fh.read(1_000_000) + str(st.st_size).encode()).hexdigest()[:12]
        if vid in d["videos"]:                                   # the same video under another name
            d["dupes"].append(str(f))
            changed = True
            continue
        dur = video_duration(f)
        if dur <= 0:                                             # not (yet) a readable video
            continue
        d["videos"][vid] = {"file": str(f), "duration": dur, "added": time.time(), "size": st.st_size}
        added += 1
    for vid, v in d["videos"].items():                           # previews are kept with the other saved images
        poster = poster_file(name, vid)
        if not poster.exists() and Path(v["file"]).exists():
            poster.parent.mkdir(parents=True, exist_ok=True)
            old = POSTERS_DIR / name.lower() / f"{vid}.jpg"
            if old.exists():
                shutil.copyfile(old, poster)
            else:
                subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{min(v['duration'] * 0.1, 5):.1f}",
                                "-i", v["file"], "-frames:v", "1", "-vf", "scale='min(640,iw)':-2", "-q:v", "5", str(poster)],
                               capture_output=True, stdin=subprocess.DEVNULL)
    if added or changed:
        watch_path(name).write_text(json.dumps({"folder": d["folder"], "videos": d["videos"], "dupes": d["dupes"]}))
    return added


def random_segment(name: str, length: int) -> tuple | None:
    """A random video from the collection and a random window in it: (video file, start second, clip file or None)."""
    vids = [v for v in load_watch(name)["videos"].values() if Path(v["file"]).exists()]
    if not vids:
        return None
    v = random.choice(vids)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    start, clip = cut_window(v, length, CLIPS_DIR / f"watch_{name.lower()}_{int(time.time() * 1000)}.mp4")
    return v["file"], start, clip


def import_videos(folder: str, name: str) -> None:
    """Add every video in `folder` to the collection `name`: one searchable frame every few seconds.

    Your videos are only read. The tool keeps a small picture of each sampled frame (so search, tags
    and pose matching work on them) and cuts a clip around a frame when you ask for one.
    """
    import hashlib
    import subprocess
    import tempfile
    from PIL import Image
    if not shutil.which("ffmpeg"):
        raise ScrapeError("ffmpeg is needed to read videos:  brew install ffmpeg")
    src = Path(folder).expanduser()
    files = [src] if src.is_file() else sorted(
        f for f in src.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_SUFFIXES
        and not any(part.startswith(".") for part in f.relative_to(src).parts))
    if not files:
        raise ScrapeError(f"No video files found in '{folder}'.")
    name = re.sub(r"[^\w.-]+", "_", name.strip().lower()).strip("_")
    if not name:
        raise ScrapeError("Give the collection a name.")
    waiting = [f for f in files if not settled(f)]
    files = [f for f in files if f not in waiting]
    print(f"Found {len(files)} video file(s)." + (f" ({len(waiting)} still being copied; left for later.)" if waiting else ""))
    data = load_videos(name)
    mapping = load_local(name)
    new_items: dict[str, str] = {}
    # the images already in the collection, taken before any new frame is written to disk
    existing = load_embeddings(name) or (convert_index(name) if thumb_file(name, f"/{name}/p/x/").parent.exists() else None)
    for n, f in enumerate(files, 1):
        with f.open("rb") as fh:
            h = hashlib.md5(fh.read(4_000_000) + str(f.stat().st_size).encode()).hexdigest()[:10]
        if h in data["videos"]:
            print(f"  [{n}/{len(files)}] {f.name}: already imported, skipped.")
            continue
        dur = video_duration(f)
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-vf",
                                f"fps=1/{FRAME_EVERY},scale='min({SAVED_MAX},iw)':-2", "-q:v", "4",
                                str(Path(tmp) / "f%05d.jpg")], capture_output=True, text=True)
            frames = sorted(Path(tmp).glob("f*.jpg"))
            if r.returncode and not frames:
                print(f"  [{n}/{len(files)}] {f.name}: could not be read ({r.stderr.strip()[:120]}).")
                continue
            for i, fp in enumerate(frames):
                t = i * FRAME_EVERY
                key = f"/{name}/p/v{h}_{t}/"
                dest = thumb_file(name, key)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(fp) as im:
                    im.convert("RGB").save(dest, "JPEG", quality=SAVED_QUALITY)
                data["frames"][key] = {"video": h, "t": t}
                mapping[key] = str(f)
                new_items[key] = ""
        data["videos"][h] = {"file": str(f), "duration": dur}
        print(f"  [{n}/{len(files)}] {f.name}: {len(frames)} frames ({int(dur)} s).")
    if src.is_dir():                                   # a single file isn't a folder to watch
        remember_folder(name, src, files)
    if not new_items:
        print("Nothing new to add.")
        return
    CACHE_DIR.mkdir(exist_ok=True)
    prev = json.loads(local_map_path(name).read_text()).get("folder", str(src)) if local_map_path(name).exists() else str(src)
    local_map_path(name).write_text(json.dumps({"source": mapping, "folder": prev}))
    clip, pose = index_thumbs(name, new_items, True, True)

    # drop frames that look the same as the frame before them (a still shot) or an existing image
    drop: set = set()
    if clip:
        import numpy as np
        order = sorted(range(len(clip[0])), key=lambda i: (clip[0][i].rsplit("_", 1)[0], int(clip[0][i].rstrip("/").rsplit("_", 1)[1])))
        last = None
        for i in order:
            if last is not None and clip[0][i].rsplit("_", 1)[0] == clip[0][last].rsplit("_", 1)[0] \
                    and float(clip[1][i] @ clip[1][last]) >= DUP_SIM:
                drop.add(clip[0][i])
            else:
                last = i
        if existing is not None and len(existing[0]):
            sims = (clip[1] @ existing[1].T).max(axis=1)
            drop |= {p for p, v in zip(clip[0], sims) if v >= DUP_SIM}
        if drop:
            print(f"{len(drop)} near-identical frame(s) skipped.")
            for key in drop:
                thumb_file(name, key).unlink(missing_ok=True)
                mapping.pop(key, None)
                data["frames"].pop(key, None)
            keep = [i for i, p in enumerate(clip[0]) if p not in drop]
            clip = ([clip[0][i] for i in keep], clip[1][keep]) if keep else None
            if pose:
                kp = [i for i, p in enumerate(pose[0]) if p not in drop]
                pose = ([pose[0][i] for i in kp], pose[1][kp], pose[2][kp]) if kp else None
            new_items = {k: v for k, v in new_items.items() if k not in drop}
    local_map_path(name).write_text(json.dumps({"source": mapping, "folder": prev}))
    videos_path(name).write_text(json.dumps(data))
    if clip:
        save_embeddings(name, *merge_clip(existing, clip))
    if pose:
        save_pose(name, *merge_pose(load_pose(name), pose))
    kinds = {**load_kinds(name), **{k: "photo" for k in new_items}}
    kinds_path(name).write_text(json.dumps({"updated": time.time(), "kinds": kinds}))
    total = len(load_embeddings(name)[0]) if load_embeddings(name) else 0
    print(f"Collection '{name}' now holds {total} image(s) including {len(new_items)} video frame(s).")


def set_frame_every(seconds: int) -> None:
    global FRAME_EVERY
    FRAME_EVERY = max(1, int(seconds))


def index_videos_many(pairs_file: str) -> None:
    """Make several watched video folders searchable, one after another (a JSON list of [name, folder])."""
    pairs = json.loads(Path(pairs_file).read_text())
    for i, (name, folder) in enumerate(pairs, 1):
        print(f"\n##### [{i}/{len(pairs)}] {name}: {folder} #####")
        try:
            import_videos(folder, name)
        except ScrapeError as e:
            print(f"Error with {name}: {e}", file=sys.stderr)
        print(f"Progress: {i} / {len(pairs)} folders done")


def prepare_account(username: str, max_scrolls: int, expand_n: int = 0, workers: int = 1) -> None:
    """Do all the one-off work for an account, so every later search is instant.

    Reads the profile, keeps the thumbnails, builds the photo index and the pose index, records
    which posts are carousels, optionally opens up to `expand_n` posts to index every photo in
    them, then prints the category breakdown. Safe to run again: it only fills in what's missing.
    """
    print(f"\n=== Preparing {username} ===")
    paths, vecs, pose = ensure_indexes(username, True, max_scrolls, False, False)
    if index_orphan_slides(username):
        paths, vecs, pose = ensure_indexes(username, True, max_scrolls, False, False)
    if expand_n:
        posts = [p for p in paths if not is_slide(p)]
        todo = carousel_candidates(username, posts, expand_n)
        if todo:
            expand_carousels(username, todo, workers=workers)
        else:
            print("Every post has been looked inside already.")
    list_tags(username, 0.5, max_scrolls)
    build_library(username, 0.5, max_scrolls)
    print(f"\n{username}: ready. Photo search, tags, pose, the breakdown and the library folders "
          f"now work instantly.")


def convert_index(username: str):
    """Build the active model's index for an account from its saved thumbnails (no Instagram).

    Used the first time an account is opened after switching models: the post list comes from the
    other model's index, and the images from cache/thumbs. Posts without a saved image are dropped
    (and reported). Returns (paths, vectors) or None if there's nothing to convert.
    """
    import numpy as np
    from PIL import Image
    other = next((k for k in MODELS if k != ACTIVE_MODEL and index_file(username, k).exists()), None)
    if other is None:
        return None
    paths = [str(p) for p in np.load(index_file(username, other), allow_pickle=False)["paths"]]
    have = [p for p in paths if thumb_file(username, p).exists()]
    if not have:
        return None
    print(f"Building the {ACTIVE_MODEL} index for {username} from {len(have)} saved images "
          f"(one-off, no Instagram needed)...")
    out_paths, chunks = [], []
    for i in range(0, len(have), 64):
        batch, imgs = [], []
        for p in have[i:i + 64]:
            try:
                with Image.open(thumb_file(username, p)) as im:
                    imgs.append(im.convert("RGB"))
                batch.append(p)
            except OSError:
                continue
        if imgs:
            chunks.append(image_features(imgs))
            out_paths += batch
        if (i // 64) % 8 == 7:
            print(f"  ...{min(i + 64, len(have))} / {len(have)}")
    if not chunks:
        return None
    if len(have) < len(paths):
        print(f"  {len(paths) - len(have)} posts had no saved image and are left out of this index.")
    vecs = np.concatenate(chunks)
    save_embeddings(username, out_paths, vecs)
    return out_paths, vecs


def ensure_indexes(username: str, need_pose: bool, max_scrolls: int, refresh: bool, full: bool):
    """Return (paths, CLIP vectors, pose triple or None), building/updating indexes as needed."""
    import numpy as np
    clip = None if full else (load_embeddings(username) or convert_index(username))
    pose = None if full else load_pose(username)
    keep_pose = need_pose or pose is not None          # keep an existing pose index in sync

    if clip is None:                                   # no index yet: scrape + analyse everything
        _, thumbs = fetch_links(username, max_scrolls)
        clip, new_pose = index_thumbs(username, thumbs, True, keep_pose)
        if clip is None:
            raise ScrapeError("Couldn't get any thumbnails to analyze.")
        save_embeddings(username, *clip)
        if new_pose:
            pose = new_pose
            save_pose(username, *pose)
        paths, vecs = clip
    else:
        paths, vecs = clip
        if refresh:                                    # analyse only posts newer than the index
            _, thumbs = fetch_links(username, max_scrolls, set(paths))
            have = set(paths)
            new = {p: u for p, u in thumbs.items() if p not in have}
            if new:
                new_clip, new_pose = index_thumbs(username, new, True, keep_pose)
                if new_clip:
                    paths, vecs = paths + new_clip[0], np.concatenate([vecs, new_clip[1]])
                    save_embeddings(username, paths, vecs)
                if new_pose:
                    pose = merge_pose(pose, new_pose)
                    save_pose(username, *pose)
        else:
            print(f"Using photo index: {len(paths)} posts.")

    if need_pose:
        have_pose = set(pose[0]) if pose else set()
        missing = [p for p in paths if p not in have_pose]
        if missing:                                    # backfill poses (thumbnails kept on disk if possible)
            thumbs = {p: "" for p in missing if thumb_file(username, p).exists()}
            off_disk = [p for p in missing if p not in thumbs]
            if off_disk:
                print(f"Building the pose index: {len(off_disk)} posts need their photos again, "
                      f"so the profile is read once more (one-off).")
                _, fresh = fetch_links(username, max_scrolls)
                thumbs.update({p: fresh[p] for p in off_disk if fresh.get(p)})
            _, new_pose = index_thumbs(username, thumbs, False, True)
            if new_pose:
                pose = merge_pose(pose, new_pose)
                save_pose(username, *pose)
        if not pose:
            raise ScrapeError("Couldn't build a pose index for this account.")
    return paths, vecs, pose


# --- Post dates ---------------------------------------------------------------------------
# An Instagram post code is an encoded media id, and the top bits of that id are the upload time
# (milliseconds since 2011-08-24). So every post can be dated from its code alone, with no extra
# visit to Instagram. Checked against 1,811 posts with known dates: all within 2 days.
_CODE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
MIX_VIDEOS = False       # with a search or tags, still add random videos from watched folders
DATE_RANGE: tuple[float | None, float | None] = (None, None)      # (not before, before) in unix seconds


def post_time(path: str) -> float | None:
    """Upload time (unix seconds) of an Instagram post, or None for imported images and video frames."""
    m = re.search(r"/(?:p|reel|reels)/([\w-]+)", path)
    code = m.group(1) if m else ""
    if not 9 <= len(code) <= 11 or any(c not in _CODE_CHARS for c in code):
        return None
    n = 0
    for c in code:
        n = n * 64 + _CODE_CHARS.index(c)
    t = ((n >> 23) + 1314220021721) / 1000
    return t if 1.28e9 < t < time.time() + 86400 else None


def parse_date(text: str) -> float:
    """'2022' or '2022-03' or '2022-03-15' -> unix seconds at the start of that period (UTC)."""
    import calendar
    parts = [int(x) for x in text.strip().split("-")] + [1, 1]
    return float(calendar.timegm((parts[0], parts[1], parts[2], 0, 0, 0)))


def set_date_range(after: str | None, before: str | None) -> None:
    global DATE_RANGE
    try:
        DATE_RANGE = (parse_date(after) if after else None, parse_date(before) if before else None)
    except (ValueError, IndexError):
        raise ScrapeError("Dates look like 2022 or 2022-03-15.")


def in_date_range(path: str) -> bool:
    lo, hi = DATE_RANGE
    if lo is None and hi is None:
        return True
    t = post_time(path)
    if t is None:                                   # no date known: left out when a range is asked for
        return False
    return (lo is None or t >= lo) and (hi is None or t < hi)


def apply_date_range(items: list, path_of=lambda x: x[1]) -> list:
    """Keep only the items inside the date range (all of them when no range is set)."""
    if DATE_RANGE == (None, None):
        return items
    kept = [x for x in items if in_date_range(path_of(x))]
    print(f"Date filter: {len(kept)} of {len(items)} kept.")
    if not kept:
        raise ScrapeError("No posts in that date range.")
    return kept


def find_pool(username: str, query: Query, top: int, max_scrolls: int,
              refresh: bool, full: bool, worst: bool = False,
              photos_only: bool = True, tags=None, min_conf: float = 0.5,
              expand: int = 0) -> list[tuple[float, str]]:
    """Return the `top` best (score, path) matches for `query`, building/updating the index as needed."""
    import numpy as np
    paths, vecs, pose = ensure_indexes(username, bool(query.pose_ref) or specs_need_pose(tags or []),
                                       max_scrolls, refresh, full)
    allowed_tags = tagged_posts(tags, paths, vecs, pose, min_conf) if tags else None

    if query.pose_ref:
        ppaths, psegs, pvis = pose
        scores = pose_similarity(query.pose_refs(), psegs, pvis)
        usable = pvis.sum(axis=1) >= MIN_SHARED       # posts where a body was found
        allowed = None
        if query.has_scene:                           # scene acts as a gate: keep the best-matching share
            cs = dict(rank_by_vec(query.vec(), paths, vecs))
            cutoff = float(np.quantile(list(cs.values()), 1 - query.scene_top))
            allowed = {p for p, v in cs.items() if v >= cutoff}
            print(f"Scene filter: keeping the best {query.scene_top:.0%} of posts for the scene.")
        ranked = sorted(((float(sc), p) for sc, p, ok in zip(scores, ppaths, usable)
                         if ok and (allowed is None or p in allowed)), reverse=True)
        print(f"A body was detected in {int(usable.sum())} of {len(ppaths)} posts.")
        if not ranked:
            raise ScrapeError("No posts with a detectable body match the filters.")
    else:
        ranked = rank_by_vec(query.vec(), paths, vecs)
    if allowed_tags is not None:                      # --tag: only posts carrying every requested tag
        ranked = [r for r in ranked if r[1] in allowed_tags]
        print(f"Tag filter: {len(allowed_tags)} posts carry {' + '.join(l for _, l in tags)}.")
        if not ranked:
            raise ScrapeError("No posts match both the tags and the search.")
    if photos_only:                                   # reels are videos; drop them before ranking
        ranked = [r for r in ranked if not is_video_path(r[1])]
        if not ranked:
            raise ScrapeError("This account has no photo posts.")
    ranked = apply_date_range(ranked)
    if expand and not worst:                          # look inside the best-ranked carousels, then re-rank
        todo = carousel_candidates(username, [p for _, p in ranked], expand)
        if todo and expand_carousels(username, todo):
            return find_pool(username, query, top, max_scrolls, False, False, worst, photos_only,
                             tags, min_conf, 0)
    print(f"Score range across {len(ranked)} posts: best {ranked[0][0]:.3f}, "
          f"median {ranked[len(ranked) // 2][0]:.3f}, worst {ranked[-1][0]:.3f}")
    # --worst: the LOWEST-scoring posts, a sanity check that bad matches really don't fit.
    return ranked[-top:] if worst else ranked[:top]


IMAGE_EXT = {"image/jpeg": ".jpg", "image/webp": ".webp", "image/png": ".png"}

# Picks the main photo on a post page: the <img> with the biggest on-screen area (avatars and
# icons are tiny), then the widest candidate from its srcset. NOT og:image, which Instagram
# serves as a cropped thumbnail.
_MAIN_IMG_JS = """() => {
    const pick = sel => {
        let best = null, area = 0;
        for (const im of document.querySelectorAll(sel)) {
            const a = im.clientWidth * im.clientHeight;
            if (im.naturalWidth > 300 && a > area) { best = im; area = a; }
        }
        return best;
    };
    const im = pick('article img') || pick('main img');
    if (!im) return '';
    let url = im.currentSrc || im.src, widest = 0;
    for (const m of (im.srcset || '').matchAll(/(\\S+)\\s+(\\d+)w/g)) {
        if (+m[2] > widest) { widest = +m[2]; url = m[1]; }
    }
    return url;
}"""

# The post's date: the earliest <time datetime> on the page (comments are always newer than the post).
_POST_DATE_JS = """() => {
    const ts = [...document.querySelectorAll('time[datetime]')]
        .map(t => t.getAttribute('datetime')).filter(Boolean).sort();
    return ts.length ? ts[0] : '';
}"""

# True if the post page shows a video (reels, old video posts, carousels that open on a video).
_IS_VIDEO_JS = """() => !!(document.querySelector('article video, main video')
    || document.querySelector('meta[property="og:video"]'))"""


def is_video_path(path: str) -> bool:
    """Reels live under /reel/ or /reels/; they are always videos."""
    return bool(re.search(r"/(?:reel|reels)/", path))


# --- Carousel support (--all-slides) -------------------------------------------------
MAX_SLIDES = 20      # never click through more than this many slides in one post
MISS_LIMIT = 3       # stop a carousel after this many off-topic slides in a row
NEXT_BUTTON = 'article button[aria-label="Next"], main button[aria-label="Next"]'

# Centre point of the main photo's on-screen box. The visible slide always sits at this spot,
# so after each click we can ask "what image is under this point?".
_MAIN_IMG_CENTER_JS = """() => {
    let best = null, area = 0;
    for (const im of document.querySelectorAll('article img, main img')) {
        const a = im.clientWidth * im.clientHeight;
        if (im.naturalWidth > 300 && a > area) { best = im; area = a; }
    }
    if (!best) return null;
    const r = best.getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2];
}"""

# The element on top at point [x, y]: {kind: 'image'|'video'|'none', url}.
_SLIDE_AT_JS = """([x, y]) => {
    for (const el of document.elementsFromPoint(x, y)) {
        if (el.tagName === 'VIDEO') return {kind: 'video', url: ''};
        if (el.tagName === 'IMG' && el.naturalWidth > 300) {
            let url = el.currentSrc || el.src, widest = 0;
            for (const m of (el.srcset || '').matchAll(/(\\S+)\\s+(\\d+)w/g)) {
                if (+m[2] > widest) { widest = +m[2]; url = m[1]; }
            }
            return {kind: 'image', url};
        }
    }
    return {kind: 'none', url: ''};
}"""


def url_key(url: str) -> str:
    """Identify an image by its URL without the changing query string."""
    return url.split("?")[0]


def fetch_image(context, url: str):
    """Download an image with the logged-in session. Returns (bytes, extension) or None."""
    resp = context.request.get(url) if url else None
    if not (resp and resp.ok):
        return None
    return resp.body(), IMAGE_EXT.get(resp.headers.get("content-type", "").split(";")[0], ".jpg")


def make_scorer(query: Query):
    """Return fn(image bytes) -> similarity to `query` (pose similarity if --pose, else CLIP)."""
    import io
    from PIL import Image

    if query.pose_ref:
        refs = query.pose_refs()

        def pose_score(data: bytes) -> float:
            segs, vis = pose_features(Image.open(io.BytesIO(data)))
            return float(pose_similarity(refs, segs[None], vis[None])[0])
        return pose_score

    q = query.vec()

    def score(data: bytes) -> float:
        return float(embed_image(Image.open(io.BytesIO(data))) @ q)
    return score


def collect_slides(page, context, first_url: str, scorer, first_score, margin: float):
    """Click through the rest of a carousel. Returns [(slide number, bytes, ext, score)].

    With a `scorer` (--find), a slide is kept only if it scores within `margin` of the
    first slide, and we give up after MISS_LIMIT off-topic slides in a row (the first slide
    is usually a good guide to the rest, so a streak means the carousel moved on).
    Without one, every photo slide is kept. Video slides are always skipped.
    """
    center = page.evaluate(_MAIN_IMG_CENTER_JS)
    if not center:
        return []
    seen = {url_key(first_url)}
    extras, misses = [], 0
    for number in range(2, MAX_SLIDES + 1):
        if not page.query_selector(NEXT_BUTTON):
            break                                          # last slide (or not a carousel)
        page.click(NEXT_BUTTON)
        info = {"kind": "none", "url": ""}
        for _ in range(4):                                 # wait for the new slide to render
            page.wait_for_timeout(random.randint(500, 800))
            info = page.evaluate(_SLIDE_AT_JS, center)
            if info["kind"] == "video" or (info["kind"] == "image"
                                           and url_key(info["url"]) not in seen):
                break
        if info["kind"] == "video":
            print(f"    slide {number}: video, skipped")
            continue
        if info["kind"] != "image" or url_key(info["url"]) in seen:
            break                                          # nothing new appeared: we're done
        seen.add(url_key(info["url"]))
        got = fetch_image(context, info["url"])
        if not got:
            continue
        data, ext = got
        score = scorer(data) if scorer else None
        if scorer and first_score is not None and score < first_score - margin:
            misses += 1
            print(f"    slide {number}: off-topic ({score:.3f}), skipped")
            if misses >= MISS_LIMIT:
                print(f"    {MISS_LIMIT} off-topic slides in a row; leaving this carousel.")
                break
            continue
        misses = 0
        extras.append((number, data, ext, score))
    return extras


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    dest, n = folder / f"{stem}{ext}", 2
    while dest.exists():                                   # same day + score: don't overwrite
        dest, n = folder / f"{stem}-{n}{ext}", n + 1
    return dest


def save_images(groups: list[tuple[list[tuple[str, str, float | None]], int]],
                folder: Path, scorer=None, all_slides: bool = False,
                margin: float = 0.03) -> list[Path]:
    """Save the photos of posts into `folder`; returns the files written.

    `groups` is a list of (candidates, want): candidates are (username, post path, score) in
    order, where score is the --find similarity (None without --find). We walk them until
    `want` posts are saved; posts that turn out to be videos, or whose photo can't be found,
    are skipped and the next candidate is used instead.

    Files are named username_DD-MM-YYYY_score.ext (no score without --find). With
    all_slides, the other carousel photos are saved as ..._score_02.ext, ..._03.ext, ...
    using their own scores; otherwise only the first image is saved.
    """
    if not AUTH_FILE.exists():
        raise ScrapeError(f"{AUTH_FILE.name} not found. Run `python login.py` first.")
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=str(AUTH_FILE),
                                          viewport={"width": 1280, "height": 1000})
            page = context.new_page()
            for candidates, want in groups:
                got = 0
                for username, path, score in candidates:
                    if got >= want:
                        break
                    wv = watched_video(username, path) if watch_path(username).exists() else None
                    if wv:                               # a watched video: a random clip of it, or the whole file
                        date = fmt_date(time.strftime("%Y-%m-%d", time.localtime(Path(wv["file"]).stat().st_mtime)))
                        stem = f"{username}_{date}"
                        if CLIP_SECONDS <= 0 or wv["duration"] <= CLIP_SECONDS:
                            dest = unique_path(folder, stem, Path(wv["file"]).suffix.lower())
                            shutil.copyfile(wv["file"], dest)
                        else:
                            dest = unique_path(folder, stem, ".mp4")
                            _, dest = cut_window(wv, CLIP_SECONDS, dest, wv.get("start"))
                        if dest:
                            saved.append(dest)
                            got += 1
                            print(f"  saved {dest.name}  <-  {wv['file']}")
                        else:
                            print(f"  skipped {path}: the clip could not be cut")
                        continue
                    if video_frame(username, path):      # a frame of an imported video: save a clip
                        vf = video_frame(username, path)
                        date = fmt_date(time.strftime("%Y-%m-%d", time.localtime(Path(vf["file"]).stat().st_mtime)))
                        stem = f"{username}_{date}" + (f"_{score:.3f}" if score is not None else "")
                        ext = Path(vf["file"]).suffix.lower() if CLIP_SECONDS <= 0 else ".mp4"
                        dest = make_clip(username, path, dest=unique_path(folder, stem, ext))
                        if dest:
                            saved.append(dest)
                            got += 1
                            print(f"  saved {dest.name}  <-  {vf['file']} at {vf['t']} s")
                        else:
                            print(f"  skipped {path}: the clip could not be cut")
                        continue
                    original = load_local(username).get(path)
                    if original:                         # imported folder: copy the original file
                        date = fmt_date(time.strftime("%Y-%m-%d", time.localtime(Path(original).stat().st_mtime)))
                        stem = f"{username}_{date}" + (f"_{score:.3f}" if score is not None else "")
                        dest = unique_path(folder, stem, Path(original).suffix.lower())
                        shutil.copyfile(original, dest)
                        saved.append(dest)
                        got += 1
                        print(f"  saved {dest.name}  <-  {original}")
                        continue
                    if is_slide(path):                   # a slide we already saved while expanding
                        f = thumb_file(username, path)
                        if not f.exists():
                            print(f"  skipped {path}: slide image missing from the cache")
                            continue
                        date = fmt_date(load_expanded(username).get(base_post(path), {}).get("date"))
                        stem = f"{username}_{date}" + (f"_{score:.3f}" if score is not None else "")
                        dest = unique_path(folder, f"{stem}_{slide_no(path):02d}", ".jpg")
                        shutil.copyfile(f, dest)
                        saved.append(dest)
                        got += 1
                        print(f"  saved {dest.name}  <-  {BASE + base_post(path)}")
                        continue
                    try:
                        page.goto(BASE + path, wait_until="domcontentloaded", timeout=30_000)
                        if "/accounts/login" in page.url:
                            raise ScrapeError("Session expired. Re-run `python login.py`.")
                        try:
                            page.wait_for_selector("article img, article video, main img", timeout=10_000)
                        except PlaywrightTimeout:
                            pass
                        page.wait_for_timeout(1500)      # let the full-size image swap in

                        if page.evaluate(_IS_VIDEO_JS):
                            print(f"  skipped {path}: video")
                            continue
                        src = page.evaluate(_MAIN_IMG_JS)
                        first = fetch_image(context, src)
                        if not first:
                            print(f"  skipped {path}: couldn't find the photo")
                            continue
                        data, ext = first
                        date = (page.evaluate(_POST_DATE_JS) or "")[:10]      # YYYY-MM-DD
                        date = "-".join(reversed(date.split("-"))) if len(date) == 10 else "unknown-date"
                        base = f"{username}_{date}"

                        dest = unique_path(folder, base + (f"_{score:.3f}" if score is not None else ""), ext)
                        dest.write_bytes(data)
                        saved.append(dest)
                        got += 1
                        print(f"  saved {dest.name}  <-  {BASE + path}")

                        if all_slides:
                            first_score = scorer(data) if scorer else None
                            for number, sdata, sext, sscore in collect_slides(
                                    page, context, src, scorer, first_score, margin):
                                stem = base + (f"_{sscore:.3f}" if sscore is not None else "")
                                sdest = unique_path(folder, f"{stem}_{number:02d}", sext)
                                sdest.write_bytes(sdata)
                                saved.append(sdest)
                                print(f"    saved {sdest.name}")
                    except PlaywrightTimeout:
                        print(f"  skipped {path}: page timed out")
                    page.wait_for_timeout(random.randint(800, 1800))
                if got < want:
                    print(f"  only {got} of {want} posts saved for this group (ran out of candidates).")
        finally:
            browser.close()
    return saved


def get_pool(username: str, *args, **kwargs) -> list[tuple[float, str]]:
    """The account's photo pool; videos attached to it are set aside in ATTACHED_VIDEOS for run() to mix in."""
    pool = _get_pool(username, *args, **kwargs)
    if is_attached(username):
        scan_watched(username)
        ATTACHED_VIDEOS[username] = watch_pool(username)
    return pool


def _get_pool(username: str, max_scrolls: int, refresh: bool, full: bool, cache_hours: float,
              find: Query | None, top: int, worst: bool = False,
              photos_only: bool = True, tags=None, min_conf: float = 0.5,
              expand: int = 0) -> list[tuple[float, str]]:
    """Return this account's candidate posts as (score, path). Score is 0 without --find/--tag."""
    if is_video_only(username):                        # watched video folder: random picks only
        if (find or tags) and not MIX_VIDEOS:
            raise ScrapeError(f"{username} is a watched video folder; videos are not searched by content, "
                              f"so it is left out of searches and tag filters.")
        if find or tags:
            print(f"{username}: videos can't be matched to the search, so random ones are mixed in.")
        scan_watched(username)
        pool = watch_pool(username)
        if not pool:
            raise ScrapeError(f"{username} has no videos yet.")
        print(f"Watched video folder: {len(pool)} videos.")
        return pool
    if find:
        return find_pool(username, find, top, max_scrolls, refresh, full, worst, photos_only,
                         tags, min_conf, expand)
    if tags:                                          # tags only: random among the tagged posts
        paths, vecs, pose = ensure_indexes(username, specs_need_pose(tags), max_scrolls, refresh, full)
        hits = tagged_posts(tags, paths, vecs, pose, min_conf)
        print(f"Tag filter: {len(hits)} posts carry {' + '.join(l for _, l in tags)}.")
        pool = [(c, p) for p, c in hits.items() if not (photos_only and is_video_path(p))]
        pool = apply_date_range(pool) if pool else pool
        if not pool:
            raise ScrapeError("No posts carry those tags (try --list-tags, or lower --min-conf).")
        if expand:
            todo = carousel_candidates(username, [p for _, p in sorted(pool, reverse=True)], expand)
            if todo and expand_carousels(username, todo):
                return get_pool(username, max_scrolls, False, False, cache_hours, find, top, worst,
                                photos_only, tags, min_conf, 0)
        return pool
    update = refresh or full
    # Refreshing needs the old cache whatever its age, so ignore the age limit then.
    cached = load_cache(username, float("inf") if update else cache_hours, announce=not update)
    if full or cached is None:
        paths, _ = fetch_links(username, max_scrolls)                # scrape everything
    elif refresh:
        paths, _ = fetch_links(username, max_scrolls, set(cached))   # new posts only
    else:
        paths = cached
    if photos_only:
        paths = [p for p in paths if not is_video_path(p)]
    return apply_date_range([(0.0, p) for p in paths])


def even_pick(by_user: dict, total: int, vids: dict | None = None) -> list:
    """Take `total` posts spread evenly over the accounts in `by_user` ({user: [(score, path)]}),
    in random order. An account that has fewer than its share gives what it has and the others
    make up the difference. The picked posts are removed from `by_user`."""
    picked: list = []
    want = total
    while want > 0:
        live = [u for u, items in by_user.items() if items or (vids or {}).get(u)]
        if not live:
            break
        share, extra = divmod(want, len(live))
        bonus = set(random.sample(live, extra))
        took = 0
        for u in live:
            have = len(by_user[u]) + len((vids or {}).get(u, []))
            n = min(share + (u in bonus), have)
            for item in pick_mixed(by_user[u], (vids or {}).get(u, []), n):
                (by_user[u] if item in by_user[u] else vids[u]).remove(item)
                picked.append((item[0], u, item[1]))
            took += n
        if not took:
            break
        want -= took
    random.shuffle(picked)
    return picked


def run(usernames: list[str], max_scrolls: int, open_browser: bool, count: int,
        refresh: bool, full: bool, cache_hours: float,
        find: Query | None = None, top: int = 50, save_dir: str | None = None,
        combine: bool = False, worst: bool = False, include_videos: bool = False,
        all_slides: bool = False, slide_margin: float = 0.03,
        tags=None, min_conf: float = 0.5, all_posts: bool = False, limit: int = 0,
        expand: int = 0, even: bool = False, video_pct: int | None = None) -> bool:
    """Process the accounts one after another. Returns True if every account succeeded.

    Sequential on purpose: one account at a time is gentler on Instagram's rate limits,
    and the CLIP model is loaded once and reused.
    """
    # With --save we line up spare candidates, so skipped videos can be replaced.
    spare = 3 if save_dir else 1
    groups: list[tuple[list[tuple[str, str, float | None]], int]] = []   # ([(user, path, score)], wanted)
    pools: list[tuple[float, str, str]] = []           # (score, username, path) when combining
    vids_by_user: dict = {}
    photos_mix: dict = {}                              # video_pct mode: photo pool per account
    mix_vids: list = []                                # video_pct mode: every video, [(user, post key)]
    failed = False
    if expand and not (find or tags):
        print("Note: --expand-carousels needs a search or tags to decide which carousels look "
              "promising; ignoring it.")
        expand = 0

    for n, username in enumerate(usernames):
        print(f"\n=== {username} ({n + 1}/{len(usernames)}) ===")
        before = _network_calls
        if video_pct is not None:
            if is_watched(username):
                scan_watched(username)
                mix_vids += [(username, p) for _, p in watch_pool(username)]
                ATTACHED_VIDEOS.pop(username, None)
                if video_pct >= 100 or is_video_only(username):
                    continue                           # nothing else to take from this one
            elif video_pct >= 100:
                print("No videos here; skipped.")
                continue
        try:
            pool = get_pool(username, max_scrolls, refresh, full, cache_hours, find,
                            max(top, -(-count // len(usernames)) if even else count), worst,
                            not include_videos, tags, min_conf, expand)
        except ScrapeError as e:                       # one bad account shouldn't stop the rest
            print(f"Error: {e}", file=sys.stderr)
            failed = True
            continue
        except PlaywrightError as e:
            print(f"Browser error: {e}", file=sys.stderr)
            failed = True
            continue

        vids = ATTACHED_VIDEOS.pop(username, [])
        if video_pct is not None:
            photos_mix[username] = [(sc, p) for sc, p in pool if not is_video_post(username, p)]
        elif even:
            pools += [(score, username, path) for score, path in pool]
            if vids:
                vids_by_user[username] = list(vids)
        elif combine:
            pools += [(score, username, path) for score, path in pool + vids]
        else:
            # sample() picks distinct posts; with --find the pool is that account's top matches.
            if all_posts:                              # every post in the pool, best first (or shuffled)
                ordered = sorted(pool, reverse=True) if (find or tags) else random.sample(pool, len(pool))
                ordered += vids
                chosen = ordered[:limit] if limit else ordered
            else:
                chosen = pick_mixed(pool, vids, min(count * spare, len(pool) + len(vids)))
            groups.append(([(username, path, score if (find or tags) and not is_video_post(username, path) else None) for score, path in chosen],
                           len(chosen) if all_posts else count))
        if _network_calls > before and n < len(usernames) - 1:
            time.sleep(random.uniform(3, 6))           # breathe between accounts that hit Instagram

    if video_pct is not None:
        k = round(count * video_pct / 100)
        if k and not mix_vids:
            print("No videos in the accounts you picked; showing photos only.")
            k = 0
        by_user = {u: list(pl) for u, pl in photos_mix.items() if pl}
        ph = even_pick(by_user, count - k) if count - k > 0 else []
        vp = video_segments(mix_vids, k) if k else []
        items = [(u, p, sc if (find or tags) else None) for sc, u, p in ph] + [(u, p, None) for u, p in vp]
        random.shuffle(items)
        print(f"Mix: {len(vp)} video segment(s) from {len(mix_vids)} video(s), {len(ph)} photo(s).")
        groups = [(items, len(items))] if items else []
    elif even and (pools or vids_by_user) and not all_posts:
        by_user: dict = {u: [] for u in vids_by_user}
        for sc, u, pth in pools:
            by_user.setdefault(u, []).append((sc, pth))
        main = even_pick(by_user, count, vids_by_user)
        extra = even_pick(by_user, count * (spare - 1), vids_by_user) if spare > 1 else []
        groups = [([(u, pth, sc if (find or tags) and not is_video_post(u, pth) else None) for sc, u, pth in main + extra], count)]
        print(f"Spread evenly over {len(by_user)} account(s): "
              + ", ".join(f"{u} {sum(1 for _, x, _ in main if x == u)}" for u in by_user))
    elif combine and pools:
        if find or tags:
            pools = sorted(pools, reverse=True)                      # best matches across all accounts
            if not all_posts:
                pools = pools[-max(top, count):] if worst else pools[:max(top, count)]
        if all_posts:
            ordered = pools if (find or tags) else random.sample(pools, len(pools))
            chosen = ordered[:limit] if limit else ordered
        else:
            chosen = random.sample(pools, min(count * spare, len(pools)))
        groups = [([(u, p, sc if (find or tags) and not is_video_post(u, p) else None) for sc, u, p in chosen],
                   len(chosen) if all_posts else count)]

    if not groups:
        return False

    if all_posts:
        print(f"\nTaking every matching post: {sum(len(c) for c, _ in groups)} in total.")
        if open_browser and not save_dir:
            print("(Not opening that many browser tabs; the links are listed below.)")
            open_browser = False
    if not save_dir:
        print("\nRandom posts:" if not all_posts else "\nPosts:")
        for candidates, want in groups:
            for username, path, score in candidates[:want]:
                print(f"  [{username}] {BASE + base_post(path)}"
                      + (f"  (slide {slide_no(path)})" if is_slide(path) else "")
                      + (f"  score {score:.3f}" if score is not None else ""))
                if open_browser:
                    webbrowser.open_new_tab(BASE + base_post(path))
                    time.sleep(0.5)  # small gap so the browser opens every tab reliably
    else:
        print(f"\nSaving photos to {save_dir}/ ...")
        scorer = make_scorer(find) if (all_slides and find) else None
        files = save_images(groups, Path(save_dir), scorer, all_slides, slide_margin)
        print(f"Saved {len(files)} image(s).")
        if open_browser and files:
            webbrowser.open(Path(save_dir).resolve().as_uri())  # reveal the folder
    return not failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Open random posts from one or more Instagram profiles")
    parser.add_argument("usernames", nargs="*", metavar="username",
                        help="one or more Instagram usernames (without @), processed in order")
    parser.add_argument("--fetch", nargs="+", metavar="POST_URL",
                        help="just save the full-size photos of these Instagram post URLs into "
                             "--save FOLDER (default: picks), then exit")
    parser.add_argument("--max-scrolls", type=int, default=200,
                        help="safety cap on scroll steps (default: 200)")
    parser.add_argument("--count", type=int, default=5,
                        help="how many random posts to pick per account, or in total with --combine (default: 5)")
    parser.add_argument("--import-many", metavar="JSON_FILE",
                        help="import the photos of several folders, listed in a JSON file as [[name, folder], ...]")
    parser.add_argument("--import-new", action="store_true",
                        help="import files added to already-imported folders since last time (for the "
                             "collections named, or all of them)")
    parser.add_argument("--video-mix", type=int, default=None, metavar="PERCENT",
                        help="what share (0-100) of the --count results, in total, are video segments: 0 = photos "
                             "only, 100 = videos only. With fewer videos than needed, videos repeat with different "
                             "segments. Photos are spread evenly over the accounts.")
    parser.add_argument("--mix-videos", action="store_true",
                        help="with a search or tags, still mix in random videos from watched video folders")
    parser.add_argument("--clip-seconds", type=int, default=None, metavar="N",
                        help="length of the clips saved from imported videos, in seconds; 0 = the whole "
                             "video (default: 15)")
    parser.add_argument("--after", metavar="DATE",
                        help="only posts from this date on, e.g. 2022 or 2022-03-15 (dated from the post code; "
                             "imported images have no date and are left out)")
    parser.add_argument("--before", metavar="DATE",
                        help="only posts before this date, e.g. 2024 or 2024-06-01")
    parser.add_argument("--even", action="store_true",
                        help="take --count posts IN TOTAL, the same number from each account, mixed in random order")
    parser.add_argument("--combine", action="store_true",
                        help="pool all accounts together and pick --count posts overall")
    parser.add_argument("--refresh", action="store_true",
                        help="fetch only posts newer than the cache and add them to it")
    parser.add_argument("--full", action="store_true",
                        help="ignore the cache and rescrape the whole profile")
    parser.add_argument("--cache-hours", type=float, default=float("inf"),
                        help="expire the cache after this many hours (default: never; use --refresh)")
    parser.add_argument("--find", metavar="QUERY",
                        help='only pick posts whose photo matches this description, e.g. "a dog on a beach"')
    parser.add_argument("--like", metavar="IMAGE",
                        help="search by reference image: a file path, an image URL or an Instagram "
                             "post URL. Can be combined with --find.")
    parser.add_argument("--like-weight", type=float, default=0.5,
                        help="with --like and --find: how much the image counts vs the text, "
                             "0-1 (default: 0.5)")
    parser.add_argument("--pose", metavar="IMAGE",
                        help="match the BODY POSE of a reference photo (file, image URL or Instagram "
                             "post URL). Combine with --find/--like to also require a scene.")
    parser.add_argument("--no-mirror", action="store_true",
                        help="with --pose: don't treat a left-right flipped pose as a match")
    parser.add_argument("--scene-top", type=float, default=30,
                        help="with --pose and --find/--like: only rank posts in the best N%% for "
                             "the scene (default: 30)")
    parser.add_argument("--tag", action="append", metavar="TAG",
                        help="only posts with this tag, e.g. --tag beach --tag bikini --tag standing "
                             "(repeat for several; all must match). See --list-tags.")
    parser.add_argument("--min-conf", type=float, default=0.5,
                        help="with --tag: how confident a scene/outfit/shot tag must be, 0-1 (default: 0.5)")
    parser.add_argument("--list-tags", action="store_true",
                        help="show the tags and how many posts carry each, then exit")
    parser.add_argument("--json", action="store_true", help="with --list-tags: machine-readable output")
    parser.add_argument("--import-folder", metavar="FOLDER",
                        help="import the images in FOLDER as a collection named by the (single) "
                             "username argument, then exit")
    parser.add_argument("--frame-every", type=int, default=None, metavar="SECONDS",
                        help="with --import-videos: seconds between the sampled frames (default: 2). A larger "
                             "number indexes faster and uses less disk, but can miss short moments.")
    parser.add_argument("--index-videos-many", metavar="JSON_FILE",
                        help="make the videos of several folders searchable, listed in a JSON file as "
                             "[[name, folder], ...]; use --frame-every to set the spacing")
    parser.add_argument("--import-videos", metavar="FOLDER_OR_FILE",
                        help="import the videos in FOLDER_OR_FILE into the (single) collection named by "
                             "the username argument: a searchable frame every 2 seconds, clips on demand")
    parser.add_argument("--model", choices=list(MODELS), default=None,
                        help="photo-search model: siglip (default) or clip. Each has its own index.")
    parser.add_argument("--convert-all", action="store_true",
                        help="build the active model's index for every account that lacks it, then exit")
    parser.add_argument("--shrink-saved", action="store_true",
                        help="recompress the saved thumbnails/slides to about 1080 x 1350 px to free "
                             "disk space (one way), then exit")
    parser.add_argument("--build-library", action="store_true",
                        help="(re)build library/<account>/: browsable folders of the saved thumbnails "
                             "sorted by setting, outfit, shot and pose, then exit")
    parser.add_argument("--prepare", action="store_true",
                        help="do ALL the one-off setup for the account(s) now: photo index, pose index, "
                             "post types and thumbnails (add --expand-carousels N to also look inside "
                             "N carousels), then exit")
    parser.add_argument("--accounts-file", metavar="FILE",
                        help="read account names from a text file (one per line, or separated by spaces or "
                             "commas) and add them to the usernames given; handy with --prepare")
    parser.add_argument("--account-gap", type=float, nargs=2, default=(60, 180), metavar=("MIN", "MAX"),
                        help="with --prepare and several accounts: rest this many seconds (random between MIN "
                             "and MAX) after each account that used Instagram (default: 60 180)")
    parser.add_argument("--build-pose", action="store_true",
                        help="build the pose index for the account(s), then exit")
    parser.add_argument("--expand-carousels", type=int, default=0, metavar="N",
                        help="with a search or tags: look inside the N best-ranked carousels (their "
                             "first image ranked well) and search all their photos. Needs "
                             "--detect-carousels once per account.")
    parser.add_argument("--workers", type=int, default=1, choices=[1, 2, 3],
                        help="with --prepare and carousel indexing: browser windows working side by "
                             "side on the same login (default 1; more is faster but sends Instagram "
                             "proportionally more requests)")
    parser.add_argument("--expand-all", action="store_true",
                        help="with --prepare: look inside EVERY remaining post for more photos "
                             "(resumable; use --expand-carousels N instead to do N at a time)")
    parser.add_argument("--detect-carousels", action="store_true",
                        help="read the profile once to record which posts are carousels, then exit")
    parser.add_argument("--all", action="store_true",
                        help="take EVERY post matching the tags/search instead of --count random ones")
    parser.add_argument("--limit", type=int, default=0,
                        help="with --all: stop after this many posts (0 = no limit)")
    parser.add_argument("--top", type=int, default=50,
                        help="with --find: choose randomly among the N best matches (default: 50)")
    parser.add_argument("--all-slides", action="store_true",
                        help="with --save: also save the other photos in carousels (with --find, "
                             "only slides that still match the query)")
    parser.add_argument("--slide-margin", type=float, default=None,
                        help="with --all-slides and a search: keep slides scoring within this of the "
                             "first slide (default: 0.03 for text, 0.08 for --like; smaller = stricter)")
    parser.add_argument("--include-videos", action="store_true",
                        help="also allow reels/videos (by default only photo posts are picked)")
    parser.add_argument("--worst", action="store_true",
                        help="with a search: pick from the WORST matches instead (to test the search)")
    parser.add_argument("--save", nargs="?", const="picks", metavar="FOLDER",
                        help="save the picked images to FOLDER (default: picks) instead of opening tabs")
    parser.add_argument("--no-open", action="store_true",
                        help="don't open tabs (or the folder, with --save)")
    args = parser.parse_args()

    if args.fetch:
        items = []
        for url in args.fetch:
            m = re.match(r"https?://(?:www\.)?instagram\.com/(?:([\w.]+)/)?(p|reel|reels)/([\w-]+)", url)
            if m:
                items.append(((m.group(1) or "unknown").lower(), f"/{m.group(2)}/{m.group(3)}/", None))
            else:
                print(f"Skipping '{url}': not an Instagram post link.")
        try:
            files = save_images([(items, len(items))], Path(args.save or "picks")) if items else []
        except (ScrapeError, PlaywrightError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(f"Saved {len(files)} image(s).")
        return 0 if files else 1
    if args.model:
        set_model(args.model)
    if args.import_many:
        import_many(args.import_many)
        return 0
    if args.index_videos_many:
        if args.frame_every:
            set_frame_every(args.frame_every)
        index_videos_many(args.index_videos_many)
        return 0
    if args.import_new:
        try:
            import_new([u.lower() for u in args.usernames] or None)
        except ScrapeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        return 0
    if args.import_videos:
        if len(args.usernames) != 1:
            parser.error("give exactly one collection name, e.g.  random_post.py paigeinsco --import-videos ~/Movies/x")
        if args.frame_every:
            set_frame_every(args.frame_every)
        try:
            import_videos(args.import_videos, args.usernames[0])
        except ScrapeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        return 0
    if args.import_folder:
        if len(args.usernames) != 1:
            parser.error("give exactly one collection name, e.g.  random_post.py mypics --import-folder ~/Pictures/x")
        try:
            import_folder(args.import_folder, args.usernames[0])
        except ScrapeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        return 0
    if args.convert_all:
        accounts = sorted({f.name.split(".")[0] for k in MODELS for f in CACHE_DIR.glob(f"*.{MODELS[k]['file']}.npz")})
        for u in accounts:
            if not index_file(u).exists():
                convert_index(u)
        print(f"Done. Every account now has a {ACTIVE_MODEL} index.")
        return 0
    if args.shrink_saved:
        shrink_saved_images()
        return 0
    if not args.usernames and not args.accounts_file:
        parser.error("give at least one username (or --accounts-file)")
    query = Query(args.find, args.like, min(1.0, max(0.0, args.like_weight)), args.pose,
                  not args.no_mirror, min(100.0, max(1.0, args.scene_top)) / 100) \
        if (args.find or args.like or args.pose) else None
    margin = args.slide_margin if args.slide_margin is not None else (
        0.10 if args.pose else 0.08 if args.like else (0.012 if ACTIVE_MODEL == "siglip" else 0.03))
    raw = list(args.usernames)
    if args.accounts_file:
        try:
            text = re.sub(r"#[^\n]*", "", Path(args.accounts_file).expanduser().read_text())   # # starts a comment
            raw += re.split(r"[\s,]+", text)
        except OSError as e:
            parser.error(f"can't read {args.accounts_file}: {e}")
    usernames = list(dict.fromkeys(                     # clean up + drop duplicates, keep order
        u.strip().lstrip("@").strip("/").lower() for u in raw if u.strip() and not u.strip().startswith("#")))
    try:
        if args.list_tags:
            for u in usernames:
                list_tags(u, args.min_conf, args.max_scrolls, args.json)
            return 0
        if args.detect_carousels:
            for u in usernames:
                print(f"\n=== {u} ===")
                fetch_links(u, args.max_scrolls)
                kinds = load_kinds(u)
                print(f"{u}: {sum(1 for k in kinds.values() if k == 'carousel')} carousels among "
                      f"{len(kinds)} posts.")
            return 0
        if args.build_library:
            for u in usernames:
                build_library(u, args.min_conf, args.max_scrolls)
            return 0
        if args.prepare:
            done, failed_accounts = [], []
            for n, u in enumerate(usernames):
                before = _network_calls
                if len(usernames) > 1:
                    print(f"\n##### Account {n + 1} of {len(usernames)}: {u} #####")
                try:
                    prepare_account(u, args.max_scrolls,
                                    10 ** 6 if args.expand_all else max(0, args.expand_carousels),
                                    args.workers)
                    done.append(u)
                except (ScrapeError, PlaywrightError) as e:      # one bad account must not stop the batch
                    print(f"Error with {u}: {e}", file=sys.stderr)
                    failed_accounts.append(u)
                if _network_calls > before and n < len(usernames) - 1:
                    pause = random.uniform(*args.account_gap)
                    print(f"Resting {int(pause)} s before the next account (keeps Instagram happy)...")
                    time.sleep(pause)
            if len(usernames) > 1:
                print(f"\nBatch finished: {len(done)} ready, {len(failed_accounts)} failed"
                      + (f" ({', '.join(failed_accounts)})" if failed_accounts else "") + ".")
            return 1 if failed_accounts and not done else 0
        if args.build_pose:
            for u in usernames:
                ensure_indexes(u, True, args.max_scrolls, False, False)
                print(f"{u}: pose index ready.")
            return 0
        if args.mix_videos or args.video_mix is not None:
            global MIX_VIDEOS
            MIX_VIDEOS = True
        if args.video_mix is not None:
            args.video_mix = max(0, min(100, args.video_mix))
        if args.clip_seconds is not None:
            global CLIP_SECONDS
            CLIP_SECONDS = max(0, args.clip_seconds)
        set_date_range(args.after, args.before)
        if args.after or args.before:
            print(f"Dates: {args.after or 'the start'} to {args.before or 'now'}")
        tags = parse_tags(args.tag)
        if tags:
            print("Tags: " + ", ".join(f"{f}:{l}" for f, l in tags))
        if query:
            print(f"Searching for: {query}")
            query.prepare()      # validate the references up front (before any scraping)
        ok = run(usernames, args.max_scrolls, not args.no_open, max(1, args.count),
                 args.refresh, args.full, args.cache_hours, query, max(1, args.top),
                 args.save, args.combine, args.worst, args.include_videos,
                 args.all_slides, margin, tags, args.min_conf, args.all, max(0, args.limit),
                 max(0, args.expand_carousels), args.even and len(usernames) > 1,
                 args.video_mix)
        return 0 if ok else 1
    except ScrapeError as e:
        print(f"Error: {e}", file=sys.stderr)
    except PlaywrightError as e:
        print(f"Browser error: {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
