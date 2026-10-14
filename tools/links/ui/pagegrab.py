#!/usr/bin/env python3
"""
Download a video straight from its page, for sites whose player settings yt-dlp can't read.

  pagegrab.py [--height N] [--probe] --out DIR URL

Many sites list the video's own file addresses in the page itself (video_url / video_alt_url ... with a quality
label such as 720p). This reads them, picks the best quality (not above --height, if given), and saves the file as
"<title> [<id>].mp4" in DIR.

Prints "@@FILE<TAB><path>" when it has saved a file, and "ERROR: ..." (exit code 1) when it can't.
--probe only checks that the chosen address answers (it fetches the first kilobyte) and saves nothing.
"""
import sys

sys.dont_write_bytecode = True

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import os
import re
import shutil
import subprocess
import tempfile
import html as htmllib
from pathlib import Path
from urllib.parse import urlparse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
MAX_BYTES = 8 * 1024 ** 3


# Some sites answer Python's web library with an error but answer curl normally, so curl does the fetching when it exists
# (it is built into macOS and recent Windows). The Python way is the backup.

CURL = shutil.which("curl")


def curl_get_text(url, jar, referer=None):
    r = subprocess.run([CURL, "-sL", "--compressed", "--max-time", "40", "-A", UA, "-c", jar, "-b", jar] + (["-e", referer] if referer else [])
                       + ["-w", "\n@@STATUS %{http_code}", url], capture_output=True)
    body = r.stdout.decode("utf-8", "replace")
    body, _, status = body.rpartition("\n@@STATUS ")
    if r.returncode != 0 or not status.strip().startswith("2"):
        raise RuntimeError("HTTP %s%s" % (status.strip() or "?", " (curl exit %d)" % r.returncode if r.returncode else ""))
    return body


def curl_probe(address, referer, jar):
    r = subprocess.run([CURL, "-sL", "--max-time", "40", "-A", UA, "-e", referer, "-b", jar, "-r", "0-1023", "-o", os.devnull,
                        "-w", "%{http_code} %{content_type} %{size_download}", address], capture_output=True)
    code, ctype, size = (r.stdout.decode().split(" ") + ["?", "?", "0"])[:3]
    return int(code) if code.isdigit() else 0, ctype, int(size) if size.isdigit() else 0


