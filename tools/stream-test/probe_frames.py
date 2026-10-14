#!/usr/bin/env python3
"""Which sites hand out video frames for free (like freepornvideos' 100 numbered previews)? Changes nothing.

    cd ~/instagram-bot-2/tools/stream-test
    /opt/homebrew/bin/python3 probe_frames.py            # every site, one video page each
    /opt/homebrew/bin/python3 probe_frames.py LINK ...   # also these video pages

For each site it reads one video page and looks for frames that need no video streaming:
  - numbered images in the video's own folder (1.jpg, 2.jpg ... ): it COUNTS how many really exist (doubling, then bisecting)
  - storyboard / mosaic sheets (a "#" or "{n}" in the address): how many sheets, how big
  - WebVTT thumbnail tracks (.vtt with #xywh=): how many cues = frames, and how far apart
  - HLS playlists with an I-frame or image stream
  - short preview videos (noted only)
and saves the first and last frame it finds into frames_probe_samples/ (local only) so you can look at them.
About 20-30 requests per site, one second apart. Writes frames_probe_results.txt and .json (addresses cut before the "?").
"""
import json
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import play_test as pt                     # its page picker for each site (stdlib only until a browser is started)
import server as st                        # page_duration()

UA = pt.UA
SAMPLES = HERE / "frames_probe_samples"
OUT = HERE / "frames_probe_results"
MAXN = 400                                 # never test beyond this many numbered frames
SITES = pt.ALL_SITES + ["porngrey.net", "shyfap.net"]
pt.EXTRA += ["https://www.porngrey.net/video/babi-s-first-shoot-ever_v1/", "https://www.shyfap.net/video/show-us-your-cock_v1/"]
IMG = re.compile(r"""https?://[^"'\s<>\\)]+?\.(?:jpe?g|png|webp)(?:\?[^"'\s<>\\)]*)?""", re.I)


def clean(url):
    p = urllib.parse.urlsplit(url)
    return "%s://%s%s" % (p.scheme, p.netloc, p.path)


def fetch(url, referer=None, rng=None, limit=None, timeout=25):
    h = {"User-Agent": UA, "Accept-Language": "en"}
    if referer:
        h["Referer"] = referer
    if rng:
        h["Range"] = rng
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.status, (r.headers.get("Content-Type") or ""), (r.read(limit) if limit else r.read())


def exists(url, referer):
    """Is there an image at this address? HEAD first, then a 1-byte GET when HEAD is refused."""
    for method in ("HEAD", "GET"):
        try:
            h = {"User-Agent": UA, "Referer": referer}
            if method == "GET":
                h["Range"] = "bytes=0-0"
            with urllib.request.urlopen(urllib.request.Request(url, method=method, headers=h), timeout=20) as r:
                ct = (r.headers.get("Content-Type") or "").lower()
                return r.status in (200, 206) and ("image" in ct or "octet" in ct)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return False
        except Exception:
            return False
    return False


def last_existing(make, referer, first=1):
    """Largest n with an image at make(n), assuming n = first.. are all there (doubling, then bisecting). -> (first, last) or None"""
    if not exists(make(first), referer):
        return None
    lo, hi, step = first, None, 1
    while hi is None:
        probe = min(first + step, first + MAXN)
        if exists(make(probe), referer):
            lo = probe
            if probe >= first + MAXN:
                return first, lo
            step *= 2
        else:
            hi = probe
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if exists(make(mid), referer) else (lo, mid)
    return first, lo


def image_size(data):
    """(width, height) of a JPEG or PNG from its first bytes, or None."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except Exception:
        pass
    return None


def sample(url, referer, name):
    try:
        _, _, data = fetch(url, referer, limit=1_500_000)
        SAMPLES.mkdir(exist_ok=True)
        (SAMPLES / name).write_bytes(data)
        return image_size(data), len(data)
    except Exception:
        return None, 0


def own_dirs(text):
    """Folders of this video's own main picture (og:image, poster, JSON-LD thumbnail, preview_url): these are where its frames would be."""
    found = set()
    for pat in (r"""property=["']og:image["'][^>]*content=["']([^"']+)""", r"""content=["']([^"']+)["'][^>]*property=["']og:image""", r"""poster=["']([^"']+)""",
                r'"thumbnailUrl"\s*:\s*"([^"]+)"', r"""preview_url\d?\s*:\s*['"]([^'"]+)""", r"""data-folder=["']([^"']+)"""):
        for u in re.findall(pat, text):
            found.add(unescape(u).partition("?")[0].rsplit("/", 1)[0] + "/")
    return found


