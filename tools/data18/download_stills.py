#!/usr/bin/env python3
"""
Download a video's "Video Stills" as 000001.jpg, 000002.jpg, ...

  .venv/bin/python download_stills.py 1350614                       # -> ~/frames-test
  .venv/bin/python download_stills.py https://www.data18.com/scenes/1350614-dysfunctional-family-values-episode-9
  .venv/bin/python download_stills.py 1350614 --out ~/other-folder
  .venv/bin/python download_stills.py 1350614 --append              # keep numbering after the files already there
  .venv/bin/python download_stills.py 1350614 --all                 # every gallery (Primary, Photoset, Trailer...), not just stills

If a video has two sets of stills ("Video Stills 1" and "Video Stills 2") they are saved one after the other.
Needs the saved session (setup_session.py), same as the scraper.
"""
import argparse
import re
import sys
from pathlib import Path

import requests

import scraper

STILLS_RE = re.compile(r"^video\s?stills", re.I)     # "Video Stills", "Video Stills 1", "Videostills"


def scene_id_from(arg):
    m = re.search(r"/scenes/(\d+)", arg) or re.fullmatch(r"(\d+)", arg.strip())
    if not m:
        raise SystemExit(f"Can't find a scene number in {arg!r}. Use e.g. 1350614 or a https://www.data18.com/scenes/... link.")
    return m.group(1)


def next_number(out):
    nums = [int(p.stem) for p in out.glob("*.jpg") if p.stem.isdigit()]
    return max(nums, default=0) + 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", help="scene number or data18 scene link")
    ap.add_argument("--out", default="~/frames-test", help="folder to save into (default ~/frames-test)")
    ap.add_argument("--append", action="store_true", help="continue numbering after existing files instead of stopping")
    ap.add_argument("--all", action="store_true", help="download every gallery, not just Video Stills")
    args = ap.parse_args()

    sid = scene_id_from(args.video)
    out = Path(args.out).expanduser()
    existing = list(out.glob("*.jpg")) if out.exists() else []
    if existing and not args.append:
        raise SystemExit(f"{out} already has {len(existing)} .jpg files. Use --append to number after them, or choose another --out.")

    session = scraper.load_session()
    try:
        d = scraper.fetch_scene_details(session, sid, scraper.BASE + "/")
        if d is None:
            raise SystemExit("data18 didn't answer, try again in a moment.")
        galleries = scraper.scene_galleries(sid)
    except scraper.SessionError as e:
        raise SystemExit(str(e))
    if not galleries:
        raise SystemExit(f"Scene {sid} has no galleries.")

    chosen = [g for g in galleries if args.all or STILLS_RE.match(g["label"])]
    if not chosen:
        names = ", ".join(f"{g['label']} ({len(g['images'])})" for g in galleries)
        raise SystemExit(f"Scene {sid} has no Video Stills. It has: {names}. Use --all to download those instead.")

    out.mkdir(parents=True, exist_ok=True)
    n = next_number(out)
    first = n
    http = requests.Session()
    http.headers.update({"Referer": scraper.BASE + "/", "User-Agent": scraper.DEFAULT_UA})
    failed = []
    for g in chosen:
        print(f"{g['label']}: {len(g['images'])} images")
        for im in g["images"]:
            scraper._rate()
            try:
                r = http.get(im["f"], timeout=30)
            except requests.RequestException as e:
                failed.append((im["f"], str(e)))
                continue
            if r.status_code != 200 or not r.content.startswith(b"\xff\xd8"):    # JPEG files start with FF D8
                failed.append((im["f"], f"HTTP {r.status_code}" if r.status_code != 200 else "not a JPEG"))
                continue
            (out / f"{n:06d}.jpg").write_bytes(r.content)
            n += 1
    saved = n - first
    print(f"Saved {saved} images to {out}  ({first:06d}.jpg to {n - 1:06d}.jpg)" if saved else "Nothing saved.")
    for url, why in failed:
        print(f"  FAILED {why}: {url}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
