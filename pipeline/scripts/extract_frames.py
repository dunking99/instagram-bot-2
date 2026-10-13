#!/usr/bin/env python3
"""
Extract frames from videos in library/ (recursive)
Does NOT move or modify original videos.
"""

import os
import subprocess
from pathlib import Path
from tqdm import tqdm

# ============ CONFIG ============
LIBRARY_DIR = Path.home() / "instagram-bot-2" / "library"
OUTPUT_DIR = Path.home() / "instagram-bot-2" / "pipeline" / "frames"
INTERVAL_SECONDS = 2          # one frame every 2 seconds
MAX_VIDEOS = 10               # ← change this number (start with 5 or 10)
# ================================

def find_videos(root: Path):
    videos = []
    for path in root.rglob("*"):
        if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            videos.append(path)
    return sorted(videos)

def extract_frames(video_path: Path, output_folder: Path):
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # ffmpeg command
    cmd = [
        "ffmpeg",
        "-y",                          # overwrite if exists
        "-i", str(video_path),
        "-vf", f"fps=1/{INTERVAL_SECONDS}",
        "-q:v", "2",                   # high quality jpg
        str(output_folder / "%06d.jpg")
    ]
    
    # Run quietly
    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0

def main():
    print("Scanning for videos...")
    all_videos = find_videos(LIBRARY_DIR)
    print(f"Found {len(all_videos)} videos in total.")

    videos_to_process = all_videos[10:20]
    print(f"Will process the first {len(videos_to_process)} videos.\n")

    for video in tqdm(videos_to_process, desc="Extracting frames"):
        # Create a clean relative path: creator/video_name
        relative = video.relative_to(LIBRARY_DIR)
        creator = relative.parts[0] if len(relative.parts) > 1 else "unknown"
        video_name = video.stem

        out_folder = OUTPUT_DIR / creator / video_name
        success = extract_frames(video, out_folder)

        if not success:
            print(f"\nFailed on: {video}")

    print("\nDone!")
    print(f"Frames saved in: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