def analyse(page_url):
    """Everything free-frame-ish on one video page. -> dict"""
    res = dict(page=clean(page_url), frames=[], notes=[])
    status, _, raw = fetch(page_url)
    text = raw.decode("utf-8", "replace").replace("\\/", "/").replace("&amp;", "&")
    res["duration"] = st.page_duration(text)
    ids = re.findall(r"\d{5,}", urllib.parse.urlsplit(page_url).path)
    dirs = own_dirs(text)

    # 1. numbered images in the video's own folder
    groups = {}
    for u in set(IMG.findall(text)):
        m = re.match(r"^(.*/)(\d+)(_[a-z]+)?\.(jpe?g|png|webp)$", u.partition("?")[0], re.I)
        if m:
            groups.setdefault((m.group(1), m.group(3) or "", m.group(4)), set()).add(int(m.group(2)))
    for (d, suf, ext), nums in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if not (d in dirs or any(i in d for i in ids) or len(nums) >= 3):
            continue
        make = lambda n, d=d, suf=suf, ext=ext: "%s%d%s.%s" % (d, n, suf, ext)
        span = last_existing(make, page_url, 1) or (last_existing(make, page_url, min(nums)) if min(nums) != 1 else None)
        if span:
            a, b = span
            size, nbytes = sample(make(a), page_url, "%s_first.jpg" % re.sub(r"\W+", "_", urllib.parse.urlsplit(page_url).hostname))
            sample(make(b), page_url, "%s_last.jpg" % re.sub(r"\W+", "_", urllib.parse.urlsplit(page_url).hostname))
            res["frames"].append(dict(kind="numbered images", count=b - a + 1, size=size, bytes=nbytes, pattern=clean(make(a)).replace(str(a) + suf + "." + ext, "N" + suf + "." + ext)))
        else:
            res["notes"].append("folder %s has numbers %s on the page but no sequence from 1" % (d[-50:], sorted(nums)[:6]))

    # 2. storyboard / mosaic sheets: an address with a placeholder
    for tpl in set(re.findall(r"""https?://[^"'\s<>\\]*(?:#|\{n\}|%d|\$index\$)[^"'\s<>\\]*\.(?:jpe?g|png|webp)""", text)):
        make = lambda n, tpl=tpl: re.sub(r"#|\{n\}|%d|\$index\$", str(n), tpl, count=1)
        for first in (0, 1):
            span = last_existing(make, page_url, first)
            if span:
                size, nbytes = sample(make(span[0]), page_url, "%s_sheet.jpg" % re.sub(r"\W+", "_", urllib.parse.urlsplit(page_url).hostname))
                res["frames"].append(dict(kind="storyboard sheets", count=span[1] - span[0] + 1, size=size, bytes=nbytes, pattern=clean(tpl)))
                break

    # 3. WebVTT thumbnail tracks
    vtts = set(re.findall(r"https?://[^\"'\s<>\\]+\.vtt[^\"'\s<>\\]*", text))
    vtts |= {urllib.parse.urljoin(page_url, u) for u in re.findall(r"""["']([^"'\s]+\.vtt[^"'\s]*)["']""", text)}
    for v in list(vtts)[:3]:
        try:
            _, _, body = fetch(v, page_url, limit=400_000)
            body = body.decode("utf-8", "replace")
            cues = len(re.findall(r"-->", body))
            tiles = re.findall(r"#xywh=(\d+),(\d+),(\d+),(\d+)", body)
            ends = re.findall(r"-->\s*(\d+):(\d+):(\d+)", body)
            span = (int(ends[-1][0]) * 3600 + int(ends[-1][1]) * 60 + int(ends[-1][2])) if ends else None
            res["frames"].append(dict(kind="WebVTT thumbnails", count=cues, size=(int(tiles[0][2]), int(tiles[0][3])) if tiles else None, bytes=0, pattern=clean(v), covers_s=span))
        except Exception as e:
            res["notes"].append("vtt %s: %s" % (clean(v)[-40:], str(e)[:50]))

    # 4. HLS with image or I-frame streams
    for m3u8 in list(dict.fromkeys(re.findall(r"https?://[^\"'\s<>\\]+\.m3u8[^\"'\s<>\\]*", text)))[:1]:
        try:
            _, _, body = fetch(m3u8, page_url, limit=200_000)
            body = body.decode("utf-8", "replace")
            for tag in ("#EXT-X-I-FRAME-STREAM-INF", "#EXT-X-IMAGE-STREAM-INF"):
                if tag in body:
                    res["notes"].append("HLS playlist has %s" % tag[7:])
        except Exception:
            pass

    # 5. short preview videos and other hints (noted only)
    hints = [w for w in ("mosaic", "sprite", "storyboard", "timeline", "scrub", "data-rotate", "thumbs_rotate", "data-folder") if w in text.lower()]
    prev = re.findall(r"https?://[^\"'\s<>\\]*(?:preview|trailer)[^\"'\s<>\\]*\.mp4[^\"'\s<>\\]*", text)
    if prev:
        res["notes"].append("preview video: %s" % clean(prev[0])[-60:])
    if hints:
        res["notes"].append("page mentions: " + ", ".join(hints))
    return res


