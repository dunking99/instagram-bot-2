#!/usr/bin/env python3
"""
Downloader used by the UI (a configurable take on the vdh_*.py scripts). Works on macOS and Windows.

  downloader.py <run_config.json>   download links using Chrome + Video DownloadHelper
  downloader.py --pos               print the mouse position after a 5s countdown
  downloader.py --shot NAME FILE    after a 5s countdown, save a small picture of what is under the mouse
                                    (NAME is vdh_icon or download_button); used to find it again later by sight

How it handles big files
------------------------
After each click on Video DownloadHelper's download button, we only wait until a new file *appears* in
the Downloads folder. That file is claimed for that link, and we immediately move on to the next link.
Claimed files are watched in the background; when one finishes (its .crdownload becomes the real file and
stops growing) it is moved into the folder of the link that started it - not whichever link happens to be
current at that moment. Several downloads can run at once (setting: max_parallel).

If a finished file can't be matched to its link with confidence, it is left in Downloads and the log says
so, rather than guessing a folder.

Two download methods (setting "download_method"): "vdh" clicks Video DownloadHelper in Chrome (the code above), "ytdlp"
runs yt-dlp on each link directly: no browser, no clicking, several at once, and each file goes straight into its
creator's folder, so there is nothing to match up afterwards.

Lines starting with "@@OK <url>" tell the UI a download was filed. "@@POS x y" is used by --pos.
Moving the mouse to a screen corner aborts (pyautogui fail-safe).
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
import random
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

try:
    import pyautogui
except ImportError:
    print("pyautogui missing. Run: python3 -m pip install pyautogui")
    sys.exit(1)

PARTIAL = {".part", ".crdownload"}
VIDEO = {".mp4", ".mkv", ".webm"}


def say(msg=""):
    print(msg, flush=True)


def ev(kind, *fields):
    """A line for the dashboard's progress panel (it is not shown in the log). kind: TARGET START PROG DONE FAIL"""
    clean = [str(f).replace("\t", " ").replace("\n", " ") for f in fields]
    print("\t".join(["@@EV", kind] + clean), flush=True)


# ───────────── screen / browser ─────────────

def capture_position():
    for i in range(5, 0, -1):
        say("Move the mouse to the target... %d" % i)
        time.sleep(1)
    x, y = pyautogui.position()
    say("@@POS %d %d" % (x, y))


def _chrome_path_windows():
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            exe = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if exe.exists():
                return str(exe)
    return None


def open_url_in_chrome(url):
    if '"' in url or "\\" in url:
        raise ValueError("unsafe URL")
    if sys.platform == "darwin":
        # macOS: point the front Chrome window's current tab at the link
        script = '''
    tell application "Google Chrome"
        activate
        if (count of windows) = 0 then make new window
        set URL of active tab of front window to "%s"
    end tell
    ''' % url
        subprocess.run(["osascript", "-e", script], check=False)
    elif sys.platform.startswith("win"):
        # Windows: ask Chrome to open the link (a new tab in its current window)
        chrome = _chrome_path_windows()
        if chrome:
            subprocess.Popen([chrome, url])
        else:
            import webbrowser
            webbrowser.open(url)
    else:
        import webbrowser
        webbrowser.open(url)


# ───────────── finding buttons by their picture ─────────────
# The browser toolbar moves (Chrome adds a download icon while a download runs and pushes the extension icons left),
# so a fixed screen position can hit the wrong icon. Instead we save a picture of the icon / button once and look
# for it on screen every time.

SHOT_SIZE = {"vdh_icon": (40, 40), "download_button": (110, 34)}      # size of the saved picture, in screen points
SEARCH_TOP = {"vdh_icon": 220}                                          # the icon is only looked for in the top strip


def _screen():
    """-> (screenshot as a numpy BGR array, pixels per screen point). On a Retina Mac the screenshot has twice as many pixels."""
    import numpy as np
    shot = pyautogui.screenshot()
    scale = shot.width / float(pyautogui.size().width)
    return np.array(shot.convert("RGB"))[:, :, ::-1].copy(), scale      # RGB -> BGR (a Mac screenshot also has an alpha channel)


