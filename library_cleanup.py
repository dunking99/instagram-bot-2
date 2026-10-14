#!/usr/bin/env python3
"""Merge duplicate creator folders in library/ so there is one folder per creator, and keep everything else in step.

    python3 library_cleanup.py                 # DRY RUN: print the plan, change nothing
    python3 library_cleanup.py --apply         # do it
    python3 library_cleanup.py --undo 20261008-231500    # put everything back from that run's log

Duplicates are folders whose names differ only by case, '-', '_' or spaces (hannah_jo / hannah-jo / Hannah Jo).
Which one stays:
  * the one that has a search index or a photo collection (e.g. paigeinsco, raraknupps), because the Postroom's
    indexes belong to that name;
  * otherwise the hyphenated one, which is what the Links tool uses for new downloads.
What it changes, for every merged folder:
  * moves the videos (and anything else inside) into the kept folder; the source folder is removed once empty;
  * carries the Postroom's records over: the 'watched folder' registration (cache/<name>.watch.json) and the
    thumbnails (cache/thumbs/<name>/). Video ids come from the file contents, so they survive the move;
  * points the Links tool (its copy inside the Postroom) at the kept folder for future downloads;
  * fixes pipeline_state.json and rebuilds the position index.
Nothing is deleted: a same-name identical file, replaced registrations and old thumbnail folders go to the log folder.
Every run writes library_cleanup_logs/<timestamp>/ with log.md, moves.json (for --undo) and backups.
Empty folders that have no duplicate partner are left alone (the Links tool creates those for creators).
"""
import argparse
import collections
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(ROOT, "library")
CACHE = os.path.join(ROOT, "cache")
LOGS = os.path.join(ROOT, "library_cleanup_logs")
CLIP = os.path.join(ROOT, "CLIP Training")
LINKS = os.environ.get("LIBRARY_CLEANUP_LINKS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "links", "ui", "data", "creators.json"))
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".wmv", ".flv"}
INDEX_FILES = ("siglip.npz", "clip.npz", "videos.json", "local.json")


def key(n):
    return re.sub(r"[^a-z0-9]", "", n.lower())


def hyphen(n):
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")


def rj(p, default=None):
    try:
        with open(p) as fh:
            return json.load(fh)
    except Exception:
        return default


def wj(p, obj):
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh)
    os.replace(tmp, p)


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def files_of(folder):
    out = []
    for dp, _, fn in os.walk(folder):
        for f in fn:
            if f != ".DS_Store":
                out.append(os.path.join(dp, f))
    return out


def lowpath(p):
    return os.path.realpath(p).lower()          # symlink-proof and case-insensitive (the Mac file system is)


def build_plan():
    folders = sorted(d for d in os.listdir(LIB) if os.path.isdir(os.path.join(LIB, d)))
    regs = {}                                                      # registration name -> its json
    for f in glob.glob(os.path.join(CACHE, "*.watch.json")):
        regs[os.path.basename(f)[:-len(".watch.json")]] = rj(f, {})
    reg_of_folder = {}                                             # lower folder path -> registration name
    for n, d in regs.items():
        if d.get("folder"):
            reg_of_folder.setdefault(lowpath(d["folder"]), n)
    by_key = collections.defaultdict(list)
    for d in folders:
        by_key[key(d)].append(d)
    stale = {}                                                     # registrations whose folder is missing, by key
    for n, d in regs.items():
        fo = d.get("folder", "")
        if fo and not os.path.isdir(fo):
            stale.setdefault(key(os.path.basename(fo.rstrip("/"))) or key(n), []).append(n)

    plan, notes = [], []
    for k, members in sorted(by_key.items()):
        if len(members) < 2 and not (members and stale.get(k)):
            continue
        indexed = [m for m in members if any(os.path.exists(os.path.join(CACHE, f"{m.lower()}.{x}")) for x in INDEX_FILES)]
        photo = [m for m in members if sum(1 for f in files_of(os.path.join(LIB, m)) if os.path.splitext(f)[1].lower() not in VIDEO_EXT) > 20]
        special = sorted(set(indexed) | set(photo))
        if len(special) == 1:
            keep, why = special[0], "has a search index / photo collection"
        elif len(special) > 1:
            notes.append(f"SKIPPED {members}: more than one has an index or photos, needs your decision")
            continue
        else:
            h = hyphen(members[0])
            if h in members:
                keep, why = h, "hyphenated, matches the Links tool"
            else:
                notes.append(f"SKIPPED {members}: no obvious folder to keep")
                continue
        sources = [m for m in members if m != keep]
        stale_regs = [n for n in stale.get(k, []) if not os.path.isdir(regs[n].get("folder", ""))]
        plan.append({"key": k, "keep": keep, "why": why, "sources": sources, "stale_regs": stale_regs,
                     "reg_keep": reg_of_folder.get(lowpath(os.path.join(LIB, keep))),
                     "reg_src": {s: reg_of_folder.get(lowpath(os.path.join(LIB, s))) for s in sources}})
    return plan, notes, regs


