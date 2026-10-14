#!/usr/bin/env python3
"""Open a JSON address (or file) and show where its pictures are: which fields hold picture addresses, how many are really different pictures
(the same picture often appears at several sizes), what sizes exist, and what one entry looks like. Changes nothing.

    cd ~/instagram-bot-2
    tools/data18/.venv/bin/python tools/stream-test/inspect_json.py "https://pornbox.com/contents/127185" --header "X-Requested-With: XMLHttpRequest" --cookie "agree18=1"
    tools/data18/.venv/bin/python tools/stream-test/inspect_json.py saved.json

Writes inspect_json_results.txt (addresses shortened: long path pieces and query values are replaced by their length).
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "inspect_json_results"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
IMG = re.compile(r"https?://[^\s\"'<>]+?\.(?:jpe?g|png|webp|avif)(?:\?[^\s\"'<>]*)?", re.I)


def short(url, keep=14):
    """Readable address without tokens: path pieces longer than `keep` and query values longer than 12 characters become <length>."""
    p = urllib.parse.urlsplit(url)
    path = "/".join(seg if len(seg) <= keep else "<%d>" % len(seg) for seg in p.path.split("/"))
    q = "&".join("%s=%s" % (k, v if len(v) <= 12 else "<%d>" % len(v)) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True))
    return "%s://%s%s%s" % (p.scheme, p.netloc, path, ("?" + q) if q else "")


def identity(url):
    """What makes a picture THE picture, ignoring its size and signature: the path after any token-looking pieces, without the query."""
    segs = [s for s in urllib.parse.urlsplit(url).path.split("/") if s]
    while segs and (len(segs[0]) > 24 or "==" in segs[0] or re.fullmatch(r"[0-9a-f]{16,}", segs[0])):
        segs.pop(0)
    return "/".join(segs) or url


def walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, "%s.%s" % (path, k) if path else str(k))
    elif isinstance(node, list):
        for v in node:
            yield from walk(v, path + "[]")
    elif isinstance(node, str):
        for u in IMG.findall(node):
            yield path, u


def parent_of(node, want_path, want_url, path=""):
    """The dict that holds the first picture at this path (to show what one entry looks like)."""
    if isinstance(node, dict):
        for k, v in node.items():
            here = "%s.%s" % (path, k) if path else str(k)
            if isinstance(v, str) and here == want_path and want_url in v:
                return node
            found = parent_of(v, want_path, want_url, here)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = parent_of(v, want_path, want_url, path + "[]")
            if found is not None:
                return found
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="a JSON address or a file")
    ap.add_argument("--header", action="append", default=[], help='extra request header, e.g. "X-Requested-With: XMLHttpRequest"')
    ap.add_argument("--cookie", help='cookies to send, e.g. "agree18=1"')
    a = ap.parse_args()
    if a.source.startswith("http"):
        h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
        for line in a.header:
            k, _, v = line.partition(":")
            h[k.strip()] = v.strip()
        if a.cookie:
            h["Cookie"] = a.cookie
        with urllib.request.urlopen(urllib.request.Request(a.source, headers=h), timeout=30) as r:
            raw = r.read()
        print("fetched %d KB" % (len(raw) // 1024))
    else:
        raw = Path(a.source).read_bytes()
    data = json.loads(raw)
    groups = OrderedDict()
    everything = []
    for path, url in walk(data):
        everything.append(url)
        groups.setdefault(re.sub(r"\.(?:w|h)?\d+(?:x\d+)?$", ".*", path), []).append(url)     # sizes in sibling fields (w165, w243 ...) count as one place
    distinct = len({identity(u) for u in everything})
    lines = ["Top level: %s" % (", ".join(list(data)[:40]) if isinstance(data, dict) else "list of %d" % len(data)), "",
             "IN TOTAL: %d picture addresses, but only %d different pictures (the rest are the same picture at other sizes)" % (len(everything), distinct), "",
             "WHERE THE PICTURES ARE (field path, how many addresses, how many different pictures, sizes seen):"]
    for path, urls in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:10]:
        ids = Counter(identity(u) for u in urls)
        widths = Counter(dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(u).query)).get("w", "?") for u in urls)
        lines.append("")
        lines.append("  %s" % path)
        lines.append("     %d addresses = %d different pictures (most repeated: %d sizes of one picture)" % (len(urls), len(ids), max(ids.values())))
        lines.append("     widths asked for: %s" % ", ".join("%s x%d" % (w, c) for w, c in widths.most_common(8)))
        lines.append("     e.g. " + short(urls[0]))
        entry = parent_of(data, path, urls[0])
        if isinstance(entry, dict):
            shown = {k: (short(v, 8) if isinstance(v, str) and IMG.search(v) else v) for k, v in list(entry.items())[:6]}
            lines.append("     that entry (first fields): " + json.dumps(shown, default=str)[:420])
        nums = sorted({int(m.group(1)) for u in ids for m in [re.search(r"(\d+)\.(?:jpe?g|png|webp)$", u)] if m})
        if len(nums) > 2:
            lines.append("     picture numbers in the file names: %d..%d (%d different)" % (nums[0], nums[-1], len(nums)))
    if not groups:
        lines.append("  (no picture addresses found in this JSON)")
    text = "\n".join(lines)
    print("\n" + text)
    OUT.with_suffix(".txt").write_text(text + "\n")
    print("\nWritten: %s.txt" % OUT)


if __name__ == "__main__":
    main()
