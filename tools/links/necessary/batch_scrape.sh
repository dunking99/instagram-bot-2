#!/bin/bash

urls=(
  "https://fruitsvids.com/video-creators/artist1-exclusive-videos/6/"
  "https://fruitsvids.com/video-creators/artist2-exclusive-videos/5/"
  "https://fruitsvids.com/video-creators/artist3-exclusive-videos/4/"
  "https://fruitsvids.com/video-creators/artist-seven-exclusive-videos/2/"
  "https://fruitsvids.com/video-creators/artist5-exclusive-videos/3/"
  "https://fruitsvids.com/video-creators/artist-6-exclusive-videos/2/"
  "https://fruitsvids.com/video-creators/artist8-exclusive-videos/3/"
  "https://fruitsvids.com/video-creators/artist25-exclusive-videos/6/"
  "https://fruitsvids.com/video-creators/artist-eleven-exclusive-videos/2/"
  "https://fruitsvids.com/video-creators/luke-moore-exclusive-videos/2/"
  "https://fruitsvids.com/video-creators/artist101-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist102-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist103-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist104-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist105-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist106-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist107-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist108-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist109-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist110-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist111-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist112-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist113-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist114-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist115-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist116-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist117-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist118-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist119-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist120-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist121-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist122-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist123-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist124-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist125-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist126-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist127-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist128-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist129-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist130-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist131-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist132-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist133-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist134-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist135-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist136-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist137-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist138-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist139-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist140-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist141-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist101-exclusive-videos/"
  "https://fruitsvids.com/models/artist102-videos/"
  "https://fruitsvids.com/video-creators/emma-clarke-new-videos/"
  "https://fruitsvids.com/models/artist104/"
  "https://fruitsvids.com/video-creators/artist105-new-videos/"
  "https://fruitsvids.com/models/sophie-turner-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist107-videos/"
  "https://fruitsvids.com/models/artist108-exclusive-videos/"
  "https://fruitsvids.com/video-creators/lily-evans/"
  "https://fruitsvids.com/models/artist110-new-videos/"
  "https://fruitsvids.com/video-creators/artist111-exclusive-videos/"
  "https://fruitsvids.com/models/olivia-hart-videos/"
  "https://fruitsvids.com/video-creators/artist113/"
  "https://fruitsvids.com/models/artist114-exclusive-videos/"
  "https://fruitsvids.com/video-creators/mia-novak-new-videos/"
  "https://fruitsvids.com/models/artist116-videos/"
  "https://fruitsvids.com/video-creators/artist117-exclusive-videos/"
  "https://fruitsvids.com/models/chloe-bennett/"
  "https://fruitsvids.com/video-creators/artist119-new-videos/"
  "https://fruitsvids.com/models/artist120-videos/"
  "https://fruitsvids.com/video-creators/grace-miller-exclusive-videos/"
  "https://fruitsvids.com/models/artist122-new-videos/"
  "https://fruitsvids.com/video-creators/artist123/"
  "https://fruitsvids.com/models/ruby-jensen-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist125-videos/"
  "https://fruitsvids.com/models/artist126-exclusive-videos/"
  "https://fruitsvids.com/video-creators/ella-fisher-new-videos/"
  "https://fruitsvids.com/models/artist128/"
  "https://fruitsvids.com/video-creators/artist129-videos/"
  "https://fruitsvids.com/models/ava-morgan-exclusive-videos/"
  "https://fruitsvids.com/video-creators/artist131-new-videos/"
  "https://fruitsvids.com/models/artist132-exclusive-videos/"
  "https://fruitsvids.com/video-creators/zoe-carter-videosis/"
  "https://fruitsvids.com/models/artist134/"
  "https://fruitsvids.com/video-creators/artist135-exclusive-videos/"
  "https://fruitsvids.com/models/hannah-lopez-new-videos/"
  "https://fruitsvids.com/video-creators/artist137-videos/"
  "https://fruitsvids.com/models/artist138-exclusive-videos/"
  "https://fruitsvids.com/video-creators/isla-reid/"
  "https://fruitsvids.com/models/artist140-new-videos/"
  "https://fruitsvids.com/video-creators/artist141-exclusive-videos/"
)

echo "Checking which creators still need scraping..."
echo

need_scrape=()

for url in "${urls[@]}"; do
  # Generate the expected filename the same way the scraper does
  slug=$(echo "$url" | sed -E 's|.*/video-creators/||; s|.*/models/||; s|/$||; s|/[0-9]+$||; s|-videosis$||; s|-exclusive-videos$||; s|-new-videos$||; s|-videos$||; s|-|/|g; s|/|_|g')
  # Simpler and more reliable way:
  filename=$(python3 -c "
from urllib.parse import urlparse
import re
url = '$url'
path = urlparse(url).path.strip('/')
parts = path.split('/')
if parts and parts[0] in ('es','fr','pt','de','it','zh','ja','ru','tr'):
    parts = parts[1:]
for p in reversed(parts):
    if p and not p.isdigit() and 'sort_by' not in p:
        slug = re.sub(r'-(videos|exclusive-videos|videosis|new-videos)$', '', p)
        print(slug.replace('-', '_') + '_links.txt')
        break
")

  if [[ -f "$filename" ]]; then
    # Check if the file has real content (at least a few https links + duration marker)
    count=$(grep -c '^https://' "$filename" 2>/dev/null || echo 0)
    has_duration=$(grep -c '|' "$filename" 2>/dev/null || echo 0)

    if (( count > 3 && has_duration > 0 )); then
      echo "✓ Skipping $filename  ($count links already present)"
      continue
    else
      echo "→ Needs re-scrape: $filename  (only $count links)"
      need_scrape+=("$url")
    fi
  else
    echo "→ Needs scrape: $filename  (file missing)"
    need_scrape+=("$url")
  fi
done

echo
echo "========================================"
echo "Will scrape ${#need_scrape[@]} creators (out of ${#urls[@]})"
echo "========================================"
echo

for url in "${need_scrape[@]}"; do
  echo "========================================"
  echo "Processing: $url"
  echo "========================================"
  python3 scrape_fruitsvids.py "$url"
  echo
  sleep 2
done

echo "All done!"
