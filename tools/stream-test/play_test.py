#!/usr/bin/env python3
"""Play test: can a real Chrome play and seek this site's video straight from its address? (what you did by hand in Incognito)

    cd ~/instagram-bot-2
    tools/data18/.venv/bin/python tools/stream-test/play_test.py                 # ALL streamable sites, through the real Stream test pop-up
    tools/data18/.venv/bin/python tools/stream-test/play_test.py LINK ...        # also these video pages
    tools/data18/.venv/bin/python tools/stream-test/play_test.py --sites tnaflix.com,pornwex.tv   # only these sites
    tools/data18/.venv/bin/python tools/stream-test/play_test.py --direct        # the earlier test: tnaflix, porneec, playvids, pornflip, address straight into a <video>
    tools/data18/.venv/bin/python tools/stream-test/play_test.py --media ADDRESS # one video address (mp4 or .m3u8), no page

Default mode: starts Stream test's own server (on a spare port, your running one is not touched), opens its real page
(the pop-up the dashboard shows) in your installed Chrome for each video page, waits for it to read the page and load the video
(including its own switch from direct to the local proxy), seeks to 40%, plays 3 seconds, and reports what happened.
The --direct and --media modes skip Stream test: they read the address themselves.

For every video page it: reads the page, finds the video address (a <source> list, a contentUrl, or an HLS playlist), opens
your installed Google Chrome (hidden), loads that address in a <video> tag on a page that sends no referrer (like the Stream
test pop-up), waits for the video to load, seeks to 40%, plays 3 seconds, and reports what happened. A picture of the
video is saved to play_test_shots/ (local only). Nothing is downloaded beyond the few seconds the video itself reads.

Needs the Playwright package (the data18 venv has it) and Google Chrome (not just Chromium: only Chrome plays H.264).
Writes play_test_results.txt and .json next to this file (addresses cut before the "?", they are signed).
"""
import argparse
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOBS_DIR = Path(os.environ.get("PROBE_JOBS") or HERE.parent / "video-finder" / "data" / "jobs")
SHOTS = HERE / "play_test_shots"
OUT = HERE / "play_test_results"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
SITES = ["tnaflix.com", "porneec.com", "playvids.com", "pornflip.com"]          # --direct mode
ALL_SITES = SITES + ["freepornvideos.xxx", "fpo.xxx", "porntrex.com", "xozilla.com", "eporner.com", "pornhub.com", "porntop.com", "youporn.com",
                     "xhamster.com", "trendyporn.com", "xxxbunker.com", "youcrazyx.com", "yrprno.com", "pornwex.tv", "pornzog.com"]
PER_SITE = 2
EXTRA = [                                   # video pages from your document, so the first run can be compared with your own test
    "https://www.tnaflix.com/anal-porn/I-love-my-family/video5977298",
    "https://www.playvids.com/lW64b_dDjR0/onlyfans-angela-white-he-man-and-the-masturbators-of-the-universe-episode-hot-nurse-fucking-videos",
    "https://porneec.com/blackedraw-ava-amira-sultry-ava-manhandled/",
    "https://porneec.com/realitykings-vivienne-vo-training-day/",
    "https://www.pornflip.com/YTB7KBIGTa5/cute-brown-haired-teenager-rides-him-in-cowgirl-style",
    "https://www.freepornvideos.xxx/videos/93745944/x/",           # sample pages for the sites that may have no saved search (from the Stream test page's "Try" buttons)
    "https://www.fpo.xxx/video/1313302/stepdaughter-l-ves-it-rough-jun-per-ren/",
    "https://www.porntrex.com/video/3357505/lucy-mochi-ix",
    "https://www.xozilla.com/videos/747219/lia-lin-s-steamy-asian-encounter-in-public/",
    "https://xhamster.com/videos/the-inappropriate-gift-xhbkvJ6",
    "https://www.youporn.com/watch/191705511/",
    "https://xxxbunker.com/2130776",
    "https://www.eporner.com/video-qL0KLOufcay/n-little-babes-cum-spills-better/",
    "https://www.pornhub.com/view_video.php?viewkey=6892855d9e556",
    "https://www.trendyporn.com/video/onlyfans-sav-shawz-155687.html",
    "https://www.youcrazyx.com/video/onlyfans-sav-shawz-111384.html",
    "https://www.yrprno.com/video/onlyfans-sav-shawz-113842.html",
    "https://porntop.com/video/920641/veronique-may-be-daddy-s-girl-but-she-isn-t-so-innocent-a",
    "https://www.pornwex.tv/video/365834/sera-ryder-and-millie-morgan-bjraw/",
    "https://pornzog.com/video/28430805/zoe-neli-i-fucked-my-stepsisters-i-cant-take-it-i-need-your-dick-in-my-mouth-now/",
]
TEST_ORIGIN = os.environ.get("PLAY_TEST_ORIGIN", "http://playtest.local")   # the made-up address the test page is served from (only changed to test against a local file)
LOAD_S, SEEK_S, PLAY_S = 30, 30, 3          # most seconds to wait for the video to load / seek, and how long it plays
TEST_PAGE = ('<!doctype html><meta name="referrer" content="no-referrer"><title>play test</title>'
             '<style>html,body{margin:0;background:#000}video{width:640px;height:360px;display:block}</style>'
             '<video id="v" muted playsinline controls></video>')