def verdict(r):
    best = max((f["count"] for f in r["frames"] if f["kind"] != "storyboard sheets"), default=0)
    sheets = max((f["count"] for f in r["frames"] if f["kind"] == "storyboard sheets"), default=0)
    if best >= 20:
        return "EASY (%d frames)" % best
    if sheets:
        return "STORYBOARD (%d sheets)" % sheets
    if best >= 2:
        return "FEW (%d frames)" % best
    return "NONE found"


def main():
    extra = [a for a in sys.argv[1:] if a.startswith("http")]
    todo = pt.collect(extra, SITES)
    rows = []
    for host in SITES:
        row = dict(site=host)
        urls = todo.get(host) or []
        if not urls:
            row.update(error="no video page known (pass a link)")
        for u in urls:
            print("checking %-20s %s" % (host, clean(u)[:80]), flush=True)
            try:
                row.update(analyse(u))
                row.pop("error", None)
                break
            except Exception as e:
                row["error"] = "%s: %s" % (clean(u)[-50:], str(e)[:90])
            time.sleep(1)
        row["verdict"] = verdict(row) if row.get("page") else "no page read"
        rows.append(row)
        print("   -> %s\n" % row["verdict"], flush=True)
        time.sleep(1)
    lines = ["%-20s %-24s %-9s %-12s %s" % ("site", "result", "size", "spacing", "how / notes")]
    for r in rows:
        f = max(r.get("frames") or [{}], key=lambda x: (x.get("kind") != "storyboard sheets", x.get("count", 0)), default={})
        size = "%sx%s" % f["size"] if f.get("size") else "-"
        spacing = "-"
        if f.get("count") and r.get("duration") and f.get("kind") != "storyboard sheets":
            spacing = "every ~%ds" % round(r["duration"] / f["count"])
        how = (f.get("kind", "") + ": " + f.get("pattern", "")[-70:]) if f else ""
        lines.append("%-20s %-24s %-9s %-12s %s" % (r["site"], r["verdict"], size, spacing, (how + " | " + "; ".join(r.get("notes") or []) + (" | " + r["error"] if r.get("error") else ""))[:230]))
    text = "\n".join(lines)
    print(text)
    OUT.with_suffix(".txt").write_text(text + "\n")
    OUT.with_suffix(".json").write_text(json.dumps(rows, indent=1, default=str))
    print("\nWritten: %s.txt and .json   (sample pictures: %s)" % (OUT, SAMPLES))


if __name__ == "__main__":
    main()
