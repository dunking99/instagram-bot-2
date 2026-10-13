#!/usr/bin/env python3
"""Save a SHORT CLIP of a video from its page link, reading only that part of the video (the rest is never downloaded).

    python3 remote_clip.py --url "https://site/video-page" --out-dir DIR --name "Title" --k 8 [--count 23] [--d18-seconds 1380]
                           [--window 180] [--height 480] [--status status.json]

Where the clip comes from: data18's video stills are one per minute, the first at 0:00, so still number k sits at about (k - 1) minutes.
The clip is centred on that moment: with the default 180 s window it starts 90 s before and ends 90 s after.
If the copy on the site is a different length from data18's, the moment is scaled to the site's length.

How the video is found and read is the same as in remote_frames.py (direct file with partial reads, embedded player, segmented HLS
stream, or yt-dlp's lookup). A direct file is cut with ffmpeg through the small caching proxy (only the needed bytes are fetched);
an HLS stream is cut by fetching only the segments that cover the clip.

Writes DIR/<name> - part 05m30-08m30.mp4 (a .part file until it is complete, so nothing picks it up half-written).
Prints "@@FILE<TAB><path>" when done. Progress is written to --status as JSON. Python 3.9, standard library only. Needs ffmpeg and ffprobe.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import remote_frames as r   # noqa: E402  (finding and reading the video is shared with the frame maker)

Fail = r.Fail


def clock(sec):
    sec = int(round(sec))
    return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60) if sec >= 3600 else "%d:%02d" % (sec // 60, sec % 60)


def tag(sec):
    sec = int(round(sec))
    return "%dh%02dm%02d" % (sec // 3600, sec % 3600 // 60, sec % 60) if sec >= 3600 else "%02dm%02d" % (sec // 60, sec % 60)


def locate(url, height):
    """Find the video behind a page link -> ("file", real address) or ("hls", HlsSource). Same order of attempts as the frame maker."""
    page_error = None
    try:
        page = r.fetch_text(url)
    except Fail as e:
        page, page_error = "", e
    sources = r.find_sources(page, url)
    kt = r.find_kt(page)
    if kt:
        sources = kt + [x for x in sources if x[1] not in [k[1] for k in kt]]
    pages = [(page, url)]
    if not sources and page:
        for emb in r.find_embeds(page, url):
            ep = r.fetch_text(emb, referer=url)
            pages.append((ep, emb))
            sources = r.find_kt(ep) or r.find_sources(ep, emb)
            if sources:
                break

    def usable(cands):
        if not cands:
            return None
        first = r.pick_source(cands, height)
        known = [x for x in cands if x[0] and x[0] <= height]
        for h, cand in [first] + sorted((x for x in cands if x != first), key=lambda x: (x not in known, -x[0])):
            real = r.probe_video(cand, url)
            if real:
                return real
        return None

    hls, found = None, None
    if not kt and len(sources) > 3:
        files, master = r.ytdlp_lookup(url)
        found = usable(files)
        if not found and master:
            hls = r.HlsSource(master, url, height)
    if not found and not hls:
        found = usable(sources)
    if not found:
        for body, where in pages:
            masters = r.find_hls(body, where)
            if masters:
                hls = r.HlsSource(masters[0], where, height)
                break
    if not found and not hls:
        files, master = r.ytdlp_lookup(url)
        found = usable(files)
        if not found and master:
            hls = r.HlsSource(master, url, height)
    if found:
        return "file", found
    if hls:
        return "hls", hls
    if page_error:
        raise page_error
    raise Fail("Couldn't find a video file or stream on that page (it may need a login, load the video with a script, or use protection I won't work around).")


def plan(length, k, count, d18, window):
    """-> (start, end, centre, note): the clip's start and end in seconds of the site's video."""
    note = ""
    if d18 and abs(count - d18 / 60.0) > 2.5:
        raise Fail("This scene's stills don't follow the one-per-minute pattern (%d stills for %.0f minutes), so a clip can't be placed reliably. Download the whole video instead." % (count, d18 / 60.0))
    centre = (k - 1) * 60.0
    if d18 and 0.7 <= length / float(d18) <= 1.3:
        centre *= length / float(d18)                      # the site's copy is a slightly different length: scale to it
    elif d18:
        raise Fail("The video on this site is %s long, but data18 says %s, so it is probably a different cut and a clip can't be placed reliably. Download the whole video instead." % (clock(length), clock(d18)))
    else:
        note = "data18 gives no length for this scene, so the position is unverified."
    start, end = centre - window / 2.0, centre + window / 2.0
    if start < 0:
        start, end = 0.0, min(float(window), length)
    if end > length:
        start, end = max(0.0, length - window), float(length)
    return start, end, centre, note


def unique(path):
    base, ext = os.path.splitext(path)
    n, out = 2, path
    while os.path.exists(out) or os.path.exists(out + ".part"):
        out = "%s (%d)%s" % (base, n, ext)
        n += 1
    return out


def clean_name(s):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", s).strip(" .")
    return re.sub(r"\s+", " ", s)[:100].strip() or "video"


def run(args):
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise Fail("%s is not installed (brew install ffmpeg)." % tool)
    r.say(phase="finding", progress=2, message="Finding the video…")
    kind, handle = locate(args.url, args.height)
    os.makedirs(args.out_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="clip_")
    try:
        if kind == "file":
            u = urllib.parse.urlparse(handle)
            origin = "%s://%s" % (u.scheme, u.netloc)
            path = u.path + ("?" + u.query if u.query else "")
            cache = r.RangeCache(origin, {"User-Agent": r.UA, "Referer": "%s://%s/" % (urllib.parse.urlparse(args.url).scheme, urllib.parse.urlparse(args.url).netloc)})
            try:
                local = "http://127.0.0.1:%d%s" % (cache.port, path)
                cache.prefetch(path)
                p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", local], capture_output=True, text=True, timeout=120)
                try:
                    length = float(p.stdout.strip().splitlines()[0])
                except (ValueError, IndexError):
                    raise Fail("Couldn't read the video's length from the server.")
                start, end, centre, note = plan(length, args.k, args.count, args.d18_seconds, args.window)
                final = unique(os.path.join(args.out_dir, "%s - part %s-%s.mp4" % (clean_name(args.name), tag(start), tag(end))))
                r.say(phase="clipping", progress=10, start=start, end=end, centre=centre, video_length=length, note=note,
                      message="Saving %s–%s of the %s video (about %d%% of it)…" % (clock(start), clock(end), clock(length), round(100 * (end - start) / length)))
                est = max(cache.sizes.values()) * (end - start) / length if cache.sizes else 0
                proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-ss", "%.2f" % start, "-i", local, "-t", "%.2f" % (end - start), "-c", "copy",
                                         "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", "-f", "mp4", final + ".part"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                while proc.poll() is None:
                    time.sleep(0.7)
                    if est:
                        r.say(mb=round(cache.fetched / 1e6, 1), progress=min(95, 10 + 85 * cache.fetched / est))
                err = (proc.stderr.read() or b"").decode("utf-8", "replace")[-300:]
                if proc.returncode != 0 or not os.path.exists(final + ".part") or os.path.getsize(final + ".part") < 50000:
                    raise Fail("ffmpeg could not cut the clip. %s" % err.strip())
                fetched = cache.fetched
                size_total = max(cache.sizes.values()) if cache.sizes else 0
            finally:
                cache.close()
        else:
            hls = handle
            length = hls.duration
            start, end, centre, note = plan(length, args.k, args.count, args.d18_seconds, args.window)
            segs = [s for s in hls.segments if s[0] + s[1] > start and s[0] < end]
            if not segs:
                raise Fail("No part of the stream covers that moment.")
            final = unique(os.path.join(args.out_dir, "%s - part %s-%s.mp4" % (clean_name(args.name), tag(segs[0][0]), tag(segs[-1][0] + segs[-1][1]))))
            r.say(phase="clipping", progress=10, start=segs[0][0], end=segs[-1][0] + segs[-1][1], centre=centre, video_length=length, note=note,
                  message="Saving %s–%s of the %s stream (%d segments)…" % (clock(segs[0][0]), clock(segs[-1][0] + segs[-1][1]), clock(length), len(segs)))
            ts = os.path.join(tmp_dir, "clip.ts")
            fetched = 0
            with open(ts, "wb") as out:
                for i, seg in enumerate(segs):
                    data = hls._get(seg[2], None)
                    out.write(data)
                    fetched += len(data)
                    r.say(mb=round(fetched / 1e6, 1), progress=10 + 85 * (i + 1) / len(segs))
            size_total = hls.sizes.get("stream", 0)
            p = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", ts, "-c", "copy", "-movflags", "+faststart", "-f", "mp4", final + ".part"], capture_output=True, text=True, timeout=300)
            if p.returncode != 0 or not os.path.exists(final + ".part"):
                raise Fail("ffmpeg could not join the segments. %s" % p.stderr[-300:])
        os.replace(final + ".part", final)
        r.say(phase="done", progress=100, file=final, mb=round(fetched / 1e6, 1), file_mb=round(os.path.getsize(final) / 1e6, 1),
              percent_of_video=round(100 * fetched / size_total) if size_total else None,
              message="Saved the clip %s–%s." % (clock(start), clock(end)))
        print("@@FILE\t%s" % final, flush=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        for stale in (locals().get("final"),):
            if stale and os.path.exists(stale + ".part"):
                os.remove(stale + ".part")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name", required=True, help="the video's title (used in the file name)")
    ap.add_argument("--k", type=int, required=True, help="which still (1 = the first, at 0:00)")
    ap.add_argument("--count", type=int, default=0, help="how many video stills the scene has (used to check the one-per-minute pattern)")
    ap.add_argument("--d18-seconds", type=float, default=0, help="the length data18 gives for the scene (0 = unknown)")
    ap.add_argument("--window", type=float, default=180, help="clip length in seconds")
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--status", help="progress file (JSON)")
    args = ap.parse_args()
    r.STATUS_FILE = args.status
    try:
        run(args)
    except Fail as e:
        r.say(phase="error", error=str(e))
        print("ERROR:", e, file=sys.stderr)
        return 1
    except Exception as e:
        r.say(phase="error", error="%s: %s" % (type(e).__name__, e))
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