def curl_download(address, referer, jar, dest):
    """Download with curl, printing "@@PCT <bytes so far> <total>" about once a second so the dashboard can show a bar."""
    import time
    hdr = dest.with_suffix(".hdr")
    p = subprocess.Popen([CURL, "-sL", "-f", "-A", UA, "-e", referer, "-b", jar, "-D", str(hdr), "-o", str(dest), "-w", "%{content_type}", address],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    total = 0
    while p.poll() is None:
        time.sleep(1)
        if not total and hdr.exists():
            found = re.findall(r"(?im)^content-length:\s*(\d+)", hdr.read_text(errors="replace"))
            total = int(found[-1]) if found else 0
        try:
            print("@@PCT %d %d NA NA NA" % (dest.stat().st_size, total), flush=True)
        except OSError:
            pass
    ctype = (p.stdout.read() or b"").decode(errors="replace").split(";")[0].strip().lower()
    try:
        hdr.unlink()
    except OSError:
        pass
    if p.returncode != 0:
        raise RuntimeError("curl exit %d (the site refused or the connection dropped)" % p.returncode)
    return ctype


def fail(msg):
    print("ERROR: %s" % msg)
    sys.exit(1)


def player_options(page):
    """-> [(height in pixels, address)] from the player settings (video_url, video_alt_url, video_alt_url2 ...)"""
    out = []
    for m in re.finditer(r"\b(video(?:_alt)?_url\d*)\s*:\s*'([^']+)'", page):
        key, addr = m.group(1), m.group(2)
        label = re.search(r"\b%s_text\s*:\s*'([^']*)'" % re.escape(key), page)
        h = re.search(r"(\d{3,4})", label.group(1)) if label else None
        out.append((int(h.group(1)) if h else 0, addr))
    return out


def page_title(page):
    m = re.search(r'"@type"\s*:\s*"VideoObject".*?"name"\s*:\s*"((?:[^"\\]|\\.)*)"', page, re.S)
    if m:
        try:
            return htmllib.unescape(json.loads('"%s"' % m.group(1)))
        except Exception:
            pass
    m = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    return htmllib.unescape(m.group(1)).strip() if m else ""


def json_ld_content_url(page):
    m = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', page)
    return m.group(1) if m else None


def clean_name(s, limit=120):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", s).strip(" .")
    return re.sub(r"\s+", " ", s)[:limit].strip() or "video"



def same_site(a, b):
    host = lambda u: ".".join((urlparse(u).hostname or "").split(".")[-2:])
    return host(a) == host(b)


def find_embeds(page, page_url):
    """Player pages this page embeds (many sites keep the video address only there)."""
    from urllib.parse import urljoin
    out = []
    for m in re.finditer(r"""<iframe[^>]+src=["']([^"']*embed[^"']*)["']""", htmllib.unescape(page), re.I):
        u = urljoin(page_url, m.group(1))
        if same_site(u, page_url) and u not in out:
            out.append(u)
    return out[:2]


def find_master(text, base):
    """The first segmented-stream playlist (.m3u8) address in a page."""
    from urllib.parse import urljoin
    m = re.search(r"""(?:https?:)?//[^"'\s<>\\]+?\.m3u8[^"'\s<>\\]*""", text.replace("&amp;", "&").replace("\\/", "/"))
    return urljoin(base, m.group(0)) if m else None


def ytdlp_bin():
    return shutil.which("yt-dlp") or next((c for c in ("/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp") if os.path.exists(c)), None)


def stream_download(master, referer, height, final, probe):
    """Save a segmented stream as one mp4 with yt-dlp (prints @@PCT / @@FILE lines like the main downloader)."""
    exe = ytdlp_bin()
    if not exe:
        fail("yt-dlp is needed for this site's stream (brew install yt-dlp)")
    fmt = "bv*[height<=%s]+ba/b[height<=%s]/b" % (height, height) if height else "bv*+ba/b"
    if probe:
        r = subprocess.run([exe, "--no-warnings", "--referer", referer, "-F", master], capture_output=True, text=True)
        print("stream found (segmented); formats:\n" + "\n".join(l for l in r.stdout.splitlines() if "x" in l or "p" in l)[:600])
        return 0 if r.returncode == 0 else 1
    cmd = [exe, "--no-warnings", "--quiet", "--no-overwrites", "--continue", "--referer", referer, "--add-header", "User-Agent:" + UA,
           "-f", fmt, "--merge-output-format", "mp4", "--retries", "5", "--fragment-retries", "5", "-N", "4", "--progress", "--newline",
           "--progress-template", "download:@@PCT %(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s "
           "%(progress.fragment_index)s %(progress.fragment_count)s", "--print", "after_move:@@FILE\t%(filepath)s",
           "-o", str(final.with_suffix("")) + ".%(ext)s", master]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    got = False
    for line in p.stdout:
        line = line.rstrip("\n")
        if line.startswith("@@FILE\t"):
            got = True
        print(line, flush=True)
    p.wait()
    if p.returncode != 0 or not got:
        fail("the stream download failed (yt-dlp exit %s)" % p.returncode)
    return 0


def main(argv):
    import requests
    args = list(argv)
    probe = "--probe" in args
    if probe:
        args.remove("--probe")
    height, outdir = None, None
    if "--height" in args:
        i = args.index("--height")
        height = int(args[i + 1]) if args[i + 1].isdigit() else None
        del args[i:i + 2]
    if "--out" in args:
        i = args.index("--out")
        outdir = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 1 or (outdir is None and not probe):
        print(__doc__)
        return 2
    url = args[0]

    jar = os.path.join(tempfile.gettempdir(), "pagegrab_%d.cookies" % os.getpid())
    s = requests.Session()
    s.headers["User-Agent"] = UA
    page, via_curl = None, False
    if CURL:
        try:
            page, via_curl = curl_get_text(url, jar), True
        except Exception as e:
            err = str(e)
    if page is None:
        try:
            r = s.get(url, timeout=30)
            r.raise_for_status()
            page = r.text
        except Exception as e:
            fail("couldn't load the page: %s" % (err if CURL and 'err' in dir() else e))

    options = [(h, a) for h, a in player_options(page)]
    if any(a.startswith("function/") for _, a in options):
        fail("this site hides its video addresses (they need decoding), so they can't be read from the page")
    options = [(h, a) for h, a in options if a.startswith("http")]
    if not options:
        ld = json_ld_content_url(page)
        if ld and ld.startswith("http") and ".m3u8" not in ld:
            options = [(0, ld)]
    if not options:                                               # the address may only be in the player page this page embeds
        master, where = find_master(page, url), url
        for emb in ([] if master else find_embeds(page, url)):
            try:
                ep = curl_get_text(emb, jar, referer=url) if CURL else s.get(emb, headers={"Referer": url}, timeout=30).text
            except Exception:
                continue
            found = [(h, a) for h, a in player_options(ep) if a.startswith("http")]
            if found:
                options, page_for_files = found, ep
                break
            master, where = find_master(ep, emb), emb
            if master:
                break
        if not options:
            if not master:
                fail("no video address found in the page")
            vid = Path(urlparse(url).path.rstrip("/")).name or "video"
            final = outdir / ("%s [%s].mp4" % (clean_name(page_title(page) or vid), clean_name(vid, 60))) if outdir else Path("x.mp4")
            if outdir:
                outdir.mkdir(parents=True, exist_ok=True)
                if final.exists():
                    print("@@FILE\t%s" % final)
                    return 0
            return stream_download(master, where, height, final, probe)
    options.sort(key=lambda x: x[0])
    pool = [o for o in options if not height or not o[0] or o[0] <= height] or options[:1]
    quality, address = pool[-1]

    headers = {"Referer": url, "Accept": "*/*"}
    if probe:
        print("options found: %s" % ", ".join("%sp" % h if h else "unlabelled" for h, _ in options))
        if via_curl:
            code, ctype, got = curl_probe(address, url, jar)
        else:
            resp = s.get(address, headers=dict(headers, Range="bytes=0-1023"), timeout=30, stream=True)
            code, ctype, got = resp.status_code, resp.headers.get("Content-Type", "?"), len(resp.raw.read(1024))
        print("chosen: %s -> HTTP %s, %s, first %d bytes read" % ("%sp" % quality if quality else "unlabelled", code, ctype, got))
        return 0 if code in (200, 206) else 1

    vid = Path(urlparse(url).path.rstrip("/")).name or Path(urlparse(address).path.rstrip("/")).stem
    name = "%s [%s].mp4" % (clean_name(page_title(page) or vid), clean_name(vid, 60))
    outdir.mkdir(parents=True, exist_ok=True)
    final = outdir / name
    if final.exists():
        print("@@FILE\t%s" % final)
        return 0
    part = final.with_suffix(".mp4.part")
    if via_curl:
        try:
            ctype = curl_download(address, url, jar, part)
            if ctype.startswith("text/") or "html" in ctype or "json" in ctype:
                part.unlink()
                fail("the address didn't return a video (%s)" % ctype)
            part.replace(final)
        except SystemExit:
            raise
        except Exception as e:
            try:
                part.unlink()
            except OSError:
                pass
            fail("download failed: %s" % e)
        print("@@FILE\t%s" % final)
        return 0
    try:
        with s.get(address, headers=headers, timeout=60, stream=True) as resp:
            resp.raise_for_status()
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype.startswith("text/") or "html" in ctype or "json" in ctype:
                fail("the address didn't return a video (%s)" % (ctype or "unknown type"))
            total = 0
            with open(part, "wb") as f:
                for chunk in resp.iter_content(1024 * 256):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        fail("file is larger than %d GB, stopped" % (MAX_BYTES // 1024 ** 3))
                    f.write(chunk)
            want = int(resp.headers.get("Content-Length") or 0)
            if want and total < want:
                fail("the download stopped early (%d of %d bytes)" % (total, want))
        part.replace(final)
    except SystemExit:
        raise
    except Exception as e:
        try:
            part.unlink()
        except OSError:
            pass
        fail("download failed: %s" % e)
    print("@@FILE\t%s" % final)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
