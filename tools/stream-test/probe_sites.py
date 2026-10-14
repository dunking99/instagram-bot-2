#!/usr/bin/env python3
"""Which Video Finder sites can Stream test really stream? One real video page per site, one frame each. Changes nothing.

    cd ~/instagram-bot-2/tools/stream-test
    /opt/homebrew/bin/python3 probe_sites.py            # test the videos found in your saved Video Finder searches
    /opt/homebrew/bin/python3 probe_sites.py LINK ...   # also test these video page links

For every site it asks Stream test (the same code the page uses) to read the video page, then takes ONE frame with
ffmpeg from the lowest quality, the same way "Get frames" does. When no video file can be read it looks for an HLS
playlist (.m3u8) on the page and tries one frame from that too. Sites Stream test lists as "not streamable", or does
not list at all, are tried anyway so the result shows whether they could be added.

Writes probe_results.txt and probe_results.json next to this file (addresses are cut before the "?" because they are
signed). About 2 requests per site, 2 seconds apart.
"""
import importlib.util
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import server as st                                   # Stream test's own code: the same readers and the same ffmpeg call

_spec = importlib.util.spec_from_file_location("vf_sites", HERE.parent / "video-finder" / "sites.py")
vf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vf)

JOBS_DIR = Path(os.environ.get("PROBE_JOBS") or HERE.parent / "video-finder" / "data" / "jobs")
OUT = HERE / "probe_results"
FRAMES = HERE / "probe_frames"
PER_SITE = 2                                          # videos tried per site
EXTRA = [                                             # sites that may have no saved search yet
    "https://www.playvids.com/XV84IVJOs08/bjraw-sera-ryder-and-millie-morgan-nbq-nice-tits-wet-pussy",
    "https://www.pornwex.tv/video/365834/sera-ryder-and-millie-morgan-bjraw/",
    "https://porneec.com/bjraw-sera-ryder-millie-morgan-millie-sera-share-the/",
]


def host_of(url):
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def clean(url):
    p = urllib.parse.urlsplit(url)
    return "%s://%s%s" % (p.scheme, p.netloc, p.path)


HOSTS = {host_of(spec["home"]): name for name, spec in vf.SITES.items()}


def collect(extra):
    """{host: [video page links]} from the saved searches (best-ranked results first), newest search first."""
    found = {}

    def add(url):
        h = host_of(url)
        if h in HOSTS and url not in found.setdefault(h, []) and len(found[h]) < PER_SITE:
            found[h].append(url)

    files = sorted(JOBS_DIR.glob("*.json"), reverse=True) if JOBS_DIR.exists() else []
    for f in files:
        try:
            job = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        for sd in (job.get("sites") or {}).values():
            for c in ((sd.get("results") or {}).get("ranked") or [])[:2]:
                add(c.get("url") or "")
    for f in files:                                   # sites that never ranked: any card will do
        try:
            job = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        for sd in (job.get("sites") or {}).values():
            for q in sd.get("queries") or []:
                for c in (q.get("cards") or [])[:3]:
                    add(c.get("url") or "")
    for u in list(EXTRA) + list(extra):
        add(u)
    return found


def find_hls(page_url):
    """First .m3u8 address on the page (or None)."""
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": st.UA, "Accept-Language": "en"})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", "replace").replace("\\/", "/").replace("&amp;", "&")
    except Exception:
        return None
    m = re.search(r"https?://[^\"'\s<>\\]+\.m3u8[^\"'\s<>\\]*", text)
    return m.group(0) if m else None


def one_frame(site, final, sec, headers):
    """Take one frame with Stream test's own ffmpeg call. -> (ok, seconds, last error)"""
    d = FRAMES / site
    d.mkdir(parents=True, exist_ok=True)
    job = dict(dir=d, headers=headers or {}, cancel=False, done=0, failed=0, files=[], last_error="", site=site)
    t0 = time.time()
    st.grab(job, final, sec, 224)
    return job["done"] == 1, round(time.time() - t0, 1), job["last_error"]