def capture_shot(name, out):
    import cv2
    w, h = SHOT_SIZE[name]
    for i in range(8 if name == "download_button" else 5, 0, -1):     # the button needs time: open Chrome, open the VDH popup
        say("Put the mouse right on the %s... %d" % ("VDH icon" if name == "vdh_icon" else "Download button", i))
        time.sleep(1)
    x, y = pyautogui.position()
    pyautogui.moveTo(x - 160, y)           # move off it, so the picture isn't of a highlighted (hovered) button
    time.sleep(0.6)
    img, scale = _screen()
    cx, cy = int(x * scale), int(y * scale)
    hw, hh = int(w * scale / 2), int(h * scale / 2)
    crop = img[max(0, cy - hh): cy + hh, max(0, cx - hw): cx + hw]
    if crop.size == 0:
        say("Couldn't take the picture (the mouse was off the screen).")
        return 1
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), crop)
    say("@@IMG %s" % name)
    say("Saved a %dx%d picture of it." % (crop.shape[1], crop.shape[0]))
    return 0


def find_on_screen(template_file, name, threshold):
    """-> ((x, y) screen point of its centre, score) or (None, best score)"""
    import cv2
    import numpy as np
    tpl = cv2.imread(str(template_file))
    if tpl is None:
        return None, 0.0
    img, scale = _screen()
    top = SEARCH_TOP.get(name)
    area = img[: int(top * scale)] if top else img
    if area.shape[0] < tpl.shape[0] or area.shape[1] < tpl.shape[1]:
        return None, 0.0
    res = cv2.matchTemplate(cv2.cvtColor(area, cv2.COLOR_BGR2GRAY), cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY), cv2.TM_CCOEFF_NORMED)
    _, best, _, loc = cv2.minMaxLoc(res)
    if best < threshold:
        return None, float(best)
    if name == "download_button":
        # the popup can list several Download buttons (more than one video found): the page's own video is the top one
        ys, xs = np.where(res >= threshold)
        if len(ys):
            i = int(np.argmin(ys))
            loc = (int(xs[i]), int(ys[i]))
    return ((loc[0] + tpl.shape[1] / 2.0) / scale, (loc[1] + tpl.shape[0] / 2.0) / scale), float(best)


def click_target(name, label, templates, fallback, s, tracker, wait):
    """Click the thing called `name`: found by its picture when we have one, else at the saved position.
    If we have a picture and can't see it, we don't click anywhere: that link is skipped."""
    tpl = Path(templates) / (name + ".png") if templates else None
    if not (s.get("use_image_clicks", True) and tpl and tpl.is_file()):
        pyautogui.click(fallback)
        return
    thr = float(s.get("image_match_threshold", 0.8))
    end, best = time.time() + wait, 0.0
    while True:
        pos, score = find_on_screen(tpl, name, thr)
        best = max(best, score)
        if pos:
            pyautogui.click(pos)
            return
        if time.time() > end:
            raise RuntimeError("couldn't see the %s on screen (best match %.0f%%, needs %.0f%%). Skipped this link; "
                               "re-capture its picture in Settings if this keeps happening" % (label, best * 100, thr * 100))
        tracker.sleep(0.4)


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name) or "unknown"


# ───────────── watching the Downloads folder ─────────────

def scan(downloads):
    """{file name: size} for video files and in-progress downloads in the folder."""
    out = {}
    try:
        with os.scandir(downloads) as it:
            for e in it:
                if Path(e.name).suffix.lower() in VIDEO | PARTIAL:
                    try:
                        if e.is_file():
                            out[e.name] = e.stat().st_size
                    except OSError:
                        pass
    except OSError:
        pass
    return out


def is_partial(name):
    return Path(name).suffix.lower() in PARTIAL


def final_name(name):
    """'X.mp4.crdownload' -> 'X.mp4' (what the browser renames it to when done)"""
    return Path(name).with_suffix("").name if is_partial(name) else name


def unique_dest(folder, name):
    dest = folder / name
    n = 1
    while dest.exists():
        dest = folder / ("%s (%d)%s" % (Path(name).stem, n, Path(name).suffix))
        n += 1
    return dest


