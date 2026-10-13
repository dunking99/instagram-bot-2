"""
Sort and crop screenshots from the macOS Photos library (read-only).

Your Photos library is never modified. The script only READS the preview images that Photos keeps
on this Mac (resources/derivatives) and the library database (opened read-only), and writes its
own results into pilot/.

For each screenshot it
  1. finds the photo inside the screenshot (cuts off the status bar, post header, like bar...),
  2. decides whether it is a photo of a person (keep), something else such as a receipt or an app
     screen (junk), or unsure (review).

Run a pilot on a random sample:
    python3 photos_import.py --pilot 400
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

LIBRARY = Path.home() / "Pictures" / "Photos Library.photoslibrary"
PILOT_DIR = Path(__file__).with_name("pilot")
APPLE_EPOCH = 978307200                      # Photos stores dates as seconds since 2001-01-01
CROP_SIDE = 640                              # size of the saved crops (longest side)

# What CLIP is asked about each screenshot. Probabilities are shared out across ALL of these, and
# the "keep" ones are added up.
KEEP_PROMPTS = [
    "a photo of a woman",
    "a photo of a person posing",
    "a fashion photo of a person",
    "a portrait photo of a person",
    "a selfie",
    "a photo of a person at the beach",
    "a photo of a person in a city",
    "a photo of a group of friends",
]
JUNK_PROMPTS = [
    "a screenshot of a receipt",
    "a screenshot of a text message conversation",
    "a screenshot of a phone settings screen",
    "a screenshot of an app with menus and buttons",
    "a screenshot of a website or article with text",
    "a screenshot of a map",
    "a screenshot of a document or a form",
    "a screenshot of a spreadsheet or a table",
    "a screenshot of a video game",
    "a meme with text over a picture",
    "a photo of food on a plate",
    "a photo of a product for sale",
    "a photo of a dog or a cat",
    "a photo of a landscape with no people",
    "a graph or a chart",
    "a screenshot of a QR code or a ticket",
]


# --- Reading the library ------------------------------------------------------------------
def open_db() -> sqlite3.Connection:
    db = LIBRARY / "database" / "Photos.sqlite"
    if not db.exists():
        sys.exit(f"Can't find the Photos library at {LIBRARY}")
    # read-only and immutable: never takes locks, never writes
    return sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)


def load_screenshots() -> list[dict]:
    """Every non-hidden, non-trashed photo that Photos has flagged as a screenshot."""
    con = open_db()
    rows = con.execute("""
        SELECT a.ZUUID, aa.ZORIGINALFILENAME, a.ZDATECREATED, a.ZWIDTH, a.ZHEIGHT
        FROM ZASSET a LEFT JOIN ZADDITIONALASSETATTRIBUTES aa ON aa.ZASSET = a.Z_PK
        WHERE a.ZISDETECTEDSCREENSHOT = 1 AND a.ZKIND = 0 AND a.ZTRASHEDSTATE = 0 AND a.ZHIDDEN = 0
    """).fetchall()
    con.close()
    out = []
    for uuid, name, created, w, h in rows:
        date = time.strftime("%Y-%m-%d", time.gmtime(created + APPLE_EPOCH)) if created else ""
        out.append({"uuid": uuid, "filename": name or "", "date": date, "width": w, "height": h})
    return out


def preview_path(uuid: str) -> Path | None:
    """The biggest preview Photos keeps on this Mac for an item (it keeps the originals in iCloud)."""
    d = LIBRARY / "resources" / "derivatives"
    for p in (d / uuid[0] / f"{uuid}_1_105_c.jpeg", d / "masters" / uuid[0] / f"{uuid}_4_5005_c.jpeg"):
        if p.exists():
            return p
    return None


# --- Finding the photo inside a screenshot ------------------------------------------------
def find_photo_box(img) -> tuple[tuple[int, int, int, int], str]:
    """(left, top, right, bottom) of the photo inside a screenshot, and how it was found.

    Interface backgrounds are flat, a photo is full of detail. The photo is the tallest stretch of
    rows that is "busy" across most of the width, which skips the status bar, the post header
    (a small avatar and a name), and the like/comment bar underneath. If no such stretch exists
    (a very dark or very plain photo), it falls back to the screenshot minus its top and bottom edges.
    """
    import numpy as np
    w, h = img.size
    scale = 200 / w
    small = img.convert("RGB").resize((200, max(1, int(h * scale))))
    arr = np.asarray(small).astype("int16")
    H, W, _ = arr.shape
    # the interface background colour: what the top and bottom strips are mostly made of
    strips = np.concatenate([arr[:max(2, H // 40)].reshape(-1, 3), arr[-max(2, H // 40):].reshape(-1, 3)])
    bg = np.median(strips, axis=0)
    differs = (np.abs(arr - bg).sum(axis=2) > 60)
    b = 8
    rows, cols = H // b, W // b
    if rows < 6:
        return (0, 0, w, h), "whole image"
    blocks = differs[:rows * b, :cols * b].reshape(rows, b, cols, b).mean(axis=(1, 3))
    busy = blocks > 0.45
    frac = busy.mean(axis=1)                              # share of each block-row that is busy
    good = frac >= 0.5
    best, start = (0, 0), None
    gap = 0
    for r in range(rows):
        if good[r]:
            if start is None:
                start = r
            gap = 0
            end = r
        elif start is not None:
            gap += 1
            if gap > 2:
                if end - start > best[1] - best[0]:
                    best = (start, end)
                start = None
    if start is not None and end - start > best[1] - best[0]:
        best = (start, end)
    top, bottom = best
    if (bottom - top + 1) >= max(4, int(rows * 0.18)):
        cols_busy = busy[top:bottom + 1].mean(axis=0) >= 0.3
        xs = np.where(cols_busy)[0]
        left = int(xs[0]) * b if len(xs) else 0
        right = (int(xs[-1]) + 1) * b if len(xs) else W
        box = (left / scale, top * b / scale, right / scale, (bottom + 1) * b / scale)
        box = tuple(int(round(v)) for v in box)
        return (max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])), "detected"
    return (0, int(h * 0.07), w, int(h * 0.93)), "fallback"


# --- Sorting -------------------------------------------------------------------------------
def prompt_matrix():
    import numpy as np
    import random_post as rp
    prompts = KEEP_PROMPTS + JUNK_PROMPTS
    return prompts, np.stack([rp.embed_text(p) for p in prompts])


def keep_probability(vec, matrix, n_keep: int) -> tuple[float, int]:
    """(probability that this is a photo of a person, index of the best-matching prompt)."""
    import numpy as np
    import random_post as rp
    logits = rp.logit_scale() * (matrix @ vec)
    logits -= logits.max()
    p = np.exp(logits)
    p /= p.sum()
    return float(p[:n_keep].sum()), int(p.argmax())


def assign_pile(p_keep: float, body: bool, keep_at: float = 0.7, junk_at: float = 0.2) -> str:
    """keep / junk / review from the photo score and whether a body was found in the crop."""
    if p_keep >= 0.9 or (p_keep >= keep_at and body):
        return "keep"
    if p_keep <= junk_at and not body:
        return "junk"
    return "review"


def process(item: dict, matrix, prompts, crops_dir: Path) -> dict | None:
    from PIL import Image
    import random_post as rp
    src = preview_path(item["uuid"])
    if src is None:
        return None
    try:
        img = Image.open(src).convert("RGB")
    except OSError:
        return None
    box, how = find_photo_box(img)
    crop = img.crop(box)
    vec = rp.embed_image(crop)
    p_keep, best = keep_probability(vec, matrix, len(KEEP_PROMPTS))
    whole_p, _ = keep_probability(rp.embed_image(img), matrix, len(KEEP_PROMPTS))
    p_keep = max(p_keep, whole_p)              # a bad crop shouldn't hide a real photo
    found = rp.pose_landmarks(crop)
    body = bool(found) and int((found[1] > rp.VIS_MIN).sum()) >= 8
    thumb = crop.copy()
    thumb.thumbnail((CROP_SIDE, CROP_SIDE))
    thumb.save(crops_dir / f"{item['uuid']}.jpg", "JPEG", quality=82)
    return {**item, "preview": str(src), "box": list(box), "box_method": how,
            "p_keep": round(p_keep, 3), "p_keep_whole": round(whole_p, 3), "body": body,
            "best_prompt": prompts[best], "pile": assign_pile(p_keep, body)}


def run_pilot(n: int, seed: int = 1) -> None:
    items = load_screenshots()
    print(f"{len(items):,} screenshots in the library (hidden and trashed ones skipped).")
    random.Random(seed).shuffle(items)
    PILOT_DIR.mkdir(exist_ok=True)
    crops = PILOT_DIR / "crops"
    crops.mkdir(exist_ok=True)
    import random_post as rp
    print("Loading the models...")
    rp.load_clip()
    rp.get_pose_model()
    prompts, matrix = prompt_matrix()
    results, started = [], time.time()
    for item in items:
        if len(results) >= n:
            break
        r = process(item, matrix, prompts, crops)
        if r:
            results.append(r)
            if len(results) % 25 == 0:
                print(f"Progress: {len(results)} / {n} screenshots sorted "
                      f"(~{int((time.time() - started) / len(results) * (n - len(results)) / 60)} min left).")
    (PILOT_DIR / "results.json").write_text(json.dumps(results))
    piles = {k: sum(1 for r in results if r["pile"] == k) for k in ("keep", "review", "junk")}
    print(f"Done: {len(results)} sorted. keep {piles['keep']}, review {piles['review']}, junk {piles['junk']}.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sort and crop screenshots from the Photos library (read-only)")
    ap.add_argument("--pilot", type=int, metavar="N", help="sort a random sample of N screenshots")
    ap.add_argument("--seed", type=int, default=1, help="random seed for the sample (default 1)")
    args = ap.parse_args()
    if not args.pilot:
        ap.error("use --pilot N")
    run_pilot(args.pilot, args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
