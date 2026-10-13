"""
Simple local UI for random_post.py.

Run:
    python3 app_v2.py

This is the redesigned interface. It starts a web page on http://localhost:8502 (this machine only) and opens it in your
browser. It is a thin front end: every search runs `random_post.py` as a subprocess, so the
command line keeps working exactly as before.
"""
import datetime
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).parent
PORT = 8502
NOISE = ("NotOpenSSLWarning", "warnings.warn", "use_fast", "urllib3")  # harmless startup chatter


# --- Launcher: `python3 app_v2.py` starts Streamlit for us ------------------------------
def _launch() -> None:
    threading.Timer(2.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve()),
                    "--server.headless", "true", "--server.address", "127.0.0.1",
                    "--server.port", str(PORT), "--browser.gatherUsageStats", "false",
                    "--theme.base", "dark", "--theme.primaryColor", "#f2784b",
                    "--theme.backgroundColor", "#121110", "--theme.secondaryBackgroundColor", "#1a1816",
                    "--theme.textColor", "#ece6dc", "--theme.linkColor", "#f2a07f",
                    "--theme.font", "Instrument Sans, sans-serif",
                    "--theme.headingFont", "Instrument Serif, serif",
                    "--theme.baseRadius", "0.65rem"], cwd=HERE)


try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    _inside_streamlit = get_script_run_ctx() is not None
except ImportError:
    sys.exit("Streamlit isn't installed. Run: python3 -m pip install streamlit")

if not _inside_streamlit:
    if __name__ == "__main__":
        _launch()
    sys.exit(0)

import streamlit as st  # noqa: E402  (only imported once we know we're running inside Streamlit)


# --- Helpers -----------------------------------------------------------------------
def build_command(usernames, count, query, top, worst, save_dir, all_slides, margin,
                  include_videos, combine, refresh, full, like=None, like_weight=0.5,
                  pose=None, mirror=True, scene_top=30, tags=(), min_conf=0.5,
                  take_all=False, limit=0, expand=0, even=False, after=None, before=None, clip_seconds=None, mix_videos=False, video_mix=None) -> list:
    """Turn the form values into a random_post.py command line."""
    cmd = [sys.executable, "random_post.py", *usernames, "--count", str(count), "--no-open"]
    if expand:
        cmd += ["--expand-carousels", str(expand)]
    if take_all:
        cmd.append("--all")
        if limit:
            cmd += ["--limit", str(limit)]
    for tag in tags:
        cmd += ["--tag", tag]
    if tags:
        cmd += ["--min-conf", str(min_conf)]
    if query or like or pose:
        if pose:
            cmd += ["--pose", str(pose)]
            if not mirror:
                cmd.append("--no-mirror")
            if query or like:
                cmd += ["--scene-top", str(scene_top)]
        if query:
            cmd += ["--find", query]
        if like:
            cmd += ["--like", str(like)]
            if query:
                cmd += ["--like-weight", str(like_weight)]
        cmd += ["--top", str(top)]
        if worst:
            cmd.append("--worst")
    if save_dir:
        cmd += ["--save", str(save_dir)]
        if all_slides:
            cmd.append("--all-slides")
            if margin is not None:                 # None = let the script choose (looser for images)
                cmd += ["--slide-margin", str(margin)]
    if include_videos:
        cmd.append("--include-videos")
    if clip_seconds is not None:
        cmd += ["--clip-seconds", str(clip_seconds)]
    if mix_videos:
        cmd.append("--mix-videos")
    if video_mix is not None:
        cmd += ["--video-mix", str(video_mix)]
    if after:
        cmd += ["--after", str(after)]
    if before:
        cmd += ["--before", str(before)]
    if even:
        cmd.append("--even")
    elif combine:
        cmd.append("--combine")
    if full:
        cmd.append("--full")
    elif refresh:
        cmd.append("--refresh")
    return cmd