class Tracker:
    """Remembers which download belongs to which link, and files each one when it completes."""

    def __init__(self, downloads, library, settings, log_file=None):
        self.downloads, self.library = downloads, library
        self.stable = float(settings.get("stable_seconds", 3))      # size must stop changing this long
        self.max_wait = float(settings.get("max_download_minutes", 40)) * 60
        self.log_file = Path(log_file) if log_file else None
        self.known = set(scan(downloads))   # files already there when we started: never ours
        self.owned = set()                  # file names that belong to a link we started
        self.pending = []                   # downloads in progress
        self.moved = 0
        self.failed = 0

    # -- record of what came from where (ui/data/download_log.jsonl)
    def record(self, event, entry, **extra):
        if not self.log_file:
            return
        try:
            row = dict(t=int(time.time()), event=event, url=entry["url"], folder=entry["folder"], file=entry["name"], **extra)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except Exception:
            pass

    def sleep(self, seconds, step=0.5):
        """Wait, but keep filing finished downloads while we wait."""
        end = time.time() + seconds
        while True:
            self.poll()
            left = end - time.time()
            if left <= 0:
                return
            time.sleep(min(step, left))

    def wait_for_claim(self, url, folder, timeout):
        """After clicking download: wait for the file this link started to appear, and claim it."""
        end = time.time() + timeout
        while time.time() < end:
            self.poll()
            files = scan(self.downloads)
            # if some earlier download just finished under an unknown name, a new finished file is
            # probably its file, not this link's. Only an in-progress file can be claimed in that case.
            ambiguous = any(e.get("lost_since") for e in self.pending)
            fresh = [n for n in files if n not in self.known and n not in self.owned
                     and not (ambiguous and not is_partial(n))]
            if fresh:
                fresh.sort(key=lambda n: (not is_partial(n), n))
                name, now = fresh[0], time.time()
                entry = {"url": url, "folder": folder, "name": name, "size": files[name],
                         "changed": now, "started": now, "lost_since": None}
                self.pending.append(entry)
                ev("START", url, folder)
                self.owned.add(name)
                if is_partial(name):
                    self.owned.add(final_name(name))
                self.record("started", entry)
                return entry
            time.sleep(0.5)
        return None

    def poll(self):
        if getattr(self, "extra_poll", None):
            self.extra_poll()                  # lets yt-dlp downloads (if any are running alongside) be collected too
        if not self.pending:
            return
        files, now = scan(self.downloads), time.time()
        for e in list(self.pending):
            if now - e["started"] > self.max_wait:
                self._give_up(e, "still not finished after %d minutes; left in Downloads as %s"
                              % (self.max_wait // 60, e["name"]))
                continue
            name = e["name"]
            if now - e.get("last_prog", 0) >= 2:
                e["last_prog"] = now
                ev("PROG", e["url"], "-1", "%.1f" % (max(e["size"], 0) / 1e6))
            if name in files:
                if files[name] != e["size"]:
                    e["size"], e["changed"] = files[name], now
                e["lost_since"] = None
                if not is_partial(name):
                    still_partial = any(name + s in files for s in PARTIAL)
                    if not still_partial and now - e["changed"] >= self.stable:
                        self._finish(e)
                continue
            # the file we were watching is gone
            if not is_partial(name):
                self._give_up(e, "the file disappeared before it could be filed (%s)" % name)
                continue
            nxt = final_name(name)
            if nxt in files:                       # normal case: X.mp4.crdownload -> X.mp4
                e.update(name=nxt, size=-1, changed=now, lost_since=None)
                continue
            e["lost_since"] = e.get("lost_since") or now
            self._adopt(e, files, now)

    def _adopt(self, e, files, now):
        """The in-progress file finished under a different name. Take the new file only if it is unambiguous."""
        cands = [n for n in files if not is_partial(n) and n not in self.known and n not in self.owned]
        lost = [x for x in self.pending if x.get("lost_since")]
        if len(cands) == 1 and len(lost) == 1:
            e.update(name=cands[0], size=-1, changed=now, lost_since=None)
            self.owned.add(cands[0])
        elif now - e["lost_since"] > 25:
            self._give_up(e, "it finished, but I can't tell which file it is. Nothing was moved; check Downloads")

    def _finish(self, e):
        dest_dir = self.library / e["folder"]
        src = self.downloads / e["name"]
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = unique_dest(dest_dir, e["name"])
            err = None
            for _ in range(5):                      # Windows can briefly lock a file the browser just closed
                try:
                    shutil.move(str(src), str(dest))
                    err = None
                    break
                except Exception as ex:
                    err = ex
                    time.sleep(1)
            if err:
                raise err
        except Exception as ex:
            self._give_up(e, "couldn't move %s: %s" % (e["name"], ex))
            return
        self.pending.remove(e)
        self.moved += 1
        say("  OK  %s  ->  %s/   (%s)" % (e["name"], e["folder"], e["url"]))
        say("@@OK %s" % e["url"])
        ev("DONE", e["url"], e["name"])
        self.record("moved", e, dest=str(dest))

    def _give_up(self, e, why):
        if e in self.pending:
            self.pending.remove(e)
        self.failed += 1
        say("  FAILED  %s: %s" % (e["url"], why))
        ev("FAIL", e["url"], why)
        self.record("failed", e, reason=why)

    def describe_pending(self):
        return ["%s (%.0f MB so far)" % (e["name"], max(e["size"], 0) / 1e6) for e in self.pending]


# ───────────── method 2: yt-dlp (no browser, no clicking) ─────────────

def ytdlp_command():
    """-> the command that runs yt-dlp, or None"""
    override = os.environ.get("LINKS_YTDLP_BIN")
    if override:
        return [override]
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    for cand in ("/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp", str(Path.home() / ".local/bin/yt-dlp")):
        if Path(cand).exists():
            return [cand]
    try:
        subprocess.run([sys.executable, "-m", "yt_dlp", "--version"], capture_output=True, check=True)
        return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        return None


def _record(log_file, event, url, folder, **extra):
    if not log_file:
        return
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(t=int(time.time()), event=event, url=url, folder=folder, **extra)) + "\n")
    except Exception:
        pass