JS = """
async ({url, loadS, seekS, playS}) => {
  const v = document.getElementById("v");
  const out = {hls_native: v.canPlayType("application/vnd.apple.mpegurl") || "no"};
  const waitFor = (events, ms) => new Promise(res => {
    const hs = [];
    const done = r => { clearTimeout(t); hs.forEach(([e, h]) => v.removeEventListener(e, h)); res(r); };
    const t = setTimeout(() => done("timeout"), ms * 1000);
    for (const e of events) { const h = () => done(e); v.addEventListener(e, h, {once: true}); hs.push([e, h]); }
  });
  const err = () => v.error ? ("code " + v.error.code + (v.error.message ? ": " + v.error.message : "")) : "";
  let t0 = performance.now();
  v.src = url; v.load();
  const first = await waitFor(["loadedmetadata", "error"], loadS);
  out.load_s = Math.round((performance.now() - t0) / 100) / 10;
  if (first !== "loadedmetadata") { out.stage = "load"; out.error = first === "timeout" ? "no answer in " + loadS + " s" : err(); return out; }
  out.duration = isFinite(v.duration) ? Math.round(v.duration) : null;
  out.size = v.videoWidth + "x" + v.videoHeight;
  let from = 0;
  if (out.duration) {
    t0 = performance.now();
    v.currentTime = v.duration * 0.4;
    const s = await waitFor(["seeked", "error"], seekS);
    out.seek_s = Math.round((performance.now() - t0) / 100) / 10;
    if (s !== "seeked") { out.stage = "seek"; out.error = s === "timeout" ? "seek took over " + seekS + " s" : err(); return out; }
    from = v.currentTime;
    out.seeked_to = Math.round(from);
  } else { out.note = "length unknown (live or open-ended)"; }
  try { await v.play(); } catch (e) { out.stage = "play"; out.error = String(e); return out; }
  await new Promise(r => setTimeout(r, playS * 1000));
  out.played_s = Math.round((v.currentTime - from) * 10) / 10;
  out.paused = v.paused;
  const q = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : null;
  out.frames = q ? q.totalVideoFrames : null;
  if (v.error) { out.stage = "play"; out.error = err(); }
  return out;
}
"""


def clean(url):
    p = urllib.parse.urlsplit(url)
    return "%s://%s%s" % (p.scheme, p.netloc, p.path)


def host_of(url):
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def fetch_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def attr(tag, name):
    m = re.search(r"""\b%s\s*=\s*(?:"([^"]*)"|'([^']*)')""" % name, tag)
    return htmllib.unescape(m.group(1) if m.group(1) is not None else m.group(2)) if m else ""


def find_sources(page):
    """The video addresses on a page -> [{kind: mp4|hls, url, label}], lowest quality first.
    Reads <source> tags (tnaflix: several mp4 sizes; playvids and pornflip: an HLS playlist) and a contentUrl (porneec: a plain mp4)."""
    text = page.replace("\\/", "/")
    found = []

    def add(kind, url, label):
        if url and url.startswith("http") and url not in [f["url"] for f in found]:
            found.append(dict(kind=kind, url=url, label=label))

    for tag in re.findall(r"<source\b[^>]*>", text, re.I):
        src, typ = attr(tag, "src"), attr(tag, "type").lower()
        if ".m3u8" in src or "mpegurl" in typ:
            add("hls", src, "HLS")
        elif ".mp4" in src or typ == "video/mp4":
            size = attr(tag, "size") or attr(tag, "label") or attr(tag, "res")
            add("mp4", src, ("%sp" % size) if size.isdigit() else (size or "mp4"))
    for m in re.finditer(r"""itemprop=["']contentUrl["'][^>]*content=["']([^"']+)["']|content=["']([^"']+)["'][^>]*itemprop=["']contentUrl["']""", text):
        u = htmllib.unescape(m.group(1) or m.group(2))
        if re.search(r"\.(mp4|m3u8|webm)(\?|$)", u):
            add("hls" if ".m3u8" in u else "mp4", u, "contentUrl")
    if not found:                                         # last resort: the first plain mp4 / playlist address in the page
        m = re.search(r"https?://[^\"'\s<>\\]+\.(?:m3u8|mp4)[^\"'\s<>\\]*", text)
        if m:
            add("hls" if ".m3u8" in m.group(0) else "mp4", htmllib.unescape(m.group(0)), "found in page")
    found.sort(key=lambda f: int(re.sub(r"\D", "", f["label"]) or 0) if f["label"].endswith("p") else 0)
    return found


