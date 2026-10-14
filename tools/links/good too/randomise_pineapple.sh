#!/bin/bash

echo "Randomising all Pineapple lists..."

python3 -c '
import random, os

files = [
    "all_links_ordered_pineapple.txt",
    "under_8min.txt",
    "8_to_12min.txt",
    "12_to_23min.txt",
    "23_to_32min.txt",
    "32min_plus.txt",
    "unknown_duration.txt"
]

for f in files:
    if not os.path.exists(f):
        print(f"Skipping {f} (not found)")
        continue
    with open(f) as file:
        lines = [l.strip() for l in file if l.strip()]
    if not lines:
        print(f"{f} is empty")
        continue
    random.shuffle(lines)
    out = f.replace(".txt", "_random.txt")
    with open(out, "w") as file:
        file.write("\n".join(lines) + "\n")
    print(f"→ {out} ({len(lines)} links)")
'

echo "All randomised!"
