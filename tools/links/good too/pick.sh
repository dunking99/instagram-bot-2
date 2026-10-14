#!/bin/bash
# ============================================
# HOW TO USE
# ============================================
# ./pick.sh 15                  → picks 15 random links from all_links_random.txt
# ./pick.sh 20 ordered          → picks 20 random links from all_links_ordered.txt
# ./pick.sh 10 pineapple        → picks 10 random links from all_links_ordered_pineapple.txt
# ./pick.sh 8 orange
# ./pick.sh 12 pear
# ./pick.sh 5 other
# ============================================

N=${1:-10}
SOURCE=${2:-random}

case "$SOURCE" in
  ordered)   FILE="all_links_ordered.txt" ;;
  pineapple) FILE="all_links_ordered_pineapple.txt" ;;
  orange)    FILE="all_links_ordered_orange.txt" ;;
  pear)      FILE="all_links_ordered_pear.txt" ;;
  other)     FILE="all_links_ordered_other.txt" ;;
  *)         FILE="all_links_random.txt" ;;
esac

if [ ! -f "$FILE" ]; then
  echo "File not found: $FILE"
  exit 1
fi

echo "Picking $N random links from → $FILE"
echo "----------------------------------------"

python3 -c '
import random, sys
n = int(sys.argv[1])
filename = sys.argv[2]
with open(filename) as f:
    lines = [l.strip() for l in f if l.strip().startswith("http")]
if not lines:
    print("No links found in file")
    sys.exit(1)
chosen = random.sample(lines, min(n, len(lines)))
print("\n".join(chosen))
' "$N" "$FILE"
