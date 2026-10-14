#!/usr/bin/env python3
"""Check one or more Pornbox scenes as a source of frames. Changes nothing except saving a few sample pictures locally.

    cd ~/instagram-bot-2
    tools/data18/.venv/bin/python tools/stream-test/pornbox_probe.py 127185
    tools/data18/.venv/bin/python tools/stream-test/pornbox_probe.py 127185 127186 ...

For each scene id it reads https://pornbox.com/contents/<id> (the same JSON the site's own page uses), prints the details that help match a
video (title, studio, performers, date, length), counts the screenshots and how far apart they are, then downloads three of them (first,
middle, last) in both sizes, with and without a referrer, and reports: did it work, how many KB, how many pixels. It finishes with an
estimate of the disk space one scene would take. Samples go in pornbox_samples/ (local only). Writes pornbox_probe_results.txt.
"""
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "pornbox_samples"
OUT = HERE / "pornbox_probe_results"
BASE = os.environ.get("PORNBOX_BASE", "https://pornbox.com")        # only changed to test against a stand-in server
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
API_HEADERS = {"User-Agent": UA, "X-Requested-With": "XMLHttpRequest", "Cookie": "agree18=1", "Accept": "application/json, text/plain, */*"}


def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, (r.headers.get("Content-Type") or ""), r.read()


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


def seconds(text):
    m = re.fullmatch(r"(?:(\d+):)?(\d+):(\d+)", (text or "").strip())
    return (int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))) if m else None


def names(items):
    out = []
    for m in items or []:
        if isinstance(m, dict):
            out.append(str(m.get("model_name") or m.get("name") or "?"))
    return out


def try_image(url, referer):
    h = {"User-Agent": UA}
    if referer:
        h["Referer"] = BASE + "/"
    try:
        status, ctype, data = get(url, h)
        return dict(ok=status == 200 and "image" in ctype.lower(), status=status, kb=len(data) // 1024, size=image_size(data), data=data)
    except urllib.error.HTTPError as e:
        return dict(ok=False, status=e.code, kb=0, size=None, data=b"")
    except Exception as e:
        return dict(ok=False, status=str(e)[:40], kb=0, size=None, data=b"")


def probe(scene_id, lines):
    lines.append("=" * 70)
    status, _, raw = get("%s/contents/%s" % (BASE, scene_id), API_HEADERS)
    d = json.loads(raw)
    runtime = seconds(d.get("runtime"))
    shots = d.get("screenshots") or []
    lines.append("scene %s: %s" % (scene_id, d.get("scene_name")))
    lines.append("  studio: %s | released: %s | length: %s (%s s)" % (d.get("studio"), d.get("release_date") or d.get("publish_date"), d.get("runtime"), runtime))
    lines.append("  performers: %s | male: %s" % (", ".join(names(d.get("models")) + names(d.get("talents_female"))) or "-", ", ".join(names(d.get("male_models"))) or "-"))
    lines.append("  price: %s | purchased: %s | guest preview allowed: %s | niches/tags: %s" % (d.get("price"), d.get("is_purchased"), d.get("allow_guest_preview"), len(d.get("niches") or [])))
    lines.append("  screenshots: %d%s" % (len(shots), ("  -> one every %.1f s" % (runtime / len(shots))) if runtime and shots else ""))
    if not shots:
        lines.append("  no screenshots list in this scene")
        return
    lines.append("  one entry's fields: %s" % ", ".join(shots[0].keys() if isinstance(shots[0], dict) else ["(not a dict)"]))
    SAMPLES.mkdir(exist_ok=True)
    picks = sorted({0, len(shots) // 2, len(shots) - 1})
    totals = {}
    for i in picks:
        for field in [k for k in shots[i] if isinstance(shots[i][k], str) and shots[i][k].startswith("http")]:
            got = False
            for referer in (False, True):
                r = try_image(shots[i][field], referer)
                lines.append("  shot #%-3d %-16s %-14s -> %s%s %s KB %s" % (i + 1, field, "with referrer" if referer else "no referrer", "OK" if r["ok"] else "FAILED ", "" if r["ok"] else " (%s)" % r["status"],
                                                                         r["kb"], ("%dx%d" % r["size"]) if r["size"] else ""))
                if r["ok"] and not got:
                    got = True
                    (SAMPLES / ("%s_%d_%s.jpg" % (scene_id, i + 1, field))).write_bytes(r["data"])
                    totals.setdefault(field, []).append(r["kb"])
                time.sleep(0.3)
    for field, kbs in totals.items():
        avg = sum(kbs) / len(kbs)
        lines.append("  estimate, %-16s ~%d KB each x %d = about %.0f MB per scene" % (field, avg, len(shots), avg * len(shots) / 1024))


def main():
    ids = [a for a in sys.argv[1:] if a.isdigit()]
    if not ids:
        sys.exit("Give one or more Pornbox scene ids, e.g. 127185")
    lines = []
    for sid in ids:
        start = len(lines)
        try:
            probe(sid, lines)
        except Exception as e:
            lines.append("scene %s: failed (%s)" % (sid, str(e)[:120]))
        print("\n".join(lines[start:]), flush=True)
        time.sleep(1)
    text = "\n".join(lines)
    OUT.with_suffix(".txt").write_text(text + "\n")
    print("\nWritten: %s.txt   (sample pictures: %s)" % (OUT, SAMPLES))


if __name__ == "__main__":
    main()
