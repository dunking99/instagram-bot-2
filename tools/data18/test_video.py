#!/usr/bin/env python3
"""
Run the position model on one data18 video's stills and photosets, kept separate.

  .venv/bin/python test_video.py 1350614
  .venv/bin/python test_video.py https://www.data18.com/scenes/1350614-... [--out ~/data18-test] [--unsure-below 0.5]

Downloads each gallery into <out>/<scene>/stills/ and <out>/<scene>/photosets/ (numbered files + manifest.csv with the source URLs), then
runs the model in ITS OWN environment (a subprocess, nothing is imported from it) and prints a summary per gallery type.
Skips Primary and Trailer. Needs the saved session (setup_session.py). Polite: uses the scraper's own rate limit.
"""
import argparse, csv, re, subprocess, sys
from collections import Counter
from pathlib import Path
import requests
import scraper

MODEL_PY = Path(__file__).resolve().parents[2] / "CLIP Training/.venv/bin/python"
MODEL_SCRIPT = str(Path(__file__).resolve().parents[2] / "CLIP Training/scripts/classify_images.py")
kind = lambda label: "stills" if re.match(r"^video\s?stills", label, re.I) else "photosets" if re.match(r"^photoset", label, re.I) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("--out", default="~/data18-test"); ap.add_argument("--unsure-below", default="0.5")
    ap.add_argument("--max", type=int, default=0, help="only the first N images of each type (0 = all)")
    a = ap.parse_args()
    m = re.search(r"/scenes/(\d+)", a.video) or re.fullmatch(r"(\d+)", a.video.strip())
    if not m: sys.exit("Give a scene number or a data18 /scenes/ link.")
    sid = m.group(1); root = Path(a.out).expanduser() / sid
    session = scraper.load_session()
    try:
        if scraper.fetch_scene_details(session, sid, scraper.BASE + "/") is None: sys.exit("data18 didn't answer, try again.")
        galleries = scraper.scene_galleries(sid)
    except scraper.SessionError as e:
        sys.exit(str(e))
    by = {"stills": [], "photosets": []}
    for g in galleries or []:
        k = kind(g["label"])
        if k: by[k] += [(g["label"], im["f"]) for im in g["images"]]
    print("galleries:", ", ".join(f"{g['label']} ({len(g['images'])})" for g in galleries or []) or "none")
    http = requests.Session(); http.headers.update({"Referer": scraper.BASE + "/", "User-Agent": scraper.DEFAULT_UA})
    summary = {}
    for k, items in by.items():
        items = items[:a.max] if a.max else items
        if not items: print(f"\n{k}: none"); continue
        d = root / k
        if d.exists() and any(d.iterdir()): print(f"\n{k}: {d} already has files, reusing them (delete the folder to redo)")
        else:
            d.mkdir(parents=True, exist_ok=True); rows = []
            for n, (label, url) in enumerate(items, 1):
                scraper._rate()
                try: r = http.get(url, timeout=30)
                except requests.RequestException: continue
                if r.status_code != 200 or not r.content.startswith(b"\xff\xd8"): continue
                (d / f"{n:06d}.jpg").write_bytes(r.content); rows.append([f"{n:06d}.jpg", label, url])
            with open(d / "manifest.csv", "w", newline="") as fh: csv.writer(fh).writerows([["file", "gallery", "url"]] + rows)
            print(f"\n{k}: downloaded {len(rows)} of {len(items)}")
        res = root / f"{k}_predictions.csv"
        r = subprocess.run([str(MODEL_PY), MODEL_SCRIPT, str(d), "--unsure-below", a.unsure_below, "--csv", str(res)], capture_output=True, text=True)
        if r.returncode: print("model failed:\n", r.stderr[-800:]); continue
        with open(res, newline="") as fh: summary[k] = [row["answer"] for row in csv.DictReader(fh)]
    print("\n=== summary (the model judged each image on its own) ===")
    for k, ans in summary.items():
        c = Counter(ans); print(f"{k}: {len(ans)} images, Unsure {c['Unsure'] / len(ans):.0%}")
        for lab, n in c.most_common(): print(f"   {lab:16s} {n:3d}  {n / len(ans):.0%}")
    print(f"\nimages and per-image results (top 3 guesses with confidence): {root}")


if __name__ == "__main__":
    main()