def run_streaming(cmd, log_box) -> tuple:
    """Run cmd, streaming its output into log_box. Returns (exit code, all output lines)."""
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(cmd, cwd=HERE, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = []
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if line and not any(n in line for n in NOISE):
                lines.append(line)
                log_box.code("\n".join(lines[-14:]), language=None)
        proc.wait()
    finally:                                   # the Stop button / a page refresh lands here
        if proc.poll() is None:
            proc.terminate()
    return proc.returncode, lines


def parse_results(lines) -> tuple:
    """Pull post links out of the script's output: ({filename: url}, [(user, url)])."""
    files, links, last_url = {}, [], None
    for line in lines:
        m = re.match(r"\s*saved (\S+)\s+<-\s+(https://\S+)", line)
        if m:
            files[m.group(1)], last_url = m.group(2), m.group(2)
            continue
        m = re.match(r"\s+saved (\S+)$", line)            # extra carousel slide
        if m and last_url:
            files[m.group(1)] = last_url
            continue
        m = re.match(r"\s+\[(.+?)\]\s+(https://\S+)(?:\s+\(slide (\d+)\))?(?:\s+score ([-\d.]+))?", line)
        if m:
            links.append((m.group(1), m.group(2), m.group(3), m.group(4)))
    return files, links


def active_model() -> str:
    return os.environ.get("RPP_MODEL", "siglip")


def index_files(account) -> list:
    """The account's photo-index files, the active model's first. Either one means it is set up."""
    cache = HERE / "cache"
    names = [active_model()] + [m for m in ("siglip", "clip") if m != active_model()]
    return [f for f in (cache / f"{account}.{m}.npz" for m in names) if f.exists()]


@st.cache_data(show_spinner=False)
def index_posts(account, stamp) -> list:
    """The account's posts (not carousel slides), read from its photo index."""
    try:
        import numpy as np
        paths = np.load(index_files(account)[0], allow_pickle=False)["paths"]
        return [str(p) for p in paths if "/@" not in str(p)]
    except (OSError, ValueError, KeyError, IndexError):
        return []


def saved_accounts() -> list:
    """Every account we hold data for: anything with a photo index or a saved post list."""
    import json
    cache = HERE / "cache"
    names = {f.name.split(".")[0] for m in ("siglip", "clip") for f in cache.glob(f"*.{m}.npz")}
    names |= {f.stem for f in cache.glob("*.json") if f.name.count(".") == 1}
    rows = []
    for name in sorted(names):
        ready = bool(index_files(name))
        try:
            n = len(json.loads((cache / f"{name}.json").read_text())["links"])
        except (OSError, ValueError, KeyError):
            n = len(index_posts(name, index_files(name)[0].stat().st_mtime)) if ready else 0
        rows.append({"account": name, "posts cached": n, "photo search ready": ready, "videos only": False})
    import random_post as rp
    for name in rp.watched_collections():                      # watched video folders sit in the same list
        w = rp.load_watch(name)
        if w["attached"]:                                      # videos attached to an account: note them on its row
            for r in rows:
                if r["account"] == name:
                    r["videos"] = len(w["videos"])
            continue
        rows.append({"account": name, "posts cached": len(w["videos"]),
                     "photo search ready": True, "videos only": True})
    return sorted(rows, key=lambda r: r["account"])


POSE_TAGS = ["standing", "sitting", "kneeling", "lying down", "on all fours",
             "bending over", "leaning", "upper body only"]


def tag_options() -> dict:
    """{facet: [labels]} for the tag pickers: labels.json plus the built-in pose tags."""
    import json
    try:
        data = json.loads((HERE / "labels.json").read_text())
        options = {facet: list(labels) for facet, labels in data.items()}
    except (OSError, ValueError, TypeError):
        options = {}
    options["pose"] = POSE_TAGS
    options["arms"] = ["arms up"]
    return options


def thumb_for(user, url, slide):
    """The saved thumbnail (or, for a carousel slide, the saved slide image) of a result."""
    m = re.search(r"/(?:p|reel|reels)/([\w-]+)", url)
    code = (m.group(1) if m else "") + (f"@{slide}" if slide else "")
    return HERE / "cache" / "thumbs" / user.lower() / f"{code}.jpg"


def slide_progress(account) -> tuple:
    """(posts opened, posts to open in total, extra photos indexed) for 'index every image'."""
    import json
    cache = HERE / "cache"

    def load(name, key):
        try:
            return json.loads((cache / f"{account}.{name}.json").read_text())[key]
        except (OSError, ValueError, KeyError):
            return {}
    idx = index_files(account)
    links = index_posts(account, idx[0].stat().st_mtime if idx else 0)
    if not links:
        return 0, 0, 0
    kinds, done = load("kinds", "kinds"), load("expanded", "posts")
    todo = [p for p in links if not re.search(r"/(reel|reels)/", p) and kinds.get(p, "carousel") == "carousel"]
    return (sum(1 for p in todo if p in done), len(todo),
            sum(max(v.get("slides", 1) - 1, 0) for v in done.values()))


# --- Background jobs: long tasks run as a separate process so the page stays usable ---------
JOB_DIR = HERE / "cache" / "jobs"
JOB_FILE = JOB_DIR / "current.json"


@st.cache_resource
def _procs() -> dict:
    """Process handles of jobs started by this server (so finished ones get reaped)."""
    return {}


def read_job():
    try:
        return json.loads(JOB_FILE.read_text())
    except (OSError, ValueError):
        return None


def job_alive(info) -> bool:
    proc = _procs().get(info["pid"])
    if proc is not None:
        return proc.poll() is None
    try:
        os.kill(info["pid"], 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def start_job(cmd, label) -> None:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    log = JOB_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.log"
    with open(log, "w") as fh:
        proc = subprocess.Popen(cmd, cwd=HERE, env={**os.environ, "PYTHONUNBUFFERED": "1"},
                                stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
    _procs()[proc.pid] = proc
    JOB_FILE.write_text(json.dumps({"pid": proc.pid, "label": label, "log": str(log),
                                    "started": time.time()}))


def stop_job(info) -> None:
    try:
        os.killpg(info["pid"], signal.SIGTERM)           # the job and the browser it started
    except ProcessLookupError:
        pass


def job_log(info, n=14) -> list:
    try:
        lines = Path(info["log"]).read_text().splitlines()
    except OSError:
        return []
    return [l for l in lines if l.strip() and not any(x in l for x in NOISE)][-n:]


@st.fragment(run_every=3)
def _gb(n) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e8 else f"{n / 1e6:.0f} MB"


@st.cache_data(show_spinner=False, ttl=60)
def folder_sizes() -> dict:
    """Bytes used by each top-level item of the project folder (cached for a minute)."""
    def size(path) -> int:
        total = 0
        try:
            with os.scandir(path) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        total += size(e.path) if e.is_dir(follow_symlinks=False) else e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
        return total
    out = {}
    for e in os.scandir(HERE):
        if e.name.startswith(".") and e.name != ".streamlit":
            continue
        out[e.name] = size(e.path) if e.is_dir(follow_symlinks=False) else e.stat(follow_symlinks=False).st_size
    sub = {}
    thumbs = HERE / "cache" / "thumbs"
    for e in (os.scandir(thumbs) if thumbs.exists() else []):
        if e.is_dir():
            sub[f"cache/thumbs/{e.name}"] = size(e.path)
    return {"top": out, "thumbs": sub}


def storage_badge() -> None:
    """Top-right: size of this project folder, and used / free space on the Mac."""
    sizes = folder_sizes()
    mine = sum(sizes["top"].values())
    disk = shutil.disk_usage(HERE)
    low = "Low space · " if disk.free < 5e9 else ""
    with st.popover(f"{low}{_gb(disk.free)} free · {_gb(mine)} used here", icon=":material/hard_drive:",
                    width="stretch"):
        st.markdown(f"**This project folder:** {_gb(mine)}  \n"
                    f"**Mac storage:** {_gb(disk.used)} used of {_gb(disk.total)}  \n"
                    f"**Free:** {_gb(disk.free)} ({disk.free / disk.total:.0%})")
        st.progress(min(1.0, disk.used / disk.total))
        if disk.free < 5e9:
            st.error("Storage is almost full. Importing and indexing need free space to work.")
        rows = sorted(sizes["top"].items(), key=lambda kv: kv[1], reverse=True)[:8]
        st.caption("Biggest items in the project folder")
        for name, n in rows:
            if n >= 1e6:
                st.write(f"`{name}` · {_gb(n)}")
        top_thumbs = sorted(sizes["thumbs"].items(), key=lambda kv: kv[1], reverse=True)[:5]
        if top_thumbs:
            st.caption("Largest saved-image folders")
            for name, n in top_thumbs:
                st.write(f"`{name}` · {_gb(n)}")
        if st.button("Recalculate", key="storage_refresh"):
            folder_sizes.clear()
            st.rerun()


def job_panel() -> None:
    """Live status of the background job. Refreshes by itself without touching the rest of the page."""
    info = read_job()
    if not info:
        return
    running = job_alive(info)
    lines = job_log(info)
    minutes = int((time.time() - info["started"]) / 60)
    progress = next((re.search(r"Progress: (\d+) / (\d+)", l) for l in reversed(lines)
                     if re.search(r"Progress: (\d+) / (\d+)", l)), None)
    with st.container(border=True):
        head, act = st.columns([6, 1], vertical_alignment="center")
        head.markdown(f"**{'Running' if running else 'Finished'}: {info['label']}**"
                      f" ({minutes} min{' so far' if running else ' ago'})")
        if progress:
            done, total = int(progress.group(1)), int(progress.group(2))
            st.progress(min(done / total, 1.0) if total else 1.0,
                        text=next(l for l in reversed(lines) if "Progress:" in l))
        with st.expander("Log", expanded=running):
            st.code("\n".join(lines) or "Starting...", language=None)
        if running:
            if act.button("Stop", key="job_stop", icon=":material/stop:", width="stretch"):
                stop_job(info)
                st.rerun(scope="fragment")
        elif act.button("Dismiss", key="job_dismiss", width="stretch"):
            JOB_FILE.unlink(missing_ok=True)
            st.rerun()
    if st.session_state.get("job_was_running") and not running:
        st.session_state["job_was_running"] = False
        st.rerun()                                       # refresh counts, sidebar and progress bars
    st.session_state["job_was_running"] = running


def run_helper(script, *args) -> str:
    out = subprocess.run([sys.executable, script, *args], cwd=HERE, capture_output=True, text=True)
    return "\n".join(l for l in (out.stdout + out.stderr).splitlines()
                     if l.strip() and not any(n in l for n in NOISE))


@st.cache_data(show_spinner=False)
def preview_image(path, mtime) -> bytes:
    """A small JPEG for the page (the saved files are ~1440 px wide)."""
    import io
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((560, 700))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return buf.getvalue()


@st.cache_data(show_spinner=False)
def slide_data_url(path, mtime) -> str:
    """The image as a data: URL, sized for a full-screen slideshow."""
    import base64
    import io
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((1200, 1200))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


SLIDESHOW_HTML = """
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{--bg:#121110;--s1:#1a1816;--s2:#252220;--line:#33302b;--text:#ece6dc;--muted:#a1998c;--accent:#f2784b}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--text);font-family:'Instrument Sans',system-ui,sans-serif}
  #stage{position:relative;height:100vh;background:#000;display:flex;flex-direction:column;border-radius:14px;overflow:hidden}
  #view{flex:1;min-height:0;display:flex;align-items:center;justify-content:center}
  #view img,#view video{max-width:100%;max-height:100%;object-fit:contain;user-select:none}
  #view video{display:none;width:100%;height:100%;background:#000}
  #prog{height:3px;background:var(--accent);width:0}
  #bar{display:flex;align-items:center;gap:8px;padding:10px 14px;background:var(--s1);font-size:14px;flex-wrap:wrap;border-top:1px solid var(--line)}
  #bar button,#bar select{background:var(--s2);color:var(--text);border:1px solid var(--line);border-radius:10px;
    padding:0 12px;height:36px;font:inherit;font-size:14px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;transition:border-color .15s,background .15s}
  #bar button:hover,#bar select:hover{border-color:var(--accent);background:#2d2926}
  #bar button:focus-visible,#bar select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  #bar svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
  #cap{flex:1;min-width:120px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 6px}
  #count{color:var(--muted);font-variant-numeric:tabular-nums;padding-right:6px}
  .icon{width:36px;padding:0!important;justify-content:center}
</style>
<div id="stage">
  <div id="view"><img id="img" alt=""><video id="vid" controls playsinline></video></div>
  <div id="prog"></div>
  <div id="bar">
    <button id="prev" class="icon" title="Previous (left arrow)" aria-label="Previous"><svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg></button>
    <button id="play" class="icon" title="Play / pause (space)" aria-label="Play or pause"></button>
    <button id="next" class="icon" title="Next (right arrow)" aria-label="Next"><svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg></button>
    <select id="secs" title="Seconds per image" aria-label="Seconds per image">
      <option value="2">2 s</option><option value="3">3 s</option><option value="5" selected>5 s</option>
      <option value="8">8 s</option><option value="15">15 s</option>
    </select>
    <button id="shuf" title="Shuffle the order (s)"><svg viewBox="0 0 24 24"><path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>Shuffle</button>
    <span id="cap"></span><span id="count"></span>
    <button id="fs" title="Full screen (f)"><svg viewBox="0 0 24 24"><path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/></svg>Full screen</button>
  </div>
</div>
<script>
const items = __ITEMS__;
const ICON_PAUSE = '<svg viewBox="0 0 24 24"><path d="M8 5v14M16 5v14"/></svg>';
const ICON_PLAY = '<svg viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z"/></svg>';
let order = items.map((_, i) => i), pos = 0, playing = true, timer = null, started = 0;
const $ = id => document.getElementById(id);
$("play").innerHTML = ICON_PAUSE;
function secs(){ return parseInt($("secs").value, 10) * 1000; }
function show(){
  const it = items[order[pos]], vid = $("vid"), img = $("img");
  vid.pause();
  if (it.video){
    img.style.display = "none"; vid.style.display = "block"; vid.src = it.video;
    vid.onended = () => { if (playing) go(1); };
    if (playing) vid.play().catch(() => { vid.muted = true; vid.play().catch(() => {}); });
  } else {
    vid.style.display = "none"; vid.removeAttribute("src"); vid.load(); img.style.display = ""; img.src = it.src;
  }
  $("cap").textContent = it.cap;
  $("count").textContent = (pos + 1) + " / " + items.length;
  restart();
}
function restart(){
  clearInterval(timer); $("prog").style.width = "0"; started = Date.now();
  if (!playing || items[order[pos]].video) return;      // a video plays to its end, then moves on
  timer = setInterval(() => {
    const f = (Date.now() - started) / secs();
    $("prog").style.width = Math.min(100, f * 100) + "%";
    if (f >= 1) go(1);
  }, 60);
}
function go(d){ pos = (pos + d + order.length) % order.length; show(); }
function toggle(){
  playing = !playing; $("play").innerHTML = playing ? ICON_PAUSE : ICON_PLAY; restart();
  const vid = $("vid");
  if (items[order[pos]].video){ if (playing) vid.play().catch(() => {}); else vid.pause(); }
}
function shuffle(){
  for (let i = order.length - 1; i > 0; i--){ const j = Math.floor(Math.random() * (i + 1)); [order[i], order[j]] = [order[j], order[i]]; }
  pos = 0; show();
}
function fullscreen(){
  if (document.fullscreenElement) document.exitFullscreen();
  else $("stage").requestFullscreen && $("stage").requestFullscreen();
}
$("prev").onclick = () => go(-1); $("next").onclick = () => go(1);
$("play").onclick = toggle; $("shuf").onclick = shuffle; $("fs").onclick = fullscreen;
$("secs").onchange = restart;
document.addEventListener("keydown", e => {
  if (e.key === "ArrowRight") go(1);
  else if (e.key === "ArrowLeft") go(-1);
  else if (e.key === " "){ e.preventDefault(); toggle(); }
  else if (e.key === "f") fullscreen();
  else if (e.key === "s") shuffle();
});
show();
</script>
"""


def slideshow_clip(user, url, clips, secs):
    """The video clip for a result that is a video (a frame of an imported video, or a watched video), else None."""
    import random_post as rp
    key = url.replace("https://www.instagram.com", "", 1)
    if (HERE / "cache" / f"{user.lower()}.watch.json").exists():
        wv = rp.watched_video(user, key)
        if wv:
            got = clips.get((key, secs))
            if not got or (got[1] and not Path(got[1]).exists()):
                got = clips[(key, secs)] = rp.cut_window(wv, secs, rp.CLIPS_DIR / f"watch_{wv['id']}_{int(time.time() * 1000)}.mp4",
                                                         wv.get("start"))
            start, clip = got
            if clip:
                return clip
            if wv["duration"] <= secs:                                # a short video: the whole file
                return Path(wv["file"])
            return None
        return None
    if key not in _video_frames(user, _stamp(HERE / "cache" / f"{user.lower()}.videos.json")):
        return None
    return rp.make_clip(user, key, secs)


@st.cache_data(show_spinner=False)
def video_data_url(path, mtime) -> str:
    import base64
    return "data:video/mp4;base64," + base64.b64encode(Path(path).read_bytes()).decode()


VIDEO_BUDGET = 480 * 1024 * 1024        # most video bytes put into one slideshow page (base64 adds a third; stays under the 700 MB message limit)


def slideshow(items, key, bar=None) -> None:
    """items: [(image file, caption, clip file or None)]. Images are shown for the chosen time; a clip
    plays through to its end. Arrow keys, pause, shuffle and full screen are in the player."""
    import streamlit.components.v1 as components
    data, used, skipped = [], 0, 0
    for n, (f, cap, clip) in enumerate(items, 1):
        if bar is not None:
            bar.progress(0.6 + 0.4 * n / len(items), text=f"Packing the slideshow: {n} / {len(items)}")
        if not f.exists():
            continue
        entry = {"src": slide_data_url(str(f), f.stat().st_mtime), "cap": cap}
        if clip is not None and Path(clip).exists():
            size = Path(clip).stat().st_size
            if used + size <= VIDEO_BUDGET:
                entry["video"] = video_data_url(str(clip), Path(clip).stat().st_mtime)
                used += size
            else:
                skipped += 1
        data.append(entry)
    if not data:
        st.info("Nothing to show.")
        return
    if bar is not None:
        bar.progress(1.0, text="Sending to the browser... the slideshow appears when this finishes")
    components.html(SLIDESHOW_HTML.replace("__ITEMS__", json.dumps(data)), height=720)
    st.caption("Click inside the slideshow first, then: arrow keys = previous / next, space = pause, "
               "S = shuffle, F = full screen. Videos play to the end before moving on."
               + (f" {skipped} video(s) were left as still images to keep the page light." if skipped else ""))


def index_stamp(account) -> tuple:
    """Changes whenever an account's indexes or labels.json change (so cached breakdowns refresh)."""
    files = [HERE / "cache" / f"{account}.clip.npz", HERE / "cache" / f"{account}.siglip.npz",
             HERE / "cache" / f"{account}.pose.npz",
             HERE / "cache" / f"{account}.kinds.json", HERE / "cache" / f"{account}.expanded.json",
             HERE / "labels.json"]
    return tuple(f.stat().st_mtime if f.exists() else 0 for f in files)


@st.cache_data(show_spinner=False)
def get_breakdown(account, conf, stamp, version=2, model="siglip") -> dict:
    """Tag counts for one account, from `random_post.py --list-tags --json`."""
    import json
    out = subprocess.run([sys.executable, "random_post.py", account, "--list-tags", "--json",
                          "--min-conf", str(conf)], cwd=HERE, capture_output=True, text=True)
    for line in out.stdout.splitlines():
        if line.startswith("@@JSON@@"):
            return json.loads(line[len("@@JSON@@"):])
    return {"error": "\n".join(l for l in (out.stdout + out.stderr).splitlines()
                               if l.strip() and not any(n in l for n in NOISE))[-600:]}


# --- Favourites ---------------------------------------------------------------------
FAV_DIR = HERE / "favourites"
FAV_DB = FAV_DIR / "favourites.json"


def load_favs() -> dict:
    try:
        return json.loads(FAV_DB.read_text())
    except (OSError, ValueError):
        return {}


def save_favs(favs: dict) -> None:
    FAV_DIR.mkdir(exist_ok=True)
    FAV_DB.write_text(json.dumps(favs, indent=1))


def fav_id(account, stem) -> str:
    return f"{account.lower()}:{stem}"


def toggle_fav(account, stem, src, url) -> None:
    """Star or un-star an image. Starring copies the picture into favourites/<account>/."""
    favs, fid = load_favs(), fav_id(account, stem)
    if fid in favs:
        (HERE / favs[fid]["file"]).unlink(missing_ok=True)
        del favs[fid]
    else:
        dest = FAV_DIR / account.lower() / f"{stem}{Path(src).suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        favs[fid] = {"account": account.lower(), "stem": stem, "url": url,
                     "file": str(dest.relative_to(HERE)), "added": time.time()}
    save_favs(favs)


def image_actions(ctx, account, stem, src, url, dl_name) -> None:
    """A star (favourite) button and a download button, side by side, for one image."""
    fid = fav_id(account, stem)
    starred = fid in FAVS
    c1, c2 = st.columns([1, 3])
    c1.button("", key=f"{'favon' if starred else 'favoff'}_{ctx}_{fid}", on_click=toggle_fav,
              icon=":material/star:", type="tertiary",
              args=(account, stem, str(src), url),
              help="Remove from favourites" if starred else "Add to favourites")
    c2.download_button("Download", Path(src).read_bytes(), file_name=dl_name, icon=":material/download:",
                       mime="image/png" if Path(src).suffix == ".png" else "image/jpeg",
                       key=f"dl_{ctx}_{fid}", on_click="ignore", type="tertiary")


@st.cache_data(show_spinner=False)
def _local_sources(account, stamp) -> dict:
    try:
        return json.loads((HERE / "cache" / f"{account.lower()}.local.json").read_text())["source"]
    except (OSError, ValueError, KeyError):
        return {}


def _stamp(f) -> float:
    return f.stat().st_mtime if f.exists() else 0


@st.cache_data(show_spinner=False)
def _video_frames(account, stamp) -> set:
    """Index keys of the frames that come from imported videos."""
    try:
        return set(json.loads((HERE / "cache" / f"{account.lower()}.videos.json").read_text())["frames"])
    except (OSError, ValueError, KeyError):
        return set()


CLIP_LENGTHS = {"15 seconds": 15, "30 seconds": 30, "1 minute": 60, "2 minutes": 120,
                "5 minutes": 300, "Full video": 0}
DEFAULT_CLIP = "15 seconds"


@st.cache_data(show_spinner=False, ttl=20)
def folder_status() -> list:
    """[(collection, [folders], number of new files waiting)] for every collection imported from folders."""
    import random_post as rp
    return [(n, rp.load_folders(n)["folders"], len(rp.pending_files(n))) for n in rp.imported_collections()]


def auto_import_on() -> bool:
    try:
        return bool(json.loads((HERE / "cache" / "settings.json").read_text()).get("auto_import"))
    except (OSError, ValueError):
        return False


def set_auto_import(on) -> None:
    f = HERE / "cache" / "settings.json"
    try:
        data = json.loads(f.read_text())
    except (OSError, ValueError):
        data = {}
    data["auto_import"] = bool(on)
    f.write_text(json.dumps(data))


def post_date_text(url) -> str:
    """' · posted 18 Apr 2022' for an Instagram post link (empty for imported images)."""
    import random_post as rp
    t = rp.post_time(url.replace("https://www.instagram.com", "", 1))
    return time.strftime(" · posted %d %b %Y", time.gmtime(t)) if t else ""


def reveal(path) -> None:
    subprocess.run(["open", "-R", str(path)])


def source_link(account, url, ctx) -> None:
    """'Open on Instagram' for Instagram images; 'Show in Finder' for images from an imported folder."""
    key = url.replace("https://www.instagram.com", "", 1)
    wf = HERE / "cache" / f"{account.lower()}.watch.json"
    if wf.exists():                                    # a watched video folder: play it, or reveal the file
        import random_post as rp
        wv = rp.watched_video(account, key)
        if wv:
            st.button("Show in Finder", key=f"rv_{ctx}_{key}", on_click=reveal, args=(wv["file"],), icon=":material/folder_open:", type="tertiary")
            play = f"play_{ctx}_{key}"
            if st.button("Hide video" if st.session_state.get(play) else "Play", key=f"clip_{ctx}_{key}", icon=":material/play_arrow:"):
                st.session_state[play] = None if st.session_state.get(play) else True
                st.rerun()
            if st.session_state.get(play):
                secs = CLIP_LENGTHS[st.session_state.get("clip_len", DEFAULT_CLIP)]
                pick = st.session_state.get(f"{play}_pick")
                if not pick or pick[0] != secs:                 # a random window, kept while the page re-renders
                    start, clip = rp.cut_window(wv, secs, rp.CLIPS_DIR / f"watch_{wv['id']}_{int(time.time() * 1000)}.mp4",
                                                wv.get("start"))
                    pick = st.session_state[f"{play}_pick"] = (secs, wv.get("start") or start, clip)
                _, start, clip = pick
                if clip:
                    st.video(Path(clip).read_bytes())
                else:
                    st.video(str(wv["file"]), start_time=int(start))
            return
    f = HERE / "cache" / f"{account.lower()}.local.json"
    key = url.replace("https://www.instagram.com", "", 1)
    original = _local_sources(account, f.stat().st_mtime if f.exists() else 0).get(key)
    if original:
        st.button("Show in Finder", key=f"rv_{ctx}_{key}", on_click=reveal, args=(original,), icon=":material/folder_open:", type="tertiary")
        if key in _video_frames(account, _stamp(HERE / "cache" / f"{account.lower()}.videos.json")):
            play = f"play_{ctx}_{key}"
            if st.button("Hide clip" if st.session_state.get(play) else "Play clip", key=f"clip_{ctx}_{key}", icon=":material/play_arrow:"):
                st.session_state[play] = not st.session_state.get(play)
                st.rerun()
            if st.session_state.get(play):
                import random_post as rp
                secs = CLIP_LENGTHS[st.session_state.get("clip_len", DEFAULT_CLIP)]
                clip = rp.make_clip(account, key, secs)
                if clip:
                    if secs:
                        st.video(clip.read_bytes())
                    else:                               # the whole video, starting at the matched moment
                        info = rp.video_frame(account, key)
                        st.video(str(clip), start_time=int(info["t"]))
                else:
                    st.caption("The clip could not be cut (is the video file still where it was?).")
    else:
        st.markdown(f"[Open on Instagram ↗]({url})")


def thumb_for_path(account, path):
    """Saved image for an index key such as /user/p/CODE/ or /p/CODE/@3, and its Instagram link."""
    code = re.search(r"/(?:p|reel|reels)/([\w-]+)", path).group(1)
    slide = re.search(r"/@(\d+)$", path)
    name = code + (f"@{slide.group(1)}" if slide else "")
    return (HERE / "cache" / "thumbs" / account.lower() / f"{name}.jpg",
            "https://www.instagram.com" + re.sub(r"/@\d+$", "/", path), int(slide.group(1)) if slide else None)


def pick_tag(acct, facet, label) -> None:
    """A tag row was clicked: select it, replace its group's tag, or ask how to combine."""
    sel = st.session_state.setdefault(f"sel_{acct}", [])
    tag = (facet, label)
    st.session_state[f"shown_{acct}"] = 24
    st.session_state[f"pending_{acct}"] = None
    if tag in sel:
        sel.remove(tag)
    elif not sel:
        sel.append(tag)
    elif any(f == facet for f, _ in sel):                 # an image has one tag per group: swap it
        st.session_state[f"sel_{acct}"] = [t for t in sel if t[0] != facet] + [tag]
    else:
        st.session_state[f"pending_{acct}"] = tag         # different group: ask


def resolve_pending(acct, combine) -> None:
    tag = st.session_state.get(f"pending_{acct}")
    if tag:
        sel = st.session_state.get(f"sel_{acct}", [])
        st.session_state[f"sel_{acct}"] = (sel + [tag]) if combine else [tag]
    st.session_state[f"pending_{acct}"] = None
    st.session_state[f"shown_{acct}"] = 24


def clear_selection(acct) -> None:
    st.session_state[f"sel_{acct}"] = []
    st.session_state[f"pending_{acct}"] = None


def tag_text(tags) -> str:
    return " + ".join("no confident " + f if l is None else l for f, l in tags)


def show_breakdown(info, acct) -> None:
    """Metrics, then one card per tag group. Every tag row is a button that opens its images."""
    if "error" in info:
        st.error(info["error"] or "Couldn't read this account's index.")
        return
    total = info["photos"] + info.get("slides", 0)            # every image: posts + carousel slides
    m = st.columns(4)
    m[0].metric("Photo posts", f"{info['photos']:,}")
    m[1].metric("Reels (not counted)", f"{info['reels']:,}")
    if info.get("carousels") is not None:
        m[2].metric("Carousels", f"{info['carousels']:,}", help=f"{info['expanded']} looked inside so far")
        m[3].metric("Extra slide photos indexed", f"{info['slides']:,}")
    else:
        m[2].metric("Carousels", "?", help="Not detected yet. Use the button below to find them.")
    st.caption(f"{total:,} images in total. Click a tag to see its images.")
    sel = st.session_state.get(f"sel_{acct}", [])
    uid = re.sub(r"\W", "", acct)
    css = []
    facets = info["facets"]
    layout = [["setting"], ["outfit", "shot"], ["pose", "arms"]]
    for col, group in zip(st.columns(3), layout):
        with col:
            for facet in group:
                if facet not in facets:
                    continue
                data = facets[facet]
                rows = [(label, n) for label, n in sorted(data["counts"].items(), key=lambda kv: -kv[1])]
                if data["untagged"] is not None:
                    rows.append((None, data["untagged"]))
                peak = max([n for _, n in rows] + [0.25 * total, 1])
                with st.container(border=True):
                    st.markdown(f"**{facet.capitalize()}**")
                    for i, (label, n) in enumerate(rows):
                        key = f"bd_{uid}_{facet}_{i}"
                        chosen = (facet, label) in sel
                        fill = n / peak * 100
                        base = "rgba(242,120,75,.55)" if chosen else "rgba(242,120,75,.28)"
                        css.append(f".st-key-{key} button {{ justify-content: flex-start; text-align: left; "
                                   f"border: 2px solid {'#f2784b' if chosen else 'transparent'}; "
                                   f"border-radius: 10px; font-size: 1.02rem; "
                                   f"background: linear-gradient(90deg, {base} {fill:.1f}%, "
                                   f"rgba(128,128,128,.14) {fill:.1f}%); }} "
                                   f".st-key-{key} button:hover {{ border-color: #f2784b; }}")
                        name = "no confident tag" if label is None else label
                        st.button(f"{name}   {n}  ({n / total:.0%})", key=key, width="stretch",
                                  disabled=n == 0, on_click=pick_tag, args=(acct, facet, label))
    st.markdown("<style>" + " ".join(css) + "</style>", unsafe_allow_html=True)
    show_gallery(info, acct)


def show_gallery(info, acct) -> None:
    """The images carrying the selected tags, with a question when a second group is added."""
    sel = st.session_state.get(f"sel_{acct}", [])
    pending = st.session_state.get(f"pending_{acct}")
    if pending:
        with st.container(border=True):
            st.markdown(f"You picked **{tag_text(sel)}**. Now **{tag_text([pending])}**: show it on its "
                        f"own, or only the images that have both?")
            q1, q2, q3 = st.columns(3)
            q1.button(f"Just {tag_text([pending])}", key=f"pq1_{acct}", on_click=resolve_pending,
                      args=(acct, False), width="stretch")
            q2.button(f"{tag_text(sel)} + {tag_text([pending])}", key=f"pq2_{acct}",
                      on_click=resolve_pending, args=(acct, True), width="stretch")
            q3.button("Cancel", key=f"pq3_{acct}", on_click=lambda: st.session_state.update(
                {f"pending_{acct}": None}), width="stretch")
    if not sel:
        return
    matches = []
    for path, tags in info["items"].items():
        confs = []
        for facet, label in sel:
            got = tags.get(facet)
            if label is None:
                if got:
                    break
            elif not got or got[0] != label:
                break
            else:
                confs.append(got[1])
        else:
            matches.append((min(confs) if confs else 0.0, path))
    matches.sort(reverse=True)
    h1, h2 = st.columns([5, 1])
    h1.subheader(f"{len(matches):,} images: {tag_text(sel)}")
    h2.button("Clear", key=f"clr_{acct}", on_click=clear_selection, args=(acct,))
    shown = st.session_state.get(f"shown_{acct}", 24)
    for start in range(0, min(shown, len(matches)), 4):
        for col, (conf, path) in zip(st.columns(4), matches[start:min(start + 4, shown, len(matches))]):
            f, url, slide = thumb_for_path(acct, path)
            with col:
                if f.exists():
                    st.image(preview_image(str(f), f.stat().st_mtime))
                else:
                    st.caption("No saved image.")
                tags = info["items"][path]
                st.caption(" · ".join(v[0] for k, v in tags.items() if k != "arms")
                           + (f" · slide {slide}" if slide else ""))
                source_link(acct, url, f"gal_{acct}")
                if f.exists():
                    image_actions(f"gal_{acct}", acct, f.stem, f, url,
                                  f"{acct}_{f.stem.replace('@', '_s')}.jpg")
    if shown < len(matches):
        st.button(f"Show more ({len(matches) - shown:,} left)", key=f"more_{acct}",
                  on_click=lambda: st.session_state.update({f"shown_{acct}": shown + 24}))


CSS = ''':root{--bg:#121110;--s1:#1a1816;--s2:#252220;--line:#33302b;--text:#ece6dc;--muted:#a1998c;--accent:#f2784b;--good:#8fbf7a;}
::selection{background:var(--accent);color:#1a0d07}
*{caret-color:var(--accent)}
html{scrollbar-color:#3a3631 transparent}
*::-webkit-scrollbar{width:10px;height:10px}
*::-webkit-scrollbar-thumb{background:#3a3631;border-radius:10px;border:2px solid var(--bg)}
.stApp{background:var(--bg)}
[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1480px;padding:2.2rem 2.4rem 5rem}
@media (max-width:760px){.block-container{padding:1.2rem 1rem 4rem}}
h1,h2,h3{letter-spacing:-.01em}
.brand{font-family:'Instrument Serif',Georgia,serif;font-size:2.5rem;line-height:1.05;color:var(--text);margin:0}
.brand-sub{color:var(--muted);font-size:.95rem;margin-top:.25rem}
.sec{font-family:'Instrument Serif',Georgia,serif;font-size:1.7rem;line-height:1.15;margin:1.6rem 0 .2rem;color:var(--text)}
.sec-sub{color:var(--muted);font-size:.95rem;margin-bottom:.9rem;max-width:70ch}
/* tabs as a quiet nav */
.stTabs [data-baseweb="tab-list"]{gap:.4rem;border-bottom:1px solid var(--line)}
.stTabs [data-baseweb="tab"]{height:auto;padding:.7rem 1rem;border-radius:10px 10px 0 0}
.stTabs [data-baseweb="tab"] p{font-size:1.02rem;font-weight:500;color:var(--muted)}
.stTabs [aria-selected="true"] p{color:var(--text)}
.stTabs [data-baseweb="tab-highlight"]{background:var(--accent);height:2px}
.stTabs [data-baseweb="tab-border"]{display:none}
/* panels */
.st-key-searchcard,.st-key-panel_count{background:var(--s1);border:1px solid var(--line);border-radius:16px;padding:1.1rem 1.2rem}
[data-testid="stExpander"]{border:1px solid var(--line);border-radius:14px;background:var(--s1)}
[data-testid="stExpander"] summary{padding:.8rem 1rem}
[data-testid="stExpander"] summary p{font-weight:500}
/* buttons and inputs */
.stButton>button,.stDownloadButton>button,[data-testid="stPopover"]>button{border-radius:10px;border:1px solid var(--line);background:var(--s2);transition:border-color .15s,background .15s,transform .15s}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stPopover"]>button:hover{border-color:var(--accent);background:#2d2926}
.stButton>button:active{transform:translateY(1px)}
.stButton>button[kind="primary"]{background:var(--accent);border-color:var(--accent);color:#1a0d07;font-weight:600}
.stButton>button[kind="primary"]:hover{background:#ff8a5e;border-color:#ff8a5e}
.stButton>button[kind="tertiary"]{border-color:transparent;background:transparent;color:var(--muted)}
.stButton>button[kind="tertiary"]:hover{color:var(--text);background:var(--s2)}
:focus-visible{outline:2px solid var(--accent)!important;outline-offset:2px}
[data-baseweb="input"],[data-baseweb="select"]>div,[data-baseweb="textarea"]{border-radius:10px}
/* sticky find bar */
.st-key-findbar{position:sticky;bottom:.8rem;z-index:50;background:rgba(26,24,22,.92);backdrop-filter:blur(10px);border:1px solid var(--line);border-radius:16px;padding:.7rem 1rem;box-shadow:0 12px 32px rgba(0,0,0,.45)}
.findsum{color:var(--muted);font-size:.95rem}
.findsum b{color:var(--text);font-weight:600;font-variant-numeric:tabular-nums}
/* images */
[data-testid="stImage"] img{border-radius:12px}
[data-testid="stCheckbox"] label p{font-size:.88rem;color:var(--muted)}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums}
[data-testid="stCaptionContainer"]{color:var(--muted)}
[class*="st-key-favoff_"] button,[class*="st-key-favon_"] button{padding:.2rem .45rem;min-height:2.3rem}
[class*="st-key-favon_"] button{color:#f5b301}
[class*="st-key-favon_"] [data-testid="stIconMaterial"]{font-variation-settings:'FILL' 1}
.empty{border:1px dashed var(--line);border-radius:16px;padding:2.4rem 1.6rem;text-align:center;color:var(--muted);margin-top:1.4rem}
.empty b{display:block;color:var(--text);font-family:'Instrument Serif',Georgia,serif;font-size:1.5rem;font-weight:400;margin-bottom:.3rem}
.stat{display:inline-block;margin-right:1.4rem;color:var(--muted);font-size:.92rem}
.stat b{color:var(--text);font-variant-numeric:tabular-nums}
'''


# --- Page --------------------------------------------------------------------------
st.set_page_config(page_title="Random Post Picker", page_icon=":material/casino:", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("<style>@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700"
            "&family=Instrument+Serif&display=swap');</style>", unsafe_allow_html=True)
st.markdown("<style>" + CSS + "</style>", unsafe_allow_html=True)

_t1, _t2 = st.columns([3, 2], vertical_alignment="center")
_t1.markdown('<div class="brand">Random Post Picker</div>'
             '<div class="brand-sub">Search, filter and shuffle your photo and video library.</div>',
             unsafe_allow_html=True)
with _t2:
    storage_badge()
_job = read_job()
job_running = bool(_job) and job_alive(_job)
job_panel()
FAVS = load_favs()
rows = saved_accounts()

with st.sidebar:
    st.header("Settings")
    _labels = {"siglip": "SigLIP (default)", "clip": "CLIP (older)"}
    _pick = st.selectbox("Photo search model", ["siglip", "clip"], format_func=_labels.get,
                         index=["siglip", "clip"].index(active_model()), key="model_pick",
                         help="Each model keeps its own index for every account, so you can switch "
                              "back and forth. The first time an account is opened with a model, its "
                              "index is built from the saved images (a few minutes per 1,000).")
    os.environ["RPP_MODEL"] = _pick        # background jobs and searches started now use this model
    st.divider()
    st.subheader("Instagram login")
    if not (HERE / "auth.json").exists():
        st.warning("Not logged in yet.")
    if st.button("Check which account I'm using", width="stretch"):
        with st.spinner("Checking..."):
            st.info(run_helper("whoami.py"))
    if st.button("Log in / switch account", width="stretch"):
        st.info("A browser window will open. Log in there (including 2FA).")
        with st.spinner("Waiting for you to log in (up to 3 minutes)..."):
            st.info(run_helper("login.py", "--timeout", "180"))

PILOT_DIR = HERE / "pilot"


def load_pilot() -> list:
    try:
        return json.loads((PILOT_DIR / "results.json").read_text())
    except (OSError, ValueError):
        return []


def load_overrides() -> dict:
    try:
        return json.loads((PILOT_DIR / "overrides.json").read_text())
    except (OSError, ValueError):
        return {}


def set_pile(uuid, pile) -> None:
    """Your decision for one screenshot (pile = 'keep' or 'junk'); 'auto' removes it."""
    ov = load_overrides()
    if pile == "auto":
        ov.pop(uuid, None)
    else:
        ov[uuid] = pile
    (PILOT_DIR / "overrides.json").write_text(json.dumps(ov))


def _fmt_dur(sec) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


@st.fragment(run_every=3)
def watched_panel() -> None:
    """Checks every watched folder every few seconds; new videos appear here by themselves."""
    import random_post as rp
    names = rp.watched_collections()
    if not names:
        st.markdown('<div class="empty"><b>No folders are being watched yet</b>'
                    'Add one above and its videos appear here within seconds.</div>', unsafe_allow_html=True)
        return
    for name in names:
        try:
            rp.scan_watched(name)
        except Exception as e:                     # a bad file must never stop the panel
            st.warning(f"{name}: {e}")
        d = rp.load_watch(name)
        vids = sorted(d["videos"].items(), key=lambda kv: kv[1]["added"], reverse=True)
        with st.container(border=True):
            h1, h2, h3, h4 = st.columns([4, 2, 2, 1], vertical_alignment="center")
            h1.markdown(f"**{name}** · {len(vids)} video(s)" + (" · attached to the account" if d["attached"] else "")
                        + f"  \n`{d['folder']}`")
            length = h2.selectbox("Random clip length", list(CLIP_LENGTHS), key=f"wlen_{name}", label_visibility="collapsed")
            if h3.button("Random clip", key=f"wrand_btn_{name}", disabled=not vids, icon=":material/shuffle:"):
                st.session_state[f"wrand_{name}"] = rp.random_segment(name, CLIP_LENGTHS[length])
            if h4.button("Stop", key=f"wstop_{name}", help="Stop watching this folder (your files are untouched)"):
                rp.watch_path(name).unlink(missing_ok=True)
                st.rerun(scope="app")
            pick = st.session_state.get(f"wrand_{name}")
            if pick:
                file, start, clip = pick
                st.caption(f"{Path(file).name} · from {_fmt_dur(start)}")
                if clip:
                    st.video(Path(clip).read_bytes())
                else:
                    st.video(str(file), start_time=int(start))
            for row in range(0, min(len(vids), 60), 5):
                for col, (vid, v) in zip(st.columns(5), vids[row:row + 5]):
                    with col:
                        poster = rp.poster_file(name, vid)
                        if poster.exists():
                            st.image(str(poster))
                        st.caption(f"{Path(v['file']).name} · {_fmt_dur(v['duration'])}")
                        key = f"wplay_{name}_{vid}"
                        b1, b2 = st.columns(2)
                        if b1.button("Hide" if st.session_state.get(key) else "Play", key=f"wbtn_{name}_{vid}",
                                     icon=":material/play_arrow:", width="stretch"):
                            st.session_state[key] = not st.session_state.get(key)
                        b2.button("Finder", key=f"wfind_{name}_{vid}", on_click=reveal, args=(v["file"],),
                                  icon=":material/folder_open:", width="stretch")
                        if st.session_state.get(key):
                            st.video(v["file"])
            if len(vids) > 60:
                st.caption(f"Showing the newest 60 of {len(vids)}.")


if auto_import_on() and not job_running and not st.session_state.get("auto_import_checked"):
    st.session_state["auto_import_checked"] = True      # once per browser session
    if any(n for _, _, n in folder_status()):
        start_job([sys.executable, "random_post.py", "--import-new"], "Importing new files from your folders")
        st.rerun()


def section(title, sub="") -> None:
    st.markdown(f'<div class="sec">{title}</div>' + (f'<div class="sec-sub">{sub}</div>' if sub else ""),
                unsafe_allow_html=True)


tab_find, tab_bd, tab_lib, tab_fav = st.tabs(["Discover", "Breakdown", "Library", "Favourites"])

# =====================================================================================
# DISCOVER: build a search, see results
# =====================================================================================
with tab_find:
    indexed_accounts = [r["account"] for r in rows if r["photo search ready"]]
    col_a, col_b = st.columns([3, 2], gap="large")
    with col_a:
        with st.container(key="searchcard"):
            chosen_accounts = st.multiselect("Accounts", indexed_accounts, accept_new_options=True,
                                             key="accounts_pick", placeholder="Choose accounts, or type a new username and press Enter",
                                             help="Pick one or more accounts that are already set up, or type a "
                                                  "new username and press Enter.")
            sel_a, sel_b, _ = st.columns([1.2, 1, 5])
            sel_a.button("Select all", key="accounts_all", disabled=not indexed_accounts, type="tertiary",
                         on_click=lambda: st.session_state.update(accounts_pick=list(indexed_accounts)))
            sel_b.button("Clear", key="accounts_none", disabled=not chosen_accounts, type="tertiary",
                         on_click=lambda: st.session_state.update(accounts_pick=[]))
            query = st.text_input("Describe what to find (optional)",
                                  placeholder="e.g. smiling on a beach, red dress, mirror selfie. Empty = fully random.",
                                  help="Describe what the photo should show. Leave empty for fully random posts.")
        with st.expander("Search with a photo or a body pose",
                         expanded=bool(st.session_state.get("ref_up") or st.session_state.get("pose_ref"))):
            pa, pb = st.columns(2, gap="large")
            with pa:
                ref = st.file_uploader("Look-alike photo", type=["jpg", "jpeg", "png", "webp"], key="ref_up",
                                       help="Finds posts that look like this photo: same scene, setting, style. "
                                            "Can be combined with the text above.")
                if ref:
                    st.image(ref, width=160)
                like_weight = st.slider("Image vs text", 0.0, 1.0, 0.5, 0.05,
                                        help="0 = follow the text only, 1 = follow the image only.",
                                        disabled=not (ref and query.strip()))
            with pb:
                pose_ref = st.file_uploader("Body pose", type=["jpg", "jpeg", "png", "webp"], key="pose_ref",
                                            help="Finds posts where the person is posed the same way (standing, "
                                                 "lying, arms up...). Can be combined with a scene above. The first "
                                                 "time on an account it analyses every photo's pose (a few minutes).")
                if pose_ref:
                    st.image(pose_ref, width=160)
                    mirror = st.checkbox("Count a left-right flipped pose as a match", value=True)
                    scene_top = st.slider("Scene strictness (when a scene is also given)", 5, 100, 30, 5,
                                          format="best %d%%",
                                          help="Only rank posts in the best N% for the scene, then order those "
                                               "by pose.", disabled=not (query.strip() or ref))
                else:
                    mirror, scene_top = True, 30
    with col_b:
        with st.container(key="panel_count"):
            how_many = st.radio("How many posts", ["A number", "Everything in the categories I pick"],
                                help="'Everything' takes every post carrying the tags chosen under "
                                     "'Filter by tags' below, instead of a random handful.")
            take_all = how_many != "A number"
            if take_all:
                count = 5
                even = False
                video_mix = None
                limit = st.number_input("Stop after at most", 1, 2000, 100,
                                        help="A safety cap. Saving photos visits each post on Instagram "
                                             "(about 5 seconds each), so big batches take a while.")
                st.caption("Pick the categories in 'Filter by tags' below.")
            else:
                count = st.number_input("Number of posts", 1, 1000, 5)
                limit = 0
                even = False
                video_mix = None
                if st.checkbox("Choose the mix of videos and photos", value=False, key="mix_on",
                               help="The number above becomes the total across everything you picked. Videos come "
                                    "from your watched video folders and from videos attached to accounts. If you ask "
                                    "for more videos than exist, videos repeat with different segments."):
                    video_mix = st.slider("Videos in the results", 0, 100, 50, 10, format="%d%%", key="mix_pct")
                    n_vid = round(count * video_mix / 100)
                    st.caption(f"{count} in total: {n_vid} video segment(s) and {count - n_vid} photo(s). "
                               + ("Photos only." if video_mix == 0 else "Videos only." if video_mix == 100 else ""))
                if len(chosen_accounts) > 1:
                    even = st.checkbox("Same number from each account, mixed together", value=False,
                                       help="The number above becomes the total. It is shared equally between "
                                            "the accounts you picked (an account with too few matches gives what it "
                                            "has and the others make up the difference), then shuffled so the "
                                            "accounts are mixed through the list.")
                    if even:
                        share = count // len(chosen_accounts)
                        st.caption(f"{count} in total: about {share} from each of {len(chosen_accounts)} accounts"
                                   + (f" (plus {count % len(chosen_accounts)} extra from random ones)"
                                      if count % len(chosen_accounts) else "") + ".")
            mode = st.radio("Result", ["Show instantly from saved thumbnails", "Save full-size photos (slower)",
                                       "Just give me the links"])
            if take_all and mode.startswith("Save"):
                st.warning(f"Saving up to {limit} full-size photos will take roughly {int(limit * 5 / 60) + 1} "
                           f"minutes. 'Show instantly' needs no waiting.")

    chosen_tags = []
    with st.expander("Filter by tags (scene, outfit, shot type, pose)", expanded=take_all):
        st.caption("Only posts carrying ALL the tags you pick. Edit the tags in labels.json. "
                   "Pose tags build the pose index the first time (a few minutes).")
        options = tag_options()
        tag_cols = st.columns(len(options))
        for col, (facet, labels) in zip(tag_cols, options.items()):
            with col:
                picked = st.multiselect(facet.capitalize(), labels, key=f"tag_{facet}")
                chosen_tags += [f"{facet}:{label}" for label in picked]
        min_conf = st.slider("How sure a tag must be", 0.3, 0.95, 0.5, 0.05,
                             help="Higher = fewer posts but fewer mistakes. Applies to scene, outfit and "
                                  "shot tags.", disabled=not chosen_tags)

    with st.expander("Advanced options"):
        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            has_query = bool(query.strip() or ref or pose_ref)
            pick = st.radio("Pick from", ["Best matches", "Worst matches (to test the search)"],
                            disabled=not has_query)
            top = st.number_input("Choose randomly among the top N matches", 1, 500, 50, disabled=not has_query)
            use_dates = st.checkbox("Only posts from certain dates", value=False,
                                    help="Every Instagram post can be dated from its post code. Images you "
                                         "imported from a folder or video have no date and are left out "
                                         "while this is on.")
            d1, d2 = st.columns(2)
            date_from = d1.date_input("From", value=None, min_value=datetime.date(2010, 1, 1),
                                      disabled=not use_dates, format="DD/MM/YYYY")
            date_to = d2.date_input("Until (not included)", value=None, min_value=datetime.date(2010, 1, 1),
                                    disabled=not use_dates, format="DD/MM/YYYY")
        with c2:
            all_slides = st.checkbox("Save every carousel photo", value=False,
                                     help="Clicks through carousels. With a photo search, only slides that "
                                          "still match are kept.")
            margin = st.slider("Carousel strictness", 0.0, 0.10, 0.03, 0.01,
                               help="Smaller = only slides very close to the first one's score.",
                               disabled=not (all_slides and has_query))
            expand = st.number_input("Look inside the N most promising carousels", 0, 200, 0,
                                     disabled=not (has_query or chosen_tags),
                                     help="Carousels are normally judged by their first photo only. This opens "
                                          "the best-ranked ones for your search, searches ALL their photos too, "
                                          "and remembers them. About 10 seconds per carousel. 0 = off. Needs "
                                          "the account's carousels detected first (see Breakdown).")
        with c3:
            include_videos = st.checkbox("Allow reels / videos", value=False)
            clip_len = st.selectbox("Video clip length", list(CLIP_LENGTHS), key="clip_len",
                                    help="For imported videos: how long the clip is when you press 'Play clip' "
                                         "or save results. 'Full video' plays or copies the whole file; when "
                                         "playing it starts at the matched moment.")
            mix_videos = st.checkbox("With a search, still mix in videos from watched folders", value=True,
                                     help="Videos in watched folders aren't searched by content. When you search "
                                          "or filter by tags, random videos from the watched folders you picked "
                                          "are added alongside the matching photos (in the share each account "
                                          "gets). Untick to leave them out of searches.")
            combine = st.checkbox("Pool accounts together", value=False,
                                  help="Pick the posts from all accounts combined, not per account.")
            refresh = st.checkbox("Check for new posts first", value=False)
            full = st.checkbox("Rebuild from scratch (slow)", value=False)
        base_dir = st.text_input("Save folder", "picks")

    with st.container(key="findbar"):
        fb1, fb2 = st.columns([4, 1.2], vertical_alignment="center")
        n_acc = len(chosen_accounts)
        how = (f"everything matching the tags (up to {limit})" if take_all else f"<b>{count}</b> posts")
        extras = []
        if chosen_tags:
            extras.append(f"{len(chosen_tags)} tag filter(s)")
        if query.strip():
            extras.append("text search")
        if ref:
            extras.append("photo match")
        if pose_ref:
            extras.append("pose match")
        fb1.markdown(f'<span class="findsum"><b>{n_acc}</b> account(s) · {how}'
                     + (" · " + ", ".join(extras) if extras else " · random") + "</span>", unsafe_allow_html=True)
        go = fb2.button("Find posts", type="primary", width="stretch", icon=":material/search:")

    if go:
        users = [u.strip().lstrip("@").strip("/") for u in chosen_accounts if u.strip()]
        if not users:
            st.error("Choose at least one account.")
        elif not (HERE / "auth.json").exists():
            st.error("Log in first (open the settings panel with the arrow at the top left).")
        elif take_all and not (chosen_tags or query.strip() or ref or pose_ref):
            st.error("Pick at least one category under 'Filter by tags' (or give a search) "
                     "to take everything that matches.")
        else:
            saving = mode.startswith("Save")
            instant = mode.startswith("Show")
            save_dir = f"{base_dir.rstrip('/')}/{time.strftime('%Y-%m-%d_%H-%M-%S')}" if saving else None
            like_path = None
            if ref:                                    # keep the upload on disk so the script can read it
                refs_dir = HERE / "cache" / "refs"
                refs_dir.mkdir(parents=True, exist_ok=True)
                like_path = refs_dir / f"{time.strftime('%Y%m%d-%H%M%S')}_{Path(ref.name).name}"
                like_path.write_bytes(ref.getvalue())
            pose_path = None
            if pose_ref:
                refs_dir = HERE / "cache" / "refs"
                refs_dir.mkdir(parents=True, exist_ok=True)
                pose_path = refs_dir / f"{time.strftime('%Y%m%d-%H%M%S')}_pose_{Path(pose_ref.name).name}"
                pose_path.write_bytes(pose_ref.getvalue())
            cmd = build_command(users, count, query.strip(), top, pick.startswith("Worst"), save_dir,
                                all_slides, margin if abs(margin - 0.03) > 1e-9 else None,
                                include_videos, combine, refresh, full, like_path, like_weight,
                                pose_path, mirror, scene_top, chosen_tags, min_conf, take_all, limit,
                                expand, even, date_from.isoformat() if use_dates and date_from else None,
                                date_to.isoformat() if use_dates and date_to else None,
                                CLIP_LENGTHS[clip_len], mix_videos, video_mix if not take_all else None)
            with st.status("Working... (the first search on an account takes a few minutes while it "
                           "reads the whole profile)", expanded=True) as status:
                log_box = st.empty()
                code, lines = run_streaming(cmd, log_box)
                status.update(label="Done" if code == 0 else "Finished with errors",
                              state="complete" if code == 0 else "error")
            st.session_state["last"] = {"save_dir": save_dir, "lines": lines, "code": code,
                                        "instant": instant}

    last = st.session_state.get("last")
    if not last:
        st.markdown('<div class="empty"><b>Nothing picked yet</b>Choose accounts, optionally describe what you want, '
                    'then press Find posts. Results appear right here.</div>', unsafe_allow_html=True)
    if last:
        files, links = parse_results(last["lines"])
        errors = [l for l in last["lines"] if l.startswith("Error") or "Warning" in l]
        for e in errors:
            st.warning(e)
        if last.get("instant"):
            if not links and last["code"] == 0:
                st.markdown('<div class="empty"><b>No results</b>Try fewer filters, another account, or a different description.</div>',
                            unsafe_allow_html=True)
            elif links:
                section(f"{len(links)} result{'s' if len(links) != 1 else ''}",
                        "Untick anything you don't want, then play a slideshow or save the rest.")
                toolbar = st.container()          # filled in below, once we know which are ticked
                ticked = []
                for row_start in range(0, len(links), 4):
                    for col, (i, (user, url, slide, score)) in zip(
                            st.columns(4), enumerate(links[row_start:row_start + 4], row_start)):
                        f = thumb_for(user, url, slide)
                        with col:
                            if f.exists():
                                st.image(preview_image(str(f), f.stat().st_mtime))
                            else:
                                st.caption("No saved thumbnail for this post yet.")
                            label = user + (f" · slide {slide}" if slide else "") + \
                                (f" · score {score}" if score else "") + post_date_text(url)
                            if st.checkbox(label, value=True, key=f"keep_{i}_{url}_{slide}"):
                                ticked.append((user, url, slide, score, f))
                            source_link(user, url, f"res{i}")
                            if f.exists():
                                dl_name = f"{user}_{f.stem.replace('@', '_s')}" + \
                                    (f"_{score}" if score else "") + ".jpg"
                                image_actions(f"res{i}", user, f.stem, f, url, dl_name)
                with toolbar:
                    n_show = sum(1 for t in ticked if t[4].exists())
                    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
                    out_dir = HERE / base_dir.rstrip("/") / stamp
                    tb1, tb2, tb3, tb4 = st.columns([1.5, 1.5, 1.5, 1.2], vertical_alignment="center")
                    if st.session_state.get("slideshow_on"):
                        tb1.button("Close slideshow", key="slideshow_off", icon=":material/close:", width="stretch",
                                   on_click=lambda: st.session_state.update(slideshow_on=False))
                    else:
                        tb1.button(f"Slideshow ({n_show})", key="slideshow_start", disabled=not n_show,
                                   type="primary", icon=":material/slideshow:", width="stretch",
                                   on_click=lambda: st.session_state.update(slideshow_on=True),
                                   help="Plays the ticked results one after another. Untick an image to leave it out.")
                    save_thumbs = tb2.button("Save thumbnails", disabled=not ticked, width="stretch",
                                             icon=":material/download:", help="Instant: copies the saved thumbnails.")
                    save_full = tb3.button("Save full-size", disabled=not ticked, width="stretch",
                                           icon=":material/hd:", help="Fetches the full-size photos from Instagram.")
                    if st.session_state.get("saved_dir"):
                        if tb4.button("Open folder", width="stretch", icon=":material/folder_open:"):
                            subprocess.run(["open", st.session_state["saved_dir"]])
                    if save_thumbs:
                        out_dir.mkdir(parents=True, exist_ok=True)
                        for user, url, slide, score, f in ticked:
                            if f.exists():
                                name = f"{user}_{f.stem.replace('@', '_s')}" + (f"_{score}" if score else "")
                                shutil.copyfile(f, out_dir / f"{name}.jpg")
                        st.session_state["saved_dir"] = str(out_dir)
                        st.success(f"Saved {len(ticked)} thumbnail(s) to {out_dir}")
                    if save_full:
                        out_dir.mkdir(parents=True, exist_ok=True)
                        fetch_urls = [url for _, url, slide, _, _ in ticked if not slide]
                        for user, url, slide, score, f in ticked:      # slides are already saved full-size
                            if slide and f.exists():
                                shutil.copyfile(f, out_dir / f"{user}_{f.stem.replace('@', '_s')}.jpg")
                        if fetch_urls:
                            with st.status("Fetching the full-size photos from Instagram...", expanded=True) as st2:
                                fetch_log = st.empty()
                                fetch_code, _ = run_streaming([sys.executable, "random_post.py", "--fetch", *fetch_urls,
                                                               "--save", str(out_dir), "--no-open"], fetch_log)
                                st2.update(label="Done" if fetch_code == 0 else "Finished with errors",
                                           state="complete" if fetch_code == 0 else "error")
                        st.session_state["saved_dir"] = str(out_dir)
                        st.success(f"Saved to {out_dir}")
                    if st.session_state.get("slideshow_on"):
                        from concurrent.futures import ThreadPoolExecutor, as_completed
                        clips_ss = st.session_state.setdefault("ss_clips", {})   # session state is not visible from threads
                        secs_ss = CLIP_LENGTHS[st.session_state.get("clip_len", DEFAULT_CLIP)] or 120   # a whole video is too big to embed
                        bar = st.progress(0.0, text=f"Cutting video clips: 0 / {len(ticked)}")
                        clip_list = [None] * len(ticked)
                        with ThreadPoolExecutor(max_workers=4) as pool:
                            futs = {pool.submit(slideshow_clip, t[0], t[1], clips_ss, secs_ss): i for i, t in enumerate(ticked)}
                            for done, fut in enumerate(as_completed(futs), 1):
                                clip_list[futs[fut]] = fut.result()
                                bar.progress(done / len(ticked) * 0.6, text=f"Cutting video clips: {done} / {len(ticked)}")
                        show_items = [(f, user + (f" · slide {slide}" if slide else "") +
                                       (f" · score {score}" if score else "") + post_date_text(url), clip)
                                      for (user, url, slide, score, f), clip in zip(ticked, clip_list)]
                        slideshow(show_items, "res", bar)
                        bar.empty()
        elif last["save_dir"]:
            folder = HERE / last["save_dir"]
            images = sorted(folder.glob("*.*")) if folder.exists() else []
            if images:
                section(f"{len(images)} photo{'s' if len(images) != 1 else ''} saved")
                if st.button("Open folder in Finder", icon=":material/folder_open:"):
                    subprocess.run(["open", str(folder)])
                cols = st.columns(4)
                for i, img in enumerate(images):
                    with cols[i % 4]:
                        st.image(str(img), caption=img.name)
                        if img.name in files:
                            st.markdown(f"[Open post on Instagram]({files[img.name]})")
                        if img.name in files:                     # starring needs the post code from the link
                            code = re.search(r"/(?:p|reel|reels)/([\w-]+)", files[img.name]).group(1)
                            extra = re.search(r"_(\d\d)\.\w+$", img.name)
                            image_actions(f"saved{i}", img.name.split("_")[0], code + (f"@{int(extra.group(1))}"
                                          if extra else ""), img, files[img.name], img.name)
                        else:
                            st.download_button("Download", img.read_bytes(), file_name=img.name,
                                               icon=":material/download:",
                                               mime="image/png" if img.suffix == ".png" else "image/jpeg",
                                               key=f"dls_{img}", on_click="ignore")
            elif last["code"] == 0:
                st.info("Nothing was saved.")
        elif links:
            section(f"{len(links)} link{'s' if len(links) != 1 else ''}")
            for user, url, *_ in links:
                st.markdown(f"- **{user}**: [{url}]({url})")

# =====================================================================================
# BREAKDOWN: what is in each account
# =====================================================================================
with tab_bd:
    section("Account breakdown", "How many of each account's photos fall into each category. Tags come from "
            "labels.json and the pose index; photos with no confident match are counted separately.")
    ready = [r["account"] for r in rows if r["photo search ready"] and not r.get("videos only")]
    if not ready:
        st.markdown('<div class="empty"><b>No accounts to break down yet</b>Once an account has been read '
                    '(run any photo search on it), its breakdown shows here.</div>', unsafe_allow_html=True)
    else:
        b1, b2, b3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        with b1:
            pick_acct = st.selectbox("Account", ready + ["All accounts"])
        with b2:
            bd_conf = st.slider("How sure a tag must be", 0.3, 0.95, 0.5, 0.05, key="bd_conf")
        with b3:
            if st.button("Show breakdown", type="primary", width="stretch"):
                st.session_state["bd_open"] = True
        if st.session_state.get("bd_open"):
            targets = ready if pick_acct == "All accounts" else [pick_acct]
            for acct in targets:
                with st.spinner(f"Sorting {acct}'s posts (about 20 seconds the first time)..."):
                    info = get_breakdown(acct, bd_conf, index_stamp(acct), 2, active_model())
                with st.expander(acct, expanded=len(targets) == 1):
                    show_breakdown(info, acct)
                    lib_dir = HERE / "library" / acct
                    lib_a, lib_b, _ = st.columns([2, 2, 3])
                    if lib_a.button("Build / refresh library folders", key=f"lib_{acct}"):
                        with st.spinner("Sorting the saved thumbnails into folders..."):
                            lib_out = run_helper("random_post.py", acct, "--build-library",
                                                 "--min-conf", str(bd_conf))
                        st.success("\n\n".join(l.strip() for l in lib_out.splitlines()
                                               if l.startswith(("Library", "  "))) or "Done")
                    if lib_dir.exists() and lib_b.button("Open library in Finder", key=f"openlib_{acct}"):
                        subprocess.run(["open", str(lib_dir)])
                    if "error" not in info and info.get("carousels") is None:
                        st.info("Carousels aren't detected yet, so only each post's first photo is searched.")
                        if st.button(f"Find out which of {acct}'s posts are carousels (about 2 minutes)",
                                     key=f"dc_{acct}"):
                            with st.spinner("Reading the profile..."):
                                run_helper("random_post.py", acct, "--detect-carousels")
                            st.rerun()
                    if info.get("pose_ready") is False:
                        st.info("No pose index yet, so the pose and arms tags are missing here.")
                        if st.button(f"Build the pose index for {acct} (a few minutes)", key=f"bp_{acct}"):
                            with st.spinner("Analysing poses..."):
                                run_helper("random_post.py", acct, "--build-pose")
                            st.rerun()

# =====================================================================================
# LIBRARY: accounts, video folders, image folders, pilot
# =====================================================================================
with tab_lib:
    lib_accounts, lib_videos, lib_images, lib_pilot = st.tabs(
        ["Accounts", "Video folders", "Image folders", "Photos pilot"])

    with lib_accounts:
        section("Saved accounts", "Everything you can search. Videos attached to an account show as a count.")
        if rows:
            import pandas as pd
            st.dataframe(pd.DataFrame([{
                "Account": r["account"],
                "Posts": r["posts cached"],
                "Videos": r.get("videos") or (r["posts cached"] if r.get("videos only") else 0),
                "Status": ("video folder" if r.get("videos only") else "ready" if r["photo search ready"] else "not indexed yet"),
            } for r in rows]), hide_index=True, width="stretch",
                column_config={"Posts": st.column_config.NumberColumn(format="%d"),
                               "Videos": st.column_config.NumberColumn(format="%d")})
        else:
            st.markdown('<div class="empty"><b>No accounts yet</b>Add one below, or import a folder of images.</div>',
                        unsafe_allow_html=True)

        section("Add or prepare an account", "Does all the one-off work up front so every later search is instant: reads "
                "the whole profile, keeps the thumbnails, builds the photo and pose indexes and records which posts are "
                "carousels. Roughly 8 minutes for ~1,000 posts. Safe to run again; it only fills in what's missing.")
        prep_raw = st.text_input("Account(s) to prepare", key="prep_users", placeholder="username, another_username",
                                 help="One or more usernames. They're done one after another.")
        prep_expand = st.number_input("Also look inside up to N carousels now (0 = skip)", 0, 500, 0,
                                      help="Opens each carousel and indexes all its photos (about 10 seconds "
                                           "each). You can also do this later, per search.")
        if st.button("Prepare account(s)", disabled=job_running, type="primary"):
            prep_users = [u.strip().lstrip("@").strip("/") for u in re.split(r"[\s,]+", prep_raw) if u.strip()]
            if not prep_users:
                st.error("Enter at least one account.")
            elif not (HERE / "auth.json").exists():
                st.error("Log in first (open the settings panel with the arrow at the top left).")
            else:
                prep_cmd = [sys.executable, "random_post.py", *prep_users, "--prepare"]
                if prep_expand:
                    prep_cmd += ["--expand-carousels", str(prep_expand)]
                start_job(prep_cmd, "Preparing " + ", ".join(prep_users))
                st.rerun()

        section("Index every image", "Opens every carousel so each slide can be found by search.")
        idx_accounts = [r["account"] for r in rows if r["photo search ready"] and not r.get("videos only")]
        if not idx_accounts:
            st.caption("Set up an account first.")
        else:
            idx_acct = st.selectbox("Account", idx_accounts, key="idx_acct")
            done_n, total_n, extra_n = slide_progress(idx_acct)
            st.progress(done_n / total_n if total_n else 1.0,
                        text=f"{done_n} of {total_n} posts opened, {extra_n} extra photos indexed")
            i1, i2, i3 = st.columns([3, 3, 2], gap="large")
            with i1:
                idx_cap = st.number_input("Open at most this many posts this session", 5, 2000, 10,
                                          help="Start with 10 to check it works on your account. Progress is "
                                               "saved after every post, so you can stop any time and "
                                               "continue later.")
            with i3:
                idx_workers = st.selectbox("Browser windows at once", [1, 2, 3],
                                           help="More windows finish sooner but send Instagram that many "
                                                "times the activity from your login. 1 is the safe setting.")
            with i2:
                idx_all = st.checkbox("Keep going until everything is done",
                                      help="Works through every remaining post in batches with short breaks, "
                                           "and stops by itself if Instagram starts failing to load pages.")
            if st.button("Start / continue", disabled=job_running or (done_n >= total_n and total_n > 0),
                         type="primary", key="idx_go"):
                if not (HERE / "auth.json").exists():
                    st.error("Log in first (open the settings panel with the arrow at the top left).")
                else:
                    idx_cmd = [sys.executable, "random_post.py", idx_acct, "--prepare"]
                    idx_cmd += ["--expand-all"] if idx_all else ["--expand-carousels", str(idx_cap)]
                    if idx_workers > 1:
                        idx_cmd += ["--workers", str(idx_workers)]
                    start_job(idx_cmd, f"Indexing every image of {idx_acct}"
                                       + ("" if idx_all else f" ({idx_cap} posts)")
                                       + (f", {idx_workers} windows" if idx_workers > 1 else ""))
                    st.rerun()
            if idx_workers > 1:
                st.warning(f"{idx_workers} windows means about {idx_workers} times the page loads per minute "
                           f"from your login. If Instagram starts failing pages, the job stops by itself; "
                           f"wait a few hours before trying again.")
            if job_running:
                st.caption("A background job is running; wait for it or stop it at the top of the page.")

    with lib_videos:
        section("Watched video folders", "Point a collection at a folder. Videos added to it, or to any sub-folder, "
                "show up here within a few seconds, ready to play. No search model runs on them, so adding is quick. "
                "A new name makes a collection of videos; the name of an account you already have attaches the videos "
                "to it. Your files are only read. Keep this page open while you copy files in.")
        w1, w2, w3 = st.columns([2, 4, 1], vertical_alignment="bottom")
        w_name = w1.text_input("Collection name", key="w_name")
        w_dir = w2.text_input("Folder path", key="w_dir")
        if w3.button("Watch", key="w_go", type="primary", width="stretch"):
            import random_post as _rp
            try:
                _rp.start_watching(w_name, w_dir.strip().strip("'\""))
                _rp.scan_watched(_rp.clean_name(w_name))
                st.rerun()
            except _rp.ScrapeError as e:
                st.error(str(e))
        with st.expander("Create several at once"):
            st.caption("Say how many, then give each one a name and the folder to take its videos and photos from. "
                       "Videos are added instantly (no search model). Photos are imported in the background.")
            n_rows = st.number_input("How many", 1, 100, 6, key="bulk_n")
            import pandas as pd
            table = st.data_editor(pd.DataFrame({"Name": [""] * int(n_rows), "Folder path": [""] * int(n_rows)}),
                                   key=f"bulk_table_{int(n_rows)}", hide_index=True, width="stretch",
                                   column_config={"Name": st.column_config.TextColumn(width="small"),
                                                  "Folder path": st.column_config.TextColumn(width="large")})
            if st.button("Create all", key="bulk_go", type="primary"):
                import random_post as _rp
                rows_in = [(str(a or ""), str(b or "")) for a, b in zip(table["Name"], table["Folder path"])]
                report = _rp.create_collections(rows_in)
                st.session_state["bulk_report"] = report
                todo = [[r["name"], r["folder"]] for r in report if r["status"] == "created" and r["photos"]]
                if todo and not job_running:
                    pairs = HERE / "cache" / "jobs" / f"pairs_{int(time.time())}.json"
                    pairs.parent.mkdir(parents=True, exist_ok=True)
                    pairs.write_text(json.dumps(todo))
                    start_job([sys.executable, "random_post.py", "--import-many", str(pairs)],
                              f"Importing photos for {len(todo)} categories")
                elif todo:
                    st.session_state["bulk_note"] = "Photos were not imported because another job is running; press Import below once it ends."
                st.rerun()
            report = st.session_state.get("bulk_report")
            if report:
                st.dataframe(pd.DataFrame([{"Name": r["name"], "Status": r["status"], "Videos": r["videos"], "Photos found": r["photos"]}
                                           for r in report]), hide_index=True, width="stretch")
                if any(r["photos"] for r in report if r["status"] == "created"):
                    st.caption("Photos are being imported in the background; they appear in searches when that job finishes."
                               + (" " + st.session_state.get("bulk_note", "") if st.session_state.get("bulk_note") else ""))
        watched_panel()

    with lib_images:
        section("Import a folder of images", "Adds every image in a folder (including sub-folders) as a collection that "
                "works like an account: search, tags, pose matching, breakdown and favourites. Your files are only "
                "read; the tool keeps its own resized copies. Run it again later to add new files.")
        imp1, imp2, imp3 = st.columns([2, 4, 1], vertical_alignment="bottom")
        imp_name = imp1.text_input("Collection name", key="imp_name",
                                   help="Letters and numbers, e.g. 'holiday' or a person's name.")
        imp_dir = imp2.text_input("Folder path", key="imp_dir",
                                  help="Paste the folder's path. In Finder: right-click the folder, hold Option, "
                                       "choose 'Copy ... as Pathname'.")
        if imp3.button("Import", disabled=job_running, key="imp_go", type="primary", width="stretch"):
            if not imp_name.strip() or not imp_dir.strip():
                st.error("Give both a name and a folder.")
            elif not Path(imp_dir.strip().strip("'\"")).expanduser().is_dir():
                st.error("That folder wasn't found.")
            else:
                start_job([sys.executable, "random_post.py", imp_name.strip(), "--import-folder",
                           imp_dir.strip().strip("'\"")], f"Importing {imp_name.strip()}")
                st.rerun()
        st.caption("Videos: use **Video folders**. They are added instantly, with no search model.")

        status = folder_status()
        if status:
            section("Folders already imported")
            total_new = sum(n for _, _, n in status)
            for coll, folders, n_new in status:
                with st.container(border=True):
                    r1, r2 = st.columns([4, 1], vertical_alignment="center")
                    r1.markdown(f"**{coll}** · {', '.join(Path(f).name for f in folders)}  \n"
                                + (f"{n_new} new file(s) waiting" if n_new else "up to date"))
                    if r2.button("Import new", key=f"impnew_{coll}", disabled=job_running or not n_new, width="stretch"):
                        start_job([sys.executable, "random_post.py", coll, "--import-new"], f"Importing new files into {coll}")
                        st.cache_data.clear()
                        st.rerun()
            c1, c2 = st.columns([1, 2], vertical_alignment="center")
            if c1.button(f"Import all new ({total_new})", key="impnew_all", disabled=job_running or not total_new,
                         type="primary"):
                start_job([sys.executable, "random_post.py", "--import-new"], "Importing new files from your folders")
                st.cache_data.clear()
                st.rerun()
            c2.checkbox("Check for new files when the app opens and import them automatically",
                        value=auto_import_on(), key="auto_import_box", on_change=lambda: set_auto_import(
                            st.session_state["auto_import_box"]),
                        help="Files are imported only once they've finished copying (about 30 seconds after "
                             "they last changed). Your files are only read.")

    with lib_pilot:
        section("Photos pilot", "Sorts screenshots from your Photos library into keep, review and junk. "
                "Reads the library read-only; nothing in it is changed or copied.")
        pilot_items = load_pilot()
        if st.button("Run the pilot on 400 random screenshots", disabled=job_running, type="primary"):
            start_job([sys.executable, "photos_import.py", "--pilot", "400"], "Sorting 400 screenshots from Photos")
            st.rerun()
        if pilot_items:
            import photos_import as pi
            ov = load_overrides()
            t1, t2 = st.columns(2, gap="large")
            keep_at = t1.slider("Keep when the photo score is at least", 0.3, 0.99, 0.70, 0.01)
            junk_at = t2.slider("Junk when the score is below", 0.01, 0.6, 0.20, 0.01)
            piles = {"keep": [], "review": [], "junk": []}
            for it in pilot_items:
                auto = pi.assign_pile(it["p_keep"], it["body"], keep_at, junk_at)
                piles[ov.get(it["uuid"], auto)].append((it, auto))
            corrected = [(it, a) for k in piles for it, a in piles[k] if it["uuid"] in ov]
            st.markdown(f"**{len(pilot_items)} screenshots:** {len(piles['keep'])} keep, "
                        f"{len(piles['review'])} to review, {len(piles['junk'])} junk."
                        + (f" You've corrected {len(corrected)}." if corrected else ""))
            show_full = st.checkbox("Show the whole screenshot instead of the cropped photo")
            tabs = st.tabs([f"Keep ({len(piles['keep'])})", f"Review ({len(piles['review'])})",
                            f"Junk ({len(piles['junk'])})"])
            for tab, name in zip(tabs, ("keep", "review", "junk")):
                with tab:
                    pile_rows = sorted(piles[name], key=lambda x: (x[0]["uuid"] not in ov, -x[0]["p_keep"]))
                    for start in range(0, min(len(pile_rows), 40), 5):
                        for col, (it, auto) in zip(st.columns(5), pile_rows[start:start + 5]):
                            with col:
                                img = Path(it["preview"]) if show_full else PILOT_DIR / "crops" / f"{it['uuid']}.jpg"
                                if img.exists():
                                    st.image(preview_image(str(img), img.stat().st_mtime))
                                st.caption(f"score {it['p_keep']:.2f}" + (" · body" if it["body"] else "")
                                           + f" · {it['best_prompt'].replace('a screenshot of ', '').replace('a photo of ', '')}")
                                if name != "keep":
                                    st.button("Keep", key=f"pk_{it['uuid']}", on_click=set_pile, args=(it["uuid"], "keep"),
                                              icon=":material/check:")
                                if name != "junk":
                                    st.button("Junk", key=f"pj_{it['uuid']}", on_click=set_pile, args=(it["uuid"], "junk"),
                                              icon=":material/delete:")
                                if it["uuid"] in ov:
                                    st.button("Undo", key=f"pu_{it['uuid']}", on_click=set_pile, args=(it["uuid"], "auto"),
                                              icon=":material/undo:")
                    if len(pile_rows) > 40:
                        st.caption(f"Showing the first 40 of {len(pile_rows)} (highest scores first).")

# =====================================================================================
# FAVOURITES
# =====================================================================================
with tab_fav:
    section(f"Favourites ({len(FAVS)})", "Pictures you starred. Starring copies the picture into favourites/.")
    if not FAVS:
        st.markdown('<div class="empty"><b>No favourites yet</b>Press the star under any image to keep it here.</div>',
                    unsafe_allow_html=True)
    else:
        fav_accounts = sorted({v["account"] for v in FAVS.values()})
        fa, fb = st.columns([3, 2], vertical_alignment="bottom")
        fav_filter = fa.selectbox("Account", ["All accounts"] + fav_accounts, key="fav_filter")
        if fb.button("Open favourites folder in Finder", icon=":material/folder_open:"):
            subprocess.run(["open", str(FAV_DIR)])
        shown_favs = sorted((v for v in FAVS.values()
                             if fav_filter == "All accounts" or v["account"] == fav_filter),
                            key=lambda v: -v["added"])
        for start in range(0, len(shown_favs), 5):
            for col, v in zip(st.columns(5), shown_favs[start:start + 5]):
                f = HERE / v["file"]
                with col:
                    if f.exists():
                        st.image(preview_image(str(f), f.stat().st_mtime))
                    st.caption(v["account"] + (f" · slide {v['stem'].split('@')[1]}" if "@" in v["stem"] else ""))
                    source_link(v["account"], v["url"], "fav")
                    if f.exists():
                        image_actions("fav", v["account"], v["stem"], f, v["url"], f.name)
