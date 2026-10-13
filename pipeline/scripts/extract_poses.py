#!/usr/bin/env python3
"""
Run MediaPipe Pose (new Tasks API) on extracted frames
"""

import json
import cv2
from pathlib import Path
from tqdm import tqdm
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# ============ CONFIG ============
FRAMES_DIR = Path.home() / "instagram-bot-2" / "pipeline" / "frames"
POSES_DIR  = Path.home() / "instagram-bot-2" / "pipeline" / "poses"
# ================================

# Download the model the first time (it will be cached)
model_path = Path.home() / ".mediapipe" / "pose_landmarker_heavy.task"
model_path.parent.mkdir(exist_ok=True)

if not model_path.exists():
    print("Downloading MediaPipe pose model (one-time)...")
    import urllib.request
    url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
    urllib.request.urlretrieve(url, model_path)
    print("Download complete.")

# Create the PoseLandmarker
base_options = python.BaseOptions(model_asset_path=str(model_path))
options = vision.PoseLandmarkerOptions(
    base_options=base_options,
    output_segmentation_masks=False,
    num_poses=2,                    # detect up to 2 people
    min_pose_detection_confidence=0.5,
    min_pose_presence_confidence=0.5,
    min_tracking_confidence=0.5
)
detector = vision.PoseLandmarker.create_from_options(options)

def process_image(image_path: Path, output_path: Path):
    image = cv2.imread(str(image_path))
    if image is None:
        return False

    # Convert to MediaPipe Image
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    detection_result = detector.detect(mp_image)

    data = {
        "image": image_path.name,
        "poses": []
    }

    for pose_landmarks in detection_result.pose_landmarks:
        landmarks = []
        for i, lm in enumerate(pose_landmarks):
            landmarks.append({
                "id": i,
                "x": lm.x,
                "y": lm.y,
                "z": lm.z,
                "visibility": lm.visibility if hasattr(lm, "visibility") else 0.0
            })
        data["poses"].append(landmarks)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    return True

def main():
    frame_files = list(FRAMES_DIR.rglob("*.jpg"))
    print(f"Found {len(frame_files)} frames")

    for frame_path in tqdm(frame_files, desc="Running pose estimation"):
        relative = frame_path.relative_to(FRAMES_DIR)
        output_path = POSES_DIR / relative.with_suffix(".json")
        process_image(frame_path, output_path)

    print("\nDone!")
    print(f"Pose data saved in: {POSES_DIR}")

if __name__ == "__main__":
    main()