def collect(extra, sites=None):
    pages = {}
    wanted = set(sites or SITES)

    def add(url):
        h = host_of(url)
        if h in wanted and url not in pages.setdefault(h, []) and len(pages[h]) < PER_SITE:
            pages[h].append(url)

    for u in list(EXTRA) + list(extra):               # your document's pages first, then anything given on the command line
        add(u)
    files = sorted(JOBS_DIR.glob("*.json"), reverse=True) if JOBS_DIR.exists() else []
    for f in files:                                   # then pages from your saved Video Finder searches
        try:
            job = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        for sd in (job.get("sites") or {}).values():
            for c in ((sd.get("results") or {}).get("ranked") or [])[:2]:
                add(c.get("url") or "")
    return pages


def play(browser, media_url, shot):
    ctx = browser.new_context(viewport={"width": 640, "height": 360})
    page = ctx.new_page()
    try:
        page.route(TEST_ORIGIN + "/__playtest__", lambda r: r.fulfill(status=200, content_type="text/html", body=TEST_PAGE))
        page.goto(TEST_ORIGIN + "/__playtest__")
        seen = []                                                 # what the site answered to the video request (the page itself cannot see this)
        page.on("response", lambda r: seen.append("%s %s" % (r.status, (r.headers.get("content-type") or "?").split(";")[0])) if r.url == media_url else None)
        res = page.evaluate(JS, dict(url=media_url, loadS=LOAD_S, seekS=SEEK_S, playS=PLAY_S))
        if seen:
            res["http"] = seen[0]
        try:
            SHOTS.mkdir(exist_ok=True)
            page.locator("video").screenshot(path=str(shot))
            res["shot"] = shot.name
        except Exception:
            pass
        return res
    finally:
        ctx.close()


def verdict(r):
    if r.get("error"):
        return "FAILED at %s" % r.get("stage", "?")
    if (r.get("played_s") or 0) >= PLAY_S * 0.6 and (r.get("frames") or 1) > 0 and not r.get("paused"):
        return "PLAYS"
    return "STALLED"


def test_source(browser, label, src):
    t0 = time.time()
    shot = SHOTS / ("%s_%s.png" % (re.sub(r"\W+", "_", label)[:40], int(t0)))
    row = dict(kind=src["kind"], quality=src["label"], media=clean(src["url"]))
    try:
        row.update(play(browser, src["url"], shot))
    except Exception as e:
        row.update(error=str(e)[:200], stage="browser")
    row["verdict"] = verdict(row)
    return row


POPUP_JS = """
async ({loadS, seekS, playS}) => {
  const out = {};
  if (typeof info === "undefined" || !info) { out.stage = "read"; out.error = document.querySelector("#info").textContent.slice(0, 220); return out; }
  out.read_with = info.read_with;
  out.qualities = info.sources.map(o => o.label).join(",");
  out.page_len = info.duration || null;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const waitFor = (events, ms) => new Promise(res => {
    const hs = [];
    const done = r => { clearTimeout(t); hs.forEach(([e, h]) => vid.removeEventListener(e, h)); res(r); };
    const t = setTimeout(() => done("timeout"), ms * 1000);
    for (const e of events) { const h = () => done(e); vid.addEventListener(e, h, {once: true}); hs.push([e, h]); }
  });
  const err = () => vid.error ? ("code " + vid.error.code + (vid.error.message ? ": " + vid.error.message : "")) : "";
  let t0 = performance.now();
  while (vid.readyState < 1 && performance.now() - t0 < loadS * 1000) {                    // the page may switch itself from direct to the local proxy meanwhile
    if (vid.error && document.querySelector("#mode").value === "proxy") break;             // it already tried the proxy and that failed too: no point waiting
    await sleep(200);
  }
  out.load_s = Math.round((performance.now() - t0) / 100) / 10;
  out.mode = document.querySelector("#mode").value;
  out.fell_back = /Direct playback failed/.test(logEl.innerText);
  if (vid.readyState < 1) { out.stage = "load"; out.error = vid.error ? err() : "no answer in " + loadS + " s"; return out; }
  out.duration = isFinite(vid.duration) ? Math.round(vid.duration) : null;
  out.size = vid.videoWidth + "x" + vid.videoHeight;
  let from = 0;
  if (out.duration) {
    t0 = performance.now();
    vid.currentTime = vid.duration * 0.4;
    const r = await waitFor(["seeked", "error"], seekS);
    out.seek_s = Math.round((performance.now() - t0) / 100) / 10;
    if (r !== "seeked") { out.stage = "seek"; out.error = r === "timeout" ? "seek took over " + seekS + " s" : err(); return out; }
    from = vid.currentTime; out.seeked_to = Math.round(from);
  }
  try { await vid.play(); } catch (e) { out.stage = "play"; out.error = String(e); return out; }
  await sleep(playS * 1000);
  out.played_s = Math.round((vid.currentTime - from) * 10) / 10;
  out.paused = vid.paused;
  const q = vid.getVideoPlaybackQuality ? vid.getVideoPlaybackQuality() : null;
  out.frames = q ? q.totalVideoFrames : null;
  if (vid.error) { out.stage = "play"; out.error = err(); }
  return out;
}
"""


