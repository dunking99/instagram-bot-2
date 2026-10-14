#!/bin/bash

echo "Creating category files..."

> all_links_ordered_pineapple.txt
> all_links_ordered_orange.txt
> all_links_ordered_pear.txt
> all_links_ordered_other.txt

for f in *_links.txt; do
  awk '
    /--- Pineapple /     {cat="pineapple"; next}
    /--- Orange /      {cat="orange"; next}
    /--- Pear / {cat="pear"; next}
    /--- Other /   {cat="other"; next}
    /^https:\/\// {
      if (cat=="pineapple")     print >> "all_links_ordered_pineapple.txt"
      else if (cat=="orange") print >> "all_links_ordered_orange.txt"
      else if (cat=="pear") print >> "all_links_ordered_pear.txt"
      else if (cat=="other") print >> "all_links_ordered_other.txt"
    }
  ' "$f"
done

for cat in pineapple orange pear other; do
  file="all_links_ordered_${cat}.txt"
  awk '!seen[$0]++' "$file" > temp && mv temp "$file"
  echo "$file → $(wc -l < "$file") links"
done