def describe(plan, notes, regs):
    lines = []
    tot_files = tot_vids = 0
    for g in plan:
        lines.append(f"\n{g['keep']}   (keep: {g['why']})")
        for s in g["sources"]:
            fs = files_of(os.path.join(LIB, s))
            v = sum(1 for f in fs if os.path.splitext(f)[1].lower() in VIDEO_EXT)
            tot_files += len(fs)
            tot_vids += v
            rn = g["reg_src"][s]
            lines.append(f"   <- {s:<18} {v} video(s), {len(fs) - v} other file(s); Postroom record: {rn or 'none'}"
                         + (f" ({len(regs[rn].get('videos', {}))} registered)" if rn else "") + "   -> folder removed when empty")
        for n in g["stale_regs"]:
            lines.append(f"   <- stale record '{n}' (its folder no longer exists, {len(regs[n].get('videos', {}))} registered) -> merged in")
    lines.append(f"\n{len(plan)} creators to merge; {tot_vids} video file(s) and {tot_files - tot_vids} other file(s) move.")
    lines += ["", *notes]
    return "\n".join(lines)


def apply(plan, regs):
    ts = time.strftime("%Y%m%d-%H%M%S")
    logdir = os.path.join(LOGS, ts)
    os.makedirs(os.path.join(logdir, "backup", "cache"), exist_ok=True)
    os.makedirs(os.path.join(logdir, "duplicates"), exist_ok=True)
    log, moves, regchanges, created = [], [], [], []
    pause = os.path.join(CLIP, "auto_pipeline_off")
    made_pause = not os.path.exists(pause)
    if made_pause:
        open(pause, "w").write("paused by library_cleanup.py\n")
    try:
        status = rj(os.path.join(CLIP, "pipeline_status.json"), {})
        if status.get("running"):
            sys.exit("An analysis job is running. Wait for it to finish, then run this again.")
        # ---- backups of everything we may edit
        for f in glob.glob(os.path.join(CACHE, "*.watch.json")):
            shutil.copy2(f, os.path.join(logdir, "backup", "cache"))
        for f in (LINKS, os.path.join(CLIP, "pipeline_state.json"), os.path.join(CLIP, "position_index.json")):
            if os.path.exists(f):
                shutil.copy2(f, os.path.join(logdir, "backup", os.path.basename(f)))
        sizes_before = {}
        # ---- A. copy thumbnails first (the Postroom's watcher deletes the thumbnails of videos that vanish from a folder)
        thumb_jobs = []
        for g in plan:
            for s_, rn in [(s2, g["reg_src"][s2]) for s2 in g["sources"] if g["reg_src"][s2]] + [("(stale)", n) for n in g["stale_regs"]]:
                thumb_jobs.append((g, rn))
        for g, rn in thumb_jobs:
            sth = os.path.join(CACHE, "thumbs", rn)
            kth = os.path.join(CACHE, "thumbs", (g["reg_keep"] or g["keep"].lower()))
            if os.path.isdir(sth):
                os.makedirs(kth, exist_ok=True)
                os.makedirs(os.path.join(logdir, "backup", "thumbs"), exist_ok=True)
                shutil.copytree(sth, os.path.join(logdir, "backup", "thumbs", rn), dirs_exist_ok=True)
                n = 0
                for t in os.listdir(sth):
                    if not os.path.exists(os.path.join(kth, t)):
                        shutil.copy2(os.path.join(sth, t), os.path.join(kth, t))
                        created.append(os.path.join(kth, t))
                        n += 1
                log.append(f"- copied {n} thumbnail(s) from `thumbs/{rn}` to `thumbs/{os.path.basename(kth)}`")
        # ---- B. per creator: move the files, then update the records straight away
        for g in plan:
            keep = g["keep"]
            kdir = os.path.join(LIB, keep)
            rk = g["reg_keep"]
            kreg_path = os.path.join(CACHE, f"{(rk or keep.lower())}.watch.json")
            kreg = rj(kreg_path, None) if rk else None
            created_reg = False
            if kreg is None:
                kreg = {"folder": kdir, "videos": {}, "dupes": []}
                created_reg = True
            moved_names = {}
            for s in g["sources"]:
                sdir = os.path.join(LIB, s)
                for f in files_of(sdir):
                    rel = os.path.relpath(f, sdir)
                    dest = os.path.join(kdir, rel)
                    sizes_before[f] = os.path.getsize(f)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    if os.path.exists(dest):
                        if os.path.getsize(dest) == os.path.getsize(f) and md5(dest) == md5(f):
                            q = os.path.join(logdir, "duplicates", s, rel)
                            os.makedirs(os.path.dirname(q), exist_ok=True)
                            shutil.move(f, q)
                            moves.append({"from": f, "to": q, "kind": "identical duplicate, set aside"})
                            log.append(f"- identical copy already in {keep}: moved {s}/{rel} to the log's duplicates folder")
                            continue
                        base, ext = os.path.splitext(dest)
                        dest = f"{base} (from {s}){ext}"
                    shutil.move(f, dest)
                    moves.append({"from": f, "to": dest, "kind": "moved"})
                    moved_names[f] = dest
                    log.append(f"- moved `{s}/{rel}` -> `{keep}/{os.path.relpath(dest, kdir)}`")
            src_regs = [(s, g["reg_src"][s]) for s in g["sources"] if g["reg_src"][s]] + [("(stale)", n) for n in g["stale_regs"]]
            for s, rn in src_regs:
                sreg = regs.get(rn) or {}
                added = 0
                for vid, v in sreg.get("videos", {}).items():
                    if vid in kreg["videos"]:
                        continue
                    old = v.get("file", "")
                    new = next((d for o, d in moved_names.items() if lowpath(o) == lowpath(old)), None)
                    if new is None:
                        cand = os.path.join(kdir, os.path.basename(old))
                        new = cand if os.path.exists(cand) else None
                    if new is None:
                        continue                                   # the file is not in the library any more
                    kreg["videos"][vid] = {**v, "file": new}
                    added += 1
                dup, sdup = kreg.get("dupes", []), sreg.get("dupes", [])
                if isinstance(dup, list) and isinstance(sdup, list):
                    kreg["dupes"] = dup + [x for x in sdup if x not in dup]
                regchanges.append({"from": rn, "into": rk or keep.lower(), "videos": added})
                log.append(f"- Postroom record `{rn}` merged into `{rk or keep.lower()}`: {added} video record(s)")
            wj(kreg_path, kreg)
            if created_reg:
                created.append(kreg_path)
                log.append(f"- created Postroom record `{keep.lower()}` for `{keep}` ({len(kreg['videos'])} video record(s))")
            for s in g["sources"]:
                sdir = os.path.join(LIB, s)
                left = files_of(sdir)
                if left:
                    log.append(f"- WARNING: `{s}` still holds {len(left)} file(s), not removed")
                    continue
                shutil.rmtree(sdir)
                moves.append({"from": sdir, "to": None, "kind": "folder removed (empty)"})
                log.append(f"- removed empty folder `{s}`")
        # ---- C. retire the old records and thumbnail folders (they are in the backup)
        for g, rn in thumb_jobs:
            target = g["reg_keep"] or g["keep"].lower()
            sth = os.path.join(CACHE, "thumbs", rn)
            if os.path.isdir(sth) and rn != target:
                shutil.rmtree(sth)
            spath = os.path.join(CACHE, f"{rn}.watch.json")
            if os.path.exists(spath) and rn != target:
                os.remove(spath)
        for g in plan:                                              # records with no thumbnail folder
            for rn in [x for x in g["reg_src"].values() if x] + g["stale_regs"]:
                spath = os.path.join(CACHE, f"{rn}.watch.json")
                if os.path.exists(spath) and rn != (g["reg_keep"] or g["keep"].lower()):
                    os.remove(spath)
        # ---- 4. Links tool (the copy inside the Postroom): future downloads go to the kept folder
        creators = rj(LINKS, None)
        if isinstance(creators, list):
            changed = 0
            for c in creators:
                cur = c.get("folder_name") or c["slug"].replace("_", "-")
                for g in plan:
                    if key(cur) == g["key"] and cur != g["keep"]:
                        c["folder_name"] = g["keep"]
                        changed += 1
                        log.append(f"- Links creator `{c['slug']}`: downloads now go to `{g['keep']}` (was `{cur}`)")
            if changed:
                wj(LINKS, creators)
        # ---- 5. pipeline_state.json keys, position index
        ps = rj(os.path.join(CLIP, "pipeline_state.json"), None)
        if ps:
            mp = {lowpath(m["from"]): m["to"] for m in moves if m["kind"] == "moved"}
            for sect in ("files",):
                new = {}
                for p, v in ps.get(sect, {}).items():
                    new[mp.get(lowpath(p), p)] = v
                ps[sect] = new
            wj(os.path.join(CLIP, "pipeline_state.json"), ps)
        py = os.path.join(CLIP, ".venv", "bin", "python")
        if not os.path.exists(py):
            py = None
        if py:
            r = subprocess.run([py, os.path.join(CLIP, "scripts", "position_index.py")], capture_output=True, text=True)
            log.append(f"- rebuilt the position index: {r.stdout.strip() or r.stderr.strip()[-200:]}")
        # ---- 6. verify
        bad = [m for m in moves if m["kind"] == "moved" and (not os.path.exists(m["to"]) or os.path.getsize(m["to"]) != sizes_before.get(m["from"]))]
        log.append(f"\nVerification: {sum(1 for m in moves if m['kind'] == 'moved')} file(s) moved, {len(bad)} problem(s).")
        wj(os.path.join(logdir, "moves.json"), {"moves": moves, "registrations": regchanges, "created": created})
        with open(os.path.join(logdir, "log.md"), "w") as fh:
            fh.write(f"# Library cleanup {ts}\n\nUndo with: `python3 library_cleanup.py --undo {ts}`\n\n" + "\n".join(log) + "\n")
        print("\n".join(log[-12:]))
        print(f"\nFull log: {os.path.join(logdir, 'log.md')}\nUndo:     python3 library_cleanup.py --undo {ts}")
        return len(bad)
    finally:
        if made_pause:
            os.remove(pause)


