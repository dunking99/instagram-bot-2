
#!/bin/bash

if [ ! -f all_links_ordered_pineapple.txt ]; then

  echo "Run combine_all.sh first"

  exit 1

fi

# macOS-compatible random shuffle using Python

python3 -c '

import random

with open("all_links_ordered_pineapple.txt") as f:

    lines = [l.strip() for l in f if l.strip()]

random.shuffle(lines)

with open("all_links_random_pineapple.txt", "w") as f:

    f.write("\n".join(lines) + "\n")

print(f"Randomised → all_links_random_pineapple.txt ({len(lines)} links)")

'

