#!/usr/bin/env python3
"""Watch what a web page asks for, and show where its pictures come from. Changes nothing.

    cd ~/instagram-bot-2
    tools/data18/.venv/bin/python tools/stream-test/capture_network.py "https://example.com/video/123"

Opens your Google Chrome in a clean, logged-out window on that page. YOU use the page as normal (click "screenshots", scroll the gallery,
press play for a second). When you are done, come back to the terminal and press Enter (or use --seconds 60 to stop by itself).
It then prints:
  - every data request (JSON and similar) that contained picture addresses: which address asked, how many pictures it listed, a sample;
  - every group of pictures that were loaded: the folder, how many, whether the file names are numbered, sizes in KB, and the picture size.
Cookies and passwords are never recorded. Long values in addresses are replaced by their length. Writes network_capture_results.txt/.json.
"""
import argparse
import json
import re
import struct
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "network_capture_results"
IMGURL = re.compile(r"""https?:(?://|\\/\\/)[^"'\s<>\\)]+?\.(?:jpe?g|png|webp|avif)(?:\?[^"'\s<>\\)]*)?""", re.I)
IMGEXT = re.compile(r"\.(jpe?g|png|webp|avif)(\?|$)", re.I)


def redact(url):
    """Keep the address readable but drop anything that looks like a token: query values longer than 12 characters become <length>."""
    p = urllib.parse.urlsplit(url.replace("\\/", "/"))
    q = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    q = "&".join("%s=%s" % (k, v if len(v) <= 12 else "<%d>" % len(v)) for k, v in q)
    return "%s://%s%s%s" % (p.scheme, p.netloc, p.path, ("?" + q) if q else "")


def image_size(data):
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                if data[i + 1] in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except Exception:
        pass
    return None


def group_images(urls_with_size):
    """[(url, bytes)] -> groups by folder and file-name shape, with counts."""
    groups = {}
    for url, nbytes in urls_with_size:
        p = urllib.parse.urlsplit(url.replace("\\/", "/"))
        folder, _, name = p.path.rpartition("/")
        folder = "/".join("*" if (len(seg) > 24 or "==" in seg) else seg for seg in folder.split("/"))      # signed links carry a token in the path: treat those as one folder
        m = re.match(r"^(.*?)(\d+)(\D*)$", name.rsplit(".", 1)[0])
        shape = ("%sN%s" % (m.group(1), m.group(3)) if m else "(named)") + "." + (name.rsplit(".", 1)[-1] if "." in name else "?")
        g = groups.setdefault((p.netloc, folder, shape), dict(n=0, nums=[], bytes=0, sample=url))
        g["n"] += 1
        g["bytes"] += nbytes or 0
        if m:
            g["nums"].append(int(m.group(2)))
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="the page to open")
    ap.add_argument("--seconds", type=int, help="stop by itself after this long (default: wait for Enter)")
    ap.add_argument("--headless", action="store_true", help="no visible window (for testing; you cannot click)")
    ap.add_argument("--click", help="click the first element showing this text, shortly after the page loads")
    ap.add_argument("--browser-path", help="path of a Chrome/Chromium program (default: your installed Google Chrome)")
    a = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright is missing. Run this with tools/data18/.venv/bin/python (it has Playwright).")
    responses = []
    with sync_playwright() as p:
        kw = dict(headless=a.headless, args=["--autoplay-policy=no-user-gesture-required"])
        try:
            browser = p.chromium.launch(executable_path=a.browser_path, **kw) if a.browser_path else p.chromium.launch(channel="chrome", **kw)
        except Exception as e:
            sys.exit("Could not start Chrome: %s" % str(e).splitlines()[0])
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})      # a fresh window: no cookies, not logged in
        page = ctx.new_page()
        page.on("response", lambda r: responses.append(r))
        print("Opening %s ..." % redact(a.url))
        page.goto(a.url, wait_until="domcontentloaded", timeout=60000)
        if a.click:
            try:
                time.sleep(3)
                page.get_by_text(a.click, exact=False).first.click(timeout=8000)
            except Exception as e:
                print("Could not click %r: %s" % (a.click, str(e).splitlines()[0]))
        if a.seconds:
            print("Recording for %d seconds ..." % a.seconds)
            time.sleep(a.seconds)
        else:
            input("\nUse the page now (open the screenshots, scroll). Press Enter here when you are done... ")
        # read what came back, before the window closes
        data_hits, images = [], []
        for r in responses:
            try:
                ct = (r.headers.get("content-type") or "").split(";")[0].lower()
                rt = r.request.resource_type
                size = int(r.headers.get("content-length") or 0)
                if rt == "image" or ct.startswith("image/") or IMGEXT.search(r.url):
                    images.append((r.url, size))
                elif rt in ("xhr", "fetch", "document") or "json" in ct:
                    body = r.body()
                    if len(body) > 4_000_000:
                        continue
                    text = body.decode("utf-8", "replace")
                    found = list(dict.fromkeys(IMGURL.findall(text)))
                    if found:
                        keys = None
                        try:
                            j = json.loads(text)
                            keys = list(j)[:10] if isinstance(j, dict) else "list of %d" % len(j)
                        except ValueError:
                            pass
                        data_hits.append(dict(url=redact(r.url), status=r.status, kind=rt, content_type=ct, bytes=len(body), pictures_listed=len(found),
                                              keys=keys, sample=[redact(u) for u in found[:3]]))
            except Exception:
                continue
        groups = group_images(images)
        top = sorted(groups.items(), key=lambda kv: -kv[1]["n"])[:8]
        lines = ["Requests recorded: %d   pictures loaded: %d" % (len(responses), len(images)), ""]
        lines.append("DATA REQUESTS THAT LISTED PICTURES (the likely 'screenshots list'):")
        for d in sorted(data_hits, key=lambda x: -x["pictures_listed"])[:8]:
            lines += ["  %s %s  [%s, %d KB]" % (d["status"], d["url"], d["kind"], d["bytes"] // 1024), "     lists %d pictures; top-level keys: %s" % (d["pictures_listed"], d["keys"]),
                      "     e.g. " + "  |  ".join(d["sample"])]
        if not data_hits:
            lines.append("  none found (the pictures may be written straight into the page, or loaded another way)")
        lines += ["", "GROUPS OF PICTURES LOADED (biggest first):"]
        out_groups = []
        for (host, folder, shape), g in top:
            nums = sorted(set(g["nums"]))
            kb = g["bytes"] // 1024 // max(g["n"], 1)
            size = None
            try:
                size = image_size(ctx.request.get(g["sample"], timeout=15000).body()[:200000])
            except Exception:
                pass
            seq = ("numbered %d..%d" % (nums[0], nums[-1])) if nums else "not numbered"
            lines.append("  %3d x  %s%s/%s   %s   ~%s KB each   picture size %s" % (g["n"], host, folder[-60:], shape, seq, kb or "?", "%dx%d" % size if size else "?"))
            out_groups.append(dict(host=host, folder=folder, shape=shape, count=g["n"], numbers=(nums[0], nums[-1]) if nums else None, kb_each=kb, size=size))
        browser.close()
    text = "\n".join(lines)
    print("\n" + text)
    OUT.with_suffix(".txt").write_text(text + "\n")
    OUT.with_suffix(".json").write_text(json.dumps(dict(data_requests=data_hits, picture_groups=out_groups), indent=1, default=str))
    print("\nWritten: %s.txt and .json" % OUT)


if __name__ == "__main__":
    main()
