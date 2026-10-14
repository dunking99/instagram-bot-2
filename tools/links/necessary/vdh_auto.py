
#!/usr/bin/env python3

"""

Video DownloadHelper Automation - Controls already-open Chrome

"""

import time

import random

import sys

import subprocess

from pathlib import Path

try:

    import pyautogui

except ImportError:

    print("Run: python3 -m pip install pyautogui")

    sys.exit(1)

# ============================================

# CONFIGURATION

# ============================================

LINKS_FILE = "all_links_random_sex.txt"

MAX_LINKS = 10

DELAY_BETWEEN_VIDEOS = 8

VDH_ICON_POS = (1248, 95)

DOWNLOAD_BUTTON_POS = (1177, 382)

# ============================================

def load_links(filename):

    path = Path(filename)

    if not path.exists():

        print(f"File not found: {filename}")

        sys.exit(1)

    with open(path) as f:

        links = [l.strip() for l in f if l.strip().startswith("http")]

    return links

def open_url_in_chrome(url):

    """Open URL in the frontmost Chrome window using AppleScript"""

    script = f'''

    tell application "Google Chrome"

        activate

        if (count of windows) = 0 then

            make new window

        end if

        set URL of active tab of front window to "{url}"

    end tell

    '''

    subprocess.run(["osascript", "-e", script])

def main():

    all_links = load_links(LINKS_FILE)

    if not all_links:

        print("No links found.")

        sys.exit(1)

    if MAX_LINKS is None or MAX_LINKS >= len(all_links):

        links = all_links

    else:

        links = random.sample(all_links, MAX_LINKS)

    print(f"Randomly selected {len(links)} links")

    print("\nIMPORTANT:")

    print("1. Open Google Chrome normally")

    print("2. Make it maximized / full screen")

    print("3. Make sure Video DownloadHelper is visible")

    print("Starting in 8 seconds...")

    time.sleep(8)

    for i, url in enumerate(links, 1):

        print(f"\n[{i}/{len(links)}] Opening: {url}")

        try:

            open_url_in_chrome(url)

            time.sleep(5)          # wait for page + video to load

            print("  → Clicking VDH icon...")

            pyautogui.click(VDH_ICON_POS)

            time.sleep(1.8)

            print("  → Clicking Download...")

            pyautogui.click(DOWNLOAD_BUTTON_POS)

            time.sleep(2.2)

            print("  ✓ Download triggered")

        except Exception as e:

            print(f"  ✗ Error: {e}")

        time.sleep(DELAY_BETWEEN_VIDEOS + random.uniform(0.5, 2.0))

    print("\nAll done!")

if __name__ == "__main__":

    main()