def popup_test(browser, port, page_url, shot):
    """Open Stream test's real page for this video page link, exactly as the dashboard's pop-up does, and play / seek in it."""
    ctx = browser.new_context(viewport={"width": 900, "height": 700})
    page = ctx.new_page()
    try:
        page.goto("http://127.0.0.1:%d/?v=%s&embed=1" % (port, urllib.parse.quote(page_url, safe="")))
        try:
            page.wait_for_function("() => (typeof info !== 'undefined' && info) || /^(Error|No video)/.test(document.querySelector('#info').textContent)", timeout=180000)
        except Exception:
            return dict(stage="read", error="Stream test did not answer in 3 minutes")
        res = page.evaluate(POPUP_JS, dict(loadS=LOAD_S + 30, seekS=SEEK_S, playS=PLAY_S))
        try:
            SHOTS.mkdir(exist_ok=True)
            page.locator("#vid").screenshot(path=str(shot))
            res["shot"] = shot.name
        except Exception:
            pass
        return res
    finally:
        ctx.close()


def main_popup(a):
    import threading
    sys.path.insert(0, str(HERE))
    import server as st
    sites = [x.strip() for x in a.sites.split(",")] if a.sites else ALL_SITES
    todo = collect([x for x in a.links if x.startswith("http")], sites)
    notes = ["%s: no video page known (pass a link)" % h for h in sites if h not in todo]
    from playwright.sync_api import sync_playwright
    srv = st.ThreadingHTTPServer(("127.0.0.1", 0), st.H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("Stream test started on port %d (your own one is not touched)\n" % port)
    rows = []
    with sync_playwright() as p:
        kw = dict(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        try:
            browser = p.chromium.launch(executable_path=a.browser_path, **kw) if a.browser_path else p.chromium.launch(channel="chrome", **kw)
        except Exception as e:
            sys.exit("Could not start Chrome: %s\nInstall Google Chrome, or pass --browser-path." % str(e).splitlines()[0])
        print("browser: %s\n" % browser.version)
        for host in sites:
            for u in todo.get(host, []):
                print("testing %-20s %s" % (host, clean(u)[:80]), flush=True)
                t0 = time.time()
                try:
                    r = popup_test(browser, port, u, SHOTS / ("%s_%d.png" % (re.sub(r"\W+", "_", host), int(t0))))
                except Exception as e:
                    r = dict(stage="browser", error=str(e)[:200])
                r["verdict"] = verdict(r)
                r.update(site=host, page=clean(u), seconds=round(time.time() - t0, 1))
                rows.append(r)
                print("   -> %s %s\n" % (r["verdict"], r.get("error") or ""), flush=True)
                time.sleep(2)
        browser.close()
    srv.shutdown()
    lines = ["%-20s %-24s %-14s %-16s %-6s %-6s %-6s %-6s %-6s %s" % ("site", "result", "read with", "mode", "len", "load s", "seek s", "played", "shown", "notes")]
    for r in rows:
        mode = (r.get("mode") or "-") + (" (fell back)" if r.get("fell_back") else "")
        lines.append("%-20s %-24s %-14s %-16s %-6s %-6s %-6s %-6s %-6s %s" % (r["site"], r["verdict"], (r.get("read_with") or "-")[:14], mode[:16], r.get("duration") or "-",
                     r.get("load_s", "-"), r.get("seek_s", "-"), r.get("played_s", "-"), r.get("size", "-"), (r.get("error") or r.get("qualities") or "")[:110]))
    lines += [""] + notes
    text = "\n".join(lines)
    print(text)
    OUT.with_suffix(".txt").write_text(text + "\n")
    OUT.with_suffix(".json").write_text(json.dumps(rows, indent=1))
    print("\nWritten: %s.txt and .json   (pictures: %s)" % (OUT, SHOTS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("links", nargs="*", help="video page links to test as well")
    ap.add_argument("--media", help="test one video address (mp4 or .m3u8) directly, no page")
    ap.add_argument("--direct", action="store_true", help="the earlier test: read the address ourselves and give it straight to a <video> (4 sites)")
    ap.add_argument("--sites", help="comma-separated hosts to test, e.g. tnaflix.com,pornwex.tv (default: all streamable sites)")
    ap.add_argument("--browser-path", help="path of a Chrome/Chromium program (default: your installed Google Chrome)")
    ap.add_argument("--all-qualities", action="store_true", help="test every quality (default: lowest and highest) (--direct only)")
    a = ap.parse_args()
    try:
        import playwright  # noqa: F401
    except ImportError:
        sys.exit("Playwright is missing. Run this with tools/data18/.venv/bin/python (it has Playwright).")
    if a.media or a.direct:
        return main_direct(a)
    return main_popup(a)


def main_direct(a):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright is missing. Run this with tools/data18/.venv/bin/python (it has Playwright).")
    jobs = []                                           # (site, page link, source)
    notes = []
    if a.media:
        jobs.append((host_of(a.media), a.media, dict(kind="hls" if ".m3u8" in a.media else "mp4", url=a.media, label="given")))
    else:
        todo = collect([x for x in a.links if x.startswith("http")])
        for host in SITES:
            if host not in todo:
                notes.append("%s: no video page known (pass a link)" % host)
        for host, urls in todo.items():
            for u in urls:
                print("reading %-16s %s" % (host, clean(u)[:90]), flush=True)
                try:
                    srcs = find_sources(fetch_page(u))
                except Exception as e:
                    notes.append("%s: could not read the page (%s) %s" % (host, str(e)[:80], clean(u)[:70]))
                    continue
                if not srcs:
                    notes.append("%s: no video address found on %s" % (host, clean(u)[:80]))
                    continue
                mp4 = [s for s in srcs if s["kind"] == "mp4"]
                pick = srcs if a.all_qualities else (([mp4[0], mp4[-1]] if len(mp4) > 1 else mp4[:1]) + [s for s in srcs if s["kind"] == "hls"][:1])
                for s in pick:
                    jobs.append((host, u, s))
    rows = []
    with sync_playwright() as p:
        kw = dict(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        try:
            browser = p.chromium.launch(executable_path=a.browser_path, **kw) if a.browser_path else p.chromium.launch(channel="chrome", **kw)
        except Exception as e:
            sys.exit("Could not start Chrome: %s\nInstall Google Chrome, or pass --browser-path." % str(e).splitlines()[0])
        print("browser: %s\n" % browser.version)
        for host, page_url, src in jobs:
            print("playing %-16s %-6s %-10s %s" % (host, src["kind"], src["label"], clean(src["url"])[:80]), flush=True)
            r = test_source(browser, host + "_" + src["label"], src)
            r.update(site=host, page=clean(page_url))
            rows.append(r)
            print("   -> %s %s\n" % (r["verdict"], r.get("error") or ""), flush=True)
            time.sleep(2)
        browser.close()
    lines = ["%-14s %-5s %-9s %-24s %-5s %-7s %-7s %-8s %s" % ("site", "type", "quality", "result", "len", "load s", "seek s", "played s", "notes")]
    for r in rows:
        lines.append("%-14s %-5s %-9s %-24s %-5s %-7s %-7s %-8s %s" % (
            r["site"], r["kind"], r["quality"][:9], r["verdict"], r.get("duration") or "-", r.get("load_s", "-"), r.get("seek_s", "-"), r.get("played_s", "-"),
            ((r.get("error") + (" [site answered " + r["http"] + "]" if r.get("http") else "") if r.get("error") else ("native HLS: " + r["hls_native"] if r["kind"] == "hls" else "")))[:110]))
    lines += [""] + notes
    text = "\n".join(lines)
    print(text)
    OUT.with_suffix(".txt").write_text(text + "\n")
    OUT.with_suffix(".json").write_text(json.dumps(rows, indent=1))
    print("\nWritten: %s.txt and .json   (pictures: %s)" % (OUT, SHOTS))


if __name__ == "__main__":
    main()
