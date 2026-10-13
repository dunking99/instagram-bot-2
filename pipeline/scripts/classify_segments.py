#!/usr/bin/env python3
"""
Improved pose + SigLIP classification → timed segments
"""

import json
import math
from pathlib import Path
from tqdm import tqdm
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModel

# ============ CONFIG ============
FRAMES_DIR  = Path.home() / "instagram-bot-2" / "pipeline" / "frames"
POSES_DIR   = Path.home() / "instagram-bot-2" / "pipeline" / "poses"
OUTPUT_DIR  = Path.home() / "instagram-bot-2" / "pipeline" / "outputs"
INTERVAL    = 2.0
MIN_SEGMENT = 8.0
# ================================

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- SigLIP setup ----------
print("Loading SigLIP model (first time may take a minute)...")
model_id = "google/siglip-base-patch16-224"
processor = AutoProcessor.from_pretrained(model_id)
model = AutoModel.from_pretrained(model_id)
model.eval()

device = "mps" if torch.backends.mps.is_available() else "cpu"
model = model.to(device)

LABELS = [
    "a woman giving a blowjob",
    "doggystyle sex position",
    "missionary sex position",
    "cowgirl sex position",
    "standing sex from behind",
    "a couple having sex",
    "other or transition scene"
]

label_map = {
    "a woman giving a blowjob": "blowjob",
    "doggystyle sex position": "doggystyle",
    "missionary sex position": "missionary",
    "cowgirl sex position": "cowgirl",
    "standing sex from behind": "standing",
    "a couple having sex": "sex",
    "other or transition scene": "other"
}

def classify_with_siglip(image_path: Path):
    try:
        image = Image.open(image_path).convert("RGB")
        inputs = processor(text=LABELS, images=image, return_tensors="pt", padding=True).to(device)
        
        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits_per_image
            probs = torch.sigmoid(logits)[0]
        
        best_idx = probs.argmax().item()
        best_label = LABELS[best_idx]
        confidence = probs[best_idx].item()
        
        return label_map[best_label], confidence
    except Exception:
        return "other", 0.0

# ---------- Simple geometric helper ----------
def get_landmark(landmarks, idx):
    if idx < len(landmarks):
        return landmarks[idx]
    return None

def classify_pose_geometry(landmarks):
    if not landmarks or len(landmarks) < 29:
        return None

    nose = get_landmark(landmarks, 0)
    l_hip = get_landmark(landmarks, 23)
    r_hip = get_landmark(landmarks, 24)
    l_knee = get_landmark(landmarks, 25)
    r_knee = get_landmark(landmarks, 26)
    l_wrist = get_landmark(landmarks, 15)
    r_wrist = get_landmark(landmarks, 16)

    def vis(p):
        return p is not None and p.get("visibility", 0) > 0.4

    # Strong doggystyle signal
    if vis(l_knee) and vis(r_knee) and vis(l_wrist) and vis(r_wrist):
        if (l_knee["y"] > 0.6 and r_knee["y"] > 0.6 and
            l_wrist["y"] > 0.55 and r_wrist["y"] > 0.55):
            return "doggystyle"

    return None

def process_video(pose_folder: Path, frame_folder: Path):
    json_files = sorted(pose_folder.glob("*.json"))
    if not json_files:
        return []

    frame_labels = []

    for i, jf in enumerate(json_files):
        with open(jf) as f:
            data = json.load(f)

        landmarks = data["poses"][0] if data.get("poses") else []
        
        # Corresponding frame image
        frame_name = jf.stem + ".jpg"
        image_path = frame_folder / frame_name

        # 1. Try geometry first (fast + strong when it works)
        geo_label = classify_pose_geometry(landmarks)

        # 2. Always run SigLIP
        sig_label, conf = classify_with_siglip(image_path)

        # Decision logic
        if geo_label:
            final = geo_label
        elif conf > 0.35:
            final = sig_label
        else:
            final = "other"

        timestamp = i * INTERVAL
        frame_labels.append((timestamp, final))

    # Group into segments
    segments = []
    if not frame_labels:
        return segments

    current_label = frame_labels[0][1]
    start_time = frame_labels[0][0]

    for ts, label in frame_labels[1:]:
        if label != current_label:
            if ts - start_time >= MIN_SEGMENT:
                segments.append({
                    "start": round(start_time, 1),
                    "end": round(ts, 1),
                    "label": current_label
                })
            current_label = label
            start_time = ts

    # last segment
    end_time = frame_labels[-1][0] + INTERVAL
    if end_time - start_time >= MIN_SEGMENT:
        segments.append({
            "start": round(start_time, 1),
            "end": round(end_time, 1),
            "label": current_label
        })

    return segments

def main():
    video_folders = [p for p in POSES_DIR.rglob("*") if p.is_dir() and any(p.glob("*.json"))]
    print(f"Found {len(video_folders)} videos")

    for pose_folder in tqdm(video_folders, desc="Classifying"):
        relative = pose_folder.relative_to(POSES_DIR)
        frame_folder = FRAMES_DIR / relative

        segments = process_video(pose_folder, frame_folder)

        output_file = OUTPUT_DIR / f"{relative}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump({
                "video": str(relative),
                "segments": segments
            }, f, indent=2)

    print("\nDone! Results in:", OUTPUT_DIR)

if __name__ == "__main__":
    main()