class YtdlpPool:
    """Runs yt-dlp on links in the background, several at once. Used on its own (every link uses yt-dlp) or alongside
    the Video DownloadHelper clicking (when some sites use one method and some the other)."""

    def __init__(self, cfg):
        import queue
        self.queue_mod = queue
        s = cfg["settings"]
        self.library = Path(s["library_dir"]).expanduser()
        self.log_file = cfg.get("log_file")
        self.height = str(s.get("ytdlp_max_height", "")).strip()
        self.base = ytdlp_command()
        self.running, self.moved, self.failed, self.fails = [], 0, 0, 0
        self.report_every, self.last_report = 30, time.time()     # seconds between "still downloading" lines

    def command(self, url, folder):
        out = str(self.library / folder / "%(title).120B [%(id)s].%(ext)s")
        cmd = self.base + ["--no-playlist", "--no-warnings", "--quiet", "--no-overwrites", "--continue", "--windows-filenames",
                           "--retries", "5", "--fragment-retries", "5", "-N", "4",
                           "--progress", "--newline", "--progress-template",
                           "download:@@PCT %(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s "
                           "%(progress.fragment_index)s %(progress.fragment_count)s",
                           "--print", "after_move:@@FILE\t%(filepath)s", "-o", out]
        if self.height.isdigit():
            cmd += ["-f", "bv*[height<=%s]+ba/b[height<=%s]/b" % (self.height, self.height)]
        return cmd + [url]

    def grab_command(self, url, folder):
        """The page-reading backup (pagegrab.py), for pages yt-dlp can't read"""
        cmd = [sys.executable, "-u", str(Path(__file__).resolve().parent / "pagegrab.py"), "--out", str(self.library / folder)]
        if self.height.isdigit():
            cmd += ["--height", self.height]
        return cmd + [url]

    def launch(self, url, folder, backup=False):
        import threading
        (self.library / folder).mkdir(parents=True, exist_ok=True)
        p = subprocess.Popen(self.grab_command(url, folder) if backup else self.command(url, folder), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace")
        job = {"p": p, "url": url, "folder": folder, "file": None, "lines": [], "q": self.queue_mod.Queue(), "backup": backup,
               "started": time.time(), "pct": None, "bytes": 0, "last_prog": 0.0}
        if not backup:
            ev("START", url, folder)

        def reader():
            for line in p.stdout:
                job["q"].put(line.rstrip("\n"))
            job["q"].put(None)
        threading.Thread(target=reader, daemon=True).start()
        self.running.append(job)

    def settle(self):
        """Collect output and finish whatever has ended."""
        for job in list(self.running):
            while True:
                try:
                    line = job["q"].get_nowait()
                except self.queue_mod.Empty:
                    break
                if line is None:
                    job["eof"] = True
                elif line.startswith("@@FILE\t"):
                    job["file"] = line.split("\t", 1)[1].strip()
                elif line.startswith("@@PCT "):
                    parts = line.split()[1:]
                    num = lambda i: float(parts[i]) if len(parts) > i and re.fullmatch(r"[\d.]+", parts[i]) else 0.0
                    done_b, total_b = num(0), max(num(1), num(2))
                    frag, frags = num(3), num(4)
                    job["bytes"] = done_b
                    job["pct"] = (100.0 * done_b / total_b) if total_b else ((100.0 * frag / frags) if frags else None)
                elif line.strip():
                    job["lines"].append(line.strip())
            if job["p"].poll() is None and time.time() - job["last_prog"] >= 1.5:
                job["last_prog"] = time.time()
                ev("PROG", job["url"], "-1" if job["pct"] is None else "%.1f" % min(job["pct"], 99.9), "%.1f" % (job["bytes"] / 1e6))
            if job["p"].poll() is not None and job.get("eof"):
                self.running.remove(job)
                if job["p"].returncode == 0 and job["file"]:
                    self.moved += 1
                    self.fails = 0
                    name = Path(job["file"]).name
                    say("  OK  %s  ->  %s/   (%s)" % (name, job["folder"], job["url"]))
                    say("@@OK %s" % job["url"])
                    ev("DONE", job["url"], name)
                    _record(self.log_file, "moved", job["url"], job["folder"], file=name, dest=job["file"])
                elif (not job["backup"] and any(("flashvars" in l or "Unable to extract" in l or "No video formats found" in l or "Unsupported URL" in l) for l in job["lines"])):
                    # yt-dlp doesn't understand this site's page: read the video's own address from the page instead
                    say("  yt-dlp can't read this page, so trying the page's own video address instead: %s" % job["url"])
                    try:
                        self.launch(job["url"], job["folder"], backup=True)
                    except Exception as e:
                        self.failed += 1
                        self.fails += 1
                        say("  FAILED  %s: %s" % (job["url"], e))
                        ev("FAIL", job["url"], str(e)[:200])
                else:
                    self.failed += 1
                    self.fails += 1
                    why = (job["lines"][-1] if job["lines"] else "exit code %s" % job["p"].returncode)[:220]
                    say("  FAILED  %s: %s" % (job["url"], why))
                    ev("FAIL", job["url"], why)
                    _record(self.log_file, "failed", job["url"], job["folder"], file="", reason=why)
        self.report()

    def written_mb(self, job):
        """MB written into this creator's folder since the job started (the partly downloaded file counts)."""
        total = 0
        try:
            for f in (self.library / job["folder"]).iterdir():
                try:
                    st = f.stat()
                    if st.st_mtime >= job["started"] - 2 and f.is_file():
                        total += st.st_size
                except OSError:
                    pass
        except OSError:
            pass
        return total / 1e6

    def report(self):
        """A long download prints nothing for minutes, which looks stuck: say what is going on every so often."""
        now = time.time()
        if not self.running or now - self.last_report < self.report_every:
            return
        self.last_report = now
        for job in self.running:
            say("  still downloading (%d s, %.0f MB so far): %s" % (now - job["started"], self.written_mb(job), job["url"]))

    def stop_all(self):
        for job in self.running:
            job["p"].terminate()
        for job in self.running:
            try:
                job["p"].wait(timeout=5)
            except Exception:
                job["p"].kill()
        n = len(self.running)
        if n:
            say("%d yt-dlp download(s) were cut off. A partly downloaded file (.part) may be left in the creator's folder." % n)
        self.running = []


def run_ytdlp(cfg):
    """Every link in this run uses yt-dlp."""
    s, links = cfg["settings"], cfg["links"]
    target = int(cfg["target_success"])
    pool_ = YtdlpPool(cfg)
    if not pool_.base:
        say("yt-dlp isn't installed (or isn't on the PATH). Install it with: brew install yt-dlp   (or switch the download method back to Video DownloadHelper in Settings)")
        return 1
    max_parallel = max(1, int(s.get("max_parallel", 3)))
    gap = float(s.get("pause_between_links", 3))
    max_fails = int(s.get("stop_after_failures", 4))
    say("Loaded %d links. Target: %d downloads, up to %d at a time. Using yt-dlp: no browser or clicking needed, so you can use the computer."
        % (len(links), target, max_parallel))
    ev("TARGET", target)
    pool, attempts, last_start = list(links), 0, 0.0
    try:
        while True:
            pool_.settle()
            stop_launching = (pool_.moved + len(pool_.running) >= target or attempts >= s["max_attempts"] or not pool
                              or (max_fails and pool_.fails >= max_fails))
            if not stop_launching and len(pool_.running) < max_parallel and time.time() - last_start >= gap:
                item = pool.pop(0)
                attempts += 1
                url, folder = item["url"], safe_name(item.get("folder") or item["creator"])
                say("\n[%d filed, %d in progress / target %d] Attempt %d\nURL: %s\nFolder: %s"
                    % (pool_.moved, len(pool_.running), target, attempts, url, folder))
                pool_.launch(url, folder)
                last_start = time.time()
                continue
            if stop_launching and not pool_.running:
                break
            time.sleep(0.4)
        if max_fails and pool_.fails >= max_fails:
            say("\nStopping: %d links in a row failed. Check the messages above (a site change, a network problem, or yt-dlp needing an update: brew upgrade yt-dlp)." % pool_.fails)
    except KeyboardInterrupt:
        say("\nStopped.")
        pool_.stop_all()
    say("\n===== FINISHED: %d filed, %d failed, %d attempts =====" % (pool_.moved, pool_.failed, attempts))
    return 0


# ───────────── the run ─────────────

def run(config_path):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    s = cfg["settings"]
    default_method = s.get("download_method", "vdh")
    methods = {(l.get("method") or default_method) for l in cfg["links"]}
    if methods == {"ytdlp"}:
        def on_term(signum, frame):
            raise KeyboardInterrupt()
        try:
            signal.signal(signal.SIGTERM, on_term)
        except Exception:
            pass
        return run_ytdlp(cfg)
    links = cfg["links"]
    target = int(cfg["target_success"])
    downloads = Path(s["download_dir"]).expanduser()
    library = Path(s["library_dir"]).expanduser()
    icon, button = tuple(s["vdh_icon"]), tuple(s["download_button"])
    templates = cfg.get("templates_dir")
    max_parallel = max(1, int(s.get("max_parallel", 3)))
    gap = float(s.get("pause_between_links", 3))

    if not downloads.is_dir():
        say("Download folder not found: %s" % downloads)
        return 1

    tracker = Tracker(downloads, library, s, cfg.get("log_file"))
    ypool = YtdlpPool(cfg) if "ytdlp" in methods else None      # some links use yt-dlp, the rest the clicking
    if ypool and not ypool.base:
        say("Some of these links are set to use yt-dlp, but it isn't installed (brew install yt-dlp). Those links will fail.")
    if ypool:
        tracker.extra_poll = ypool.settle
    n_y = lambda: len(ypool.running) if ypool else 0
    done_y = lambda: ypool.moved if ypool else 0

    def on_terminate(signum, frame):
        raise KeyboardInterrupt()
    try:
        signal.signal(signal.SIGTERM, on_terminate)
    except Exception:
        pass

    say("Loaded %d links. Target: %d downloads, up to %d at a time." % (len(links), target, max_parallel))
    ev("TARGET", target)
    say("Starting in %d seconds. Make sure Chrome is open and maximised." % s["startup_delay"])
    time.sleep(s["startup_delay"])

    pool, attempts, last_wait_msg = list(links), 0, 0.0
    fails, max_fails = 0, int(s.get("stop_after_failures", 4))   # in a row; resets whenever a download starts
    try:
        while attempts < s["max_attempts"] and pool:
            tracker.poll()
            if tracker.moved + done_y() + len(tracker.pending) + n_y() >= target:
                break                                   # enough are done or on their way
            if max_fails and ypool and ypool.fails >= max_fails:
                say("\nStopping: %d yt-dlp links in a row failed. Check the messages above." % ypool.fails)
                break
            if len(tracker.pending) + n_y() >= max_parallel:    # all slots busy: wait for one to finish
                if time.time() - last_wait_msg > 30:
                    say("  %d downloads in progress; waiting for a free slot..." % (len(tracker.pending) + n_y()))
                    last_wait_msg = time.time()
                tracker.sleep(1.0)
                continue

            attempts += 1
            item = pool.pop(0)
            url, folder = item["url"], safe_name(item.get("folder") or item["creator"])
            via = item.get("method") or default_method
            say("\n[%d filed, %d in progress / target %d] Attempt %d  (%s)\nURL: %s\nFolder: %s"
                % (tracker.moved + done_y(), len(tracker.pending) + n_y(), target, attempts,
                   "yt-dlp" if via == "ytdlp" else "Video DownloadHelper", url, folder))
            if via == "ytdlp":
                try:
                    ypool.launch(url, folder)            # no browser, no clicking for this one
                except Exception as e:
                    ypool.failed += 1
                    ypool.fails += 1
                    say("  Error: %s" % e)
                    ev("FAIL", url, str(e)[:200])
                tracker.sleep(gap)
                continue
            try:
                open_url_in_chrome(url)
                tracker.sleep(s["page_load_wait"])
                say("  -> Clicking VDH icon...")
                click_target("vdh_icon", "VDH icon", templates, icon, s, tracker, 3)
                tracker.sleep(s["menu_wait"])
                say("  -> Clicking Download...")
                click_target("download_button", "Download button", templates, button, s, tracker, 4)
                claimed = tracker.wait_for_claim(url, folder, s["download_wait"])
                if not claimed:
                    ev("FAIL", url, "No download started (nothing new appeared in the Downloads folder)")
                if claimed:
                    fails = 0
                    say("  Started: %s  (in progress: %d) - moving on, it will be filed in %s/ when done"
                        % (claimed["name"], len(tracker.pending), folder))
                else:
                    fails += 1
                    say("  No new file appeared")
            except pyautogui.FailSafeException:
                say("Aborted (mouse moved to screen corner).")
                return 1
            except Exception as e:
                fails += 1
                say("  Error: %s" % e)
                ev("FAIL", url, str(e)[:200])
            if max_fails and fails >= max_fails:
                say("\nStopping: %d links in a row didn't start a download. Common causes: Video DownloadHelper's free-plan limit "
                    "(its popup shows 'Next download: …' and no Download button), a changed popup, or Chrome not in front. "
                    "Check the popup, then run again." % fails)
                break
            tracker.sleep(gap * random.uniform(1.0, 1.6))

        # everything is started; now wait for the rest to finish and be filed
        if tracker.pending or n_y():
            say("\nAll links started. Waiting for %d download(s) to finish..." % (len(tracker.pending) + n_y()))
        last = time.time()
        while tracker.pending or n_y():
            tracker.sleep(2)
            if time.time() - last > 30:
                say("  still downloading: " + "; ".join(tracker.describe_pending()))
                last = time.time()
    except KeyboardInterrupt:
        say("\nStopped.")
        if ypool:
            ypool.stop_all()
    finally:
        if tracker.pending:
            say("\n%d download(s) were not filed yet. They may still be in your Downloads folder:" % len(tracker.pending))
            for line in tracker.describe_pending():
                say("   " + line)

    say("\n===== FINISHED: %d filed, %d failed, %d attempts =====" % (tracker.moved + done_y(), tracker.failed + (ypool.failed if ypool else 0), attempts))
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--shot":
        sys.exit(capture_shot(sys.argv[2], sys.argv[3]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "--pos":
        capture_position()
    elif len(sys.argv) >= 2:
        sys.exit(run(sys.argv[1]))
    else:
        print(__doc__)
