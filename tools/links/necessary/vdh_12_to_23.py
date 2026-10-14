#!/usr/bin/env python3
"""
Download 10 successful videos from 12_to_23min_random.txt
"""

import time
import random
import sys
import subprocess
import shutil
from pathlib import Path

try:
    import pyautogui
except ImportError:
    print("Run: python3 -m pip install pyautogui")
    sys.exit(1)

# ============================================
LINKS_FILE = "12_to_23min_random.txt"
TARGET_SUCCESS = 10
MAX_ATTEMPTS = 30

DOWNLOADS_DIR = Path.home() / "Downloads"
LIBRARY_DIR = Path(__file__).resolve().parents[3] / "library"

VDH_ICON_POS = (1248, 95)
DOWNLOAD_BUTTON_POS = (1177, 382)
WAIT_FOR_DOWNLOAD_SECONDS = 25
# ============================================

def load_links(filename):
    path = Path(filename)
    if not path.exists():
        print(f"File not found: {filename}")
        sys.exit(1)
    with open(path) as f:
        return [l.strip() for l in f if l.strip().startswith("http")]

def get_creator_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1].replace("-", "_")
    parts = slug.split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else parts[0]

def open_url_in_chrome(url):
    script = f'''
    tell application "Google Chrome"
        activate
        if (count of windows) = 0 then make new window
        set URL of active tab of front window to "{url}"
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=False)

def get_current_download_files():
    return {f.name for f in DOWNLOADS_DIR.iterdir()
            if f.suffix.lower() in {".mp4", ".mkv", ".webm", ".part", ".crdownload"}}

def wait_for_new_download(before_files, timeout=WAIT_FOR_DOWNLOAD_SECONDS):
    start = time.time()
    while time.time() - start < timeout:
        new_files = get_current_download_files() - before_files
        if new_files:
            for name in new_files:
                if name.endswith(".mp4"):
                    return DOWNLOADS_DIR / name
            return DOWNLOADS_DIR / next(iter(new_files))
        time.sleep(1.2)
    return None

def move_to_library(file_path: Path, creator: str):
    target_dir = LIBRARY_DIR / creator
    target_dir.mkdir(parents=True, exist_ok=True)

    if file_path.suffix in {".part", ".crdownload"}:
        print("    Waiting for download to finish...")
        for _ in range(40):
            time.sleep(2)
            finished = file_path.with_suffix(".mp4")
            if finished.exists():
                file_path = finished
                break
        else:
            print("    Still downloading – leaving in Downloads")
            return False

    dest = target_dir / file_path.name
    try:
        shutil.move(str(file_path), str(dest))
        print(f"    → Moved to {dest}")
        return True
    except Exception as e:
        print(f"    Move failed: {e}")
        return False

def main():
    all_links = load_links(LINKS_FILE)
    random.shuffle(all_links)
    link_pool = all_links.copy()

    print(f"Loaded {len(all_links)} links from {LINKS_FILE}")
    print(f"Target: {TARGET_SUCCESS} successful downloads")
    print("Make sure Chrome is open and maximised.")
    print("Starting in 8 seconds...")
    time.sleep(8)

    success_count = 0
    attempt = 0

    while success_count < TARGET_SUCCESS and attempt < MAX_ATTEMPTS and link_pool:
        attempt += 1
        url = link_pool.pop(0)
        creator = get_creator_from_url(url)

        print(f"\n[{success_count+1}/{TARGET_SUCCESS}] Attempt {attempt}")
        print(f"URL: {url}")
        print(f"Folder: {creator}")

        before = get_current_download_files()

        try:
            open_url_in_chrome(url)
            time.sleep(5.5)

            print("  → Clicking VDH icon...")
            pyautogui.click(VDH_ICON_POS)
            time.sleep(1.8)

            print("  → Clicking Download...")
            pyautogui.click(DOWNLOAD_BUTTON_POS)

            new_file = wait_for_new_download(before)

            if new_file:
                print(f"  ✓ Detected: {new_file.name}")
                if move_to_library(new_file, creator) or new_file.exists():
                    success_count += 1
                    print(f"  Success: {success_count}/{TARGET_SUCCESS}")
            else:
                print("  ✗ No new file appeared")

        except Exception as e:
            print(f"  ✗ Error: {e}")

        time.sleep(3 + random.uniform(0.5, 2))

    print("\n========== FINISHED ==========")
    print(f"Successful downloads: {success_count}")

if __name__ == "__main__":
    main()