def probe(url):
    site = st.site_of(url)
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    row = dict(host=host, page=clean(url), stream_test="listed")
    if site in st.NOT_STREAMABLE:                     # tried anyway: the point is to see whether it could be added
        row["stream_test"] = "marked not streamable: " + st.NOT_STREAMABLE.pop(site)
        st.SITES[site] = None
    elif site is None:
        row["stream_test"] = "not listed"
        st.SITES[host] = None
    t0 = time.time()
    try:
        info = st.fetch_info(url)
    except Exception as e:
        row.update(read="failed", error=str(e)[:220])
        hls = find_hls(url)
        if hls:
            row["hls"] = clean(hls)
            try:
                ok, secs, err = one_frame(host, hls, 60, {"Referer": url})
                row.update(hls_frame_ok=ok, hls_frame_seconds=secs, hls_frame_error=err)
            except Exception as e2:
                row.update(hls_frame_ok=False, hls_frame_error=str(e2)[:160])
        row["seconds"] = round(time.time() - t0, 1)
        return row
    srcs = info["sources"]
    row.update(read="ok", read_with=info.get("read_with"), qualities=[s["label"] for s in srcs], duration=info.get("duration"),
               preview_frames=info.get("frames") or 0, needs_proxy=any(s.get("needs_proxy") for s in srcs))
    dur = info.get("duration") or 0
    sec = int(min(dur * 0.3, dur - 5)) if dur > 60 else 60
    try:
        src = srcs[0]
        final = st.resolve_final(src["url"])
        ok, secs, err = one_frame(host, final, sec, st.ISSUED.get(src["url"]) or {})
        row.update(frame_ok=ok, frame_seconds=secs, frame_error=err)
    except Exception as e:
        row.update(frame_ok=False, frame_error=str(e)[:160])
    row["seconds"] = round(time.time() - t0, 1)
    return row


def verdict(r):
    if r.get("frame_ok"):
        return "WORKS"
    if r.get("hls_frame_ok"):
        return "HLS only (frames work)"
    if r.get("hls"):
        return "HLS (frame failed)"
    if r.get("read") == "ok":
        return "read ok, frame failed"
    return "no video file"


def main():
    extra = [a for a in sys.argv[1:] if a.startswith("http")]
    if not os.path.exists(st.FFMPEG):
        print("ffmpeg not found at %s (brew install ffmpeg)" % st.FFMPEG)
    todo = collect(extra)
    n = sum(len(v) for v in todo.values())
    print("%d video pages on %d sites (saved searches: %s)\n" % (n, len(todo), JOBS_DIR))
    missing = sorted(h for h in HOSTS if h not in todo)
    if missing:
        print("No video page known for: %s\n(add a link from each as an extra argument to test it too)\n" % ", ".join(missing))
    rows = []
    for host, urls in sorted(todo.items()):
        for u in urls:
            print("testing %-24s %s" % (host, clean(u)[:90]), flush=True)
            r = probe(u)
            rows.append(r)
            print("   -> %s %s\n" % (verdict(r), (r.get("error") or r.get("frame_error") or "")[:110]), flush=True)
            time.sleep(2)
    lines = ["%-22s %-26s %-20s %-18s %s" % ("site", "result", "read with", "qualities", "notes")]
    for r in rows:
        notes = r.get("error") or r.get("frame_error") or ""
        if r.get("preview_frames"):
            notes = ("%d preview frames on the page; " % r["preview_frames"]) + notes
        if r.get("stream_test") != "listed":
            notes = r["stream_test"][:60] + "; " + notes
        lines.append("%-22s %-26s %-20s %-18s %s" % (r["host"], verdict(r), r.get("read_with") or "-", ",".join(r.get("qualities") or [])[:18] or "-", notes[:160]))
    text = "\n".join(lines)
    print(text)
    (OUT.with_suffix(".txt")).write_text(text + "\n")
    (OUT.with_suffix(".json")).write_text(json.dumps(rows, indent=1))
    print("\nWritten: %s.txt and .json" % OUT)


if __name__ == "__main__":
    main()