def undo(ts):
    logdir = os.path.join(LOGS, ts)
    data = rj(os.path.join(logdir, "moves.json"))
    if not data:
        sys.exit(f"no log found at {logdir}")
    for m in reversed(data["moves"]):
        if m["kind"] == "folder removed (empty)":
            os.makedirs(m["from"], exist_ok=True)
        elif m["to"] and os.path.exists(m["to"]):
            os.makedirs(os.path.dirname(m["from"]), exist_ok=True)
            shutil.move(m["to"], m["from"])
    bk = os.path.join(logdir, "backup")
    for f in glob.glob(os.path.join(bk, "cache", "*.watch.json")):
        shutil.copy2(f, os.path.join(CACHE, os.path.basename(f)))
    for d in glob.glob(os.path.join(bk, "thumbs", "*")):
        dst = os.path.join(CACHE, "thumbs", os.path.basename(d))
        if not os.path.exists(dst):
            shutil.copytree(d, dst)
    for name, dst in (("creators.json", LINKS), ("pipeline_state.json", os.path.join(CLIP, "pipeline_state.json")),
                      ("position_index.json", os.path.join(CLIP, "position_index.json"))):
        if os.path.exists(os.path.join(bk, name)):
            shutil.copy2(os.path.join(bk, name), dst)
    for f in data.get("created", []):                        # records and thumbnails the run created
        if os.path.exists(f) and not os.path.exists(os.path.join(bk, "cache", os.path.basename(f))):
            os.remove(f)
    for d in glob.glob(os.path.join(CACHE, "thumbs", "*")):
        if os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
    print("restored: files moved back, records and thumbnails put back, creators/pipeline state/index restored.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo")
    a = ap.parse_args()
    if a.undo:
        return undo(a.undo)
    plan, notes, regs = build_plan()
    print(describe(plan, notes, regs))
    if a.apply:
        sys.exit(1 if apply(plan, regs) else 0)
    print("\nThis was a dry run. Nothing was changed. Run with --apply to do it.")


if __name__ == "__main__":
    main()
