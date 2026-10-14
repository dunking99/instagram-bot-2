#!/bin/bash

urls=(
  "https://pimpbunny.com/onlyfans-creators/madiiitay-exclusive-leaks/6/"
  "https://pimpbunny.com/onlyfans-creators/hannah-jo-exclusive-leaks/5/"
  "https://pimpbunny.com/onlyfans-creators/sky-bri-new-leaks/4/"
  "https://pimpbunny.com/onlyfans-creators/cheerleader-kait-new-leaks/2/"
  "https://pimpbunny.com/onlyfans-creators/solazola-leaked/3/"
  "https://pimpbunny.com/onlyfans-creators/urfavbellabby-exclusive-leaks/2/"
  "https://pimpbunny.com/onlyfans-creators/anya-matusevich-exclusive-new-leaks/3/"
  "https://pimpbunny.com/onlyfans-creators/lucy-mochi-new-leaks/6/"
  "https://pimpbunny.com/onlyfans-creators/kinsley-wyatt/2/"
  "https://pimpbunny.com/onlyfans-creators/lia-lin-leaked/2/"
  "https://pimpbunny.com/onlyfans-creators/paige-insco-exclusive-leaks/"
  "https://pimpbunny.com/onlyfans-creators/nikkinicolexxx/"
  "https://pimpbunny.com/onlyfans-creators/bunnydollstella-leaked/"
  "https://pimpbunny.com/onlyfans-creators/hannahgrape/"
  "https://pimpbunny.com/onlyfans-creators/lildaisyfoxx/"
  "https://pimpbunny.com/onlyfans-creators/sofiaweiderman/"
  "https://pimpbunny.com/onlyfans-creators/snowwhyte222/"
  "https://pimpbunny.com/onlyfans-creators/thedakotatyler-leaks/"
  "https://pimpbunny.com/onlyfans-creators/sydneycolexxx/"
  "https://pimpbunny.com/onlyfans-creators/layla-jenner-leaks/"
  "https://pimpbunny.com/onlyfans-creators/hope-heaven-new-leaks/"
  "https://pimpbunny.com/onlyfans-creators/livy-mae/"
  "https://pimpbunny.com/onlyfans-creators/missschar18/"
  "https://pimpbunny.com/models/anastangel/"
  "https://pimpbunny.com/onlyfans-creators/lolajean18-leaks/"
  "https://pimpbunny.com/onlyfans-creators/della-cate-leaks/"
  "https://pimpbunny.com/onlyfans-creators/kyler-quinn/"
  "https://pimpbunny.com/onlyfans-creators/rika-fane/"
  "https://pimpbunny.com/onlyfans-creators/shawzzz-new-leaks/"
  "https://pimpbunny.com/onlyfans-creators/katie-pardon-leaked/"
  "https://pimpbunny.com/onlyfans-creators/scvua-leaked/"
  "https://pimpbunny.com/onlyfans-creators/emmabelovedxo-exclusive-new-leaks/"
  "https://pimpbunny.com/onlyfans-creators/ashleyscott-leaked/"
  "https://pimpbunny.com/onlyfans-creators/izzy-rae-exclusive-leaks/"
  "https://pimpbunny.com/onlyfans-creators/madiruvee-new-leaks/"
  "https://pimpbunny.com/onlyfans-creators/alexybaby/"
  "https://pimpbunny.com/onlyfans-creators/gina-valentina-leaks/"
  "https://pimpbunny.com/onlyfans-creators/britni-kitten-leaked/"
  "https://pimpbunny.com/onlyfans-creators/kendall-beck-new-leaks/"
  "https://pimpbunny.com/onlyfans-creators/kylie-rocket/"
  "https://pimpbunny.com/onlyfans-creators/lilou-danero-leaks/"
  "https://pimpbunny.com/onlyfans-creators/spiraling-spirit-leaks/"
  "https://pimpbunny.com/models/spiritemoon/"
  "https://pimpbunny.com/onlyfans-creators/ryan-reid-leaks/"
  "https://pimpbunny.com/onlyfans-creators/myra-moans/"
  "https://pimpbunny.com/onlyfans-creators/stefany-kyler/"
  "https://pimpbunny.com/onlyfans-creators/malia-rain-leaked/"
  "https://pimpbunny.com/onlyfans-creators/kyliechase-leaks/"
  "https://pimpbunny.com/onlyfans-creators/kiara-cole/"
  "https://pimpbunny.com/onlyfans-creators/lily-larimar-leaks/"
  "https://pimpbunny.com/onlyfans-creators/sonya-blaze-leaked/"
)

echo "Checking which creators still need scraping..."
echo

need_scrape=()

for url in "${urls[@]}"; do
  # Generate the expected filename the same way the scraper does
  slug=$(echo "$url" | sed -E 's|.*/onlyfans-creators/||; s|.*/models/||; s|/$||; s|/[0-9]+$||; s|-leaked$||; s|-exclusive-leaks$||; s|-new-leaks$||; s|-leaks$||; s|-|/|g; s|/|_|g')
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
        slug = re.sub(r'-(leaked|exclusive-leaks|leaks|new-leaks)$', '', p)
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
  python3 scrape_pimpbunny.py "$url"
  echo
  sleep 2
done

echo "All done!"
