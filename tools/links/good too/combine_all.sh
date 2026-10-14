#!/bin/bash
echo "Combining all *_links.txt files (keeping times)..."

> all_links_ordered.txt

for f in *_links.txt; do
  # Only take lines that contain a real link
  grep -E '^https://' "$f" >> all_links_ordered.txt
done

# Remove exact duplicates while keeping order
awk '!seen[$0]++' all_links_ordered.txt > temp && mv temp all_links_ordered.txt

echo "Done → all_links_ordered.txt"
wc -l all_links_ordered.txt
