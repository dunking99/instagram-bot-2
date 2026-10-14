#!/bin/bash

echo "Splitting Pineapple links by duration..."

> under_8min.txt
> 8_to_12min.txt
> 12_to_23min.txt
> 23_to_32min.txt
> 32min_plus.txt
> unknown_duration.txt

grep -E '^https://.*\|' all_links_ordered_pineapple.txt | while read -r line; do
  link=$(echo "$line" | awk -F' *\\| *' '{print $1}')
  dur=$(echo "$line" | awk -F' *\\| *' '{print $2}')

  if [[ "$dur" == "??" || -z "$dur" ]]; then
    echo "$link" >> unknown_duration.txt
    continue
  fi

  mins=$(echo "$dur" | cut -d: -f1)
  secs=$(echo "$dur" | cut -d: -f2)
  total=$((10#$mins * 60 + 10#$secs))

  if (( total < 480 )); then
    echo "$link" >> under_8min.txt
  elif (( total < 720 )); then
    echo "$link" >> 8_to_12min.txt
  elif (( total < 1380 )); then
    echo "$link" >> 12_to_23min.txt
  elif (( total < 1920 )); then
    echo "$link" >> 23_to_32min.txt
  else
    echo "$link" >> 32min_plus.txt
  fi
done

for f in under_8min.txt 8_to_12min.txt 12_to_23min.txt 23_to_32min.txt 32min_plus.txt unknown_duration.txt; do
  awk '!seen[$0]++' "$f" > temp && mv temp "$f"
  echo "$f → $(wc -l < "$f") links"
done

echo "Done!"
