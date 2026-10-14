#!/bin/bash
cd "$(dirname "$0")"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
Q="sera+ryder+millie+morgan"
grab() {
  name="$1"; url="$2"; extra="${3:-X-Probe: 1}"
  code=$(curl -sS -L -m 25 -A "$UA" -H "Accept-Language: en" -H "$extra" -o "$name.html" -w "%{http_code} %{size_download} %{url_effective}" "$url" 2>&1)
  cf=$(grep -ciE "just a moment|cf-chl|captcha|attention required" "$name.html" 2>/dev/null)
  links=$(grep -oE 'href="[^"]+"' "$name.html" 2>/dev/null | wc -l | tr -d ' ')
  echo "$name | $code | cloudflare-or-captcha=$cf | hrefs=$links"
  sleep 2
}
grab pv_video "https://www.playvids.com/XV84IVJOs08/bjraw-sera-ryder-and-millie-morgan-nbq-nice-tits-wet-pussy"
grab pv_home "https://www.playvids.com/"
grab pv_search1 "https://www.playvids.com/search?q=$Q"
grab pv_search1_xhr "https://www.playvids.com/search?q=$Q" "X-Requested-With: XMLHttpRequest"
grab pv_search2 "https://www.playvids.com/search/$Q"
grab pw_video "https://www.pornwex.tv/video/365834/sera-ryder-and-millie-morgan-bjraw/"
grab pw_home "https://www.pornwex.tv/"
grab pw_search1 "https://www.pornwex.tv/search/$Q/"
grab pw_search2 "https://www.pornwex.tv/search/?q=$Q"
grab pw_search3 "https://www.pornwex.tv/?s=$Q"
grab pe_video "https://porneec.com/bjraw-sera-ryder-millie-morgan-millie-sera-share-the/"
grab pe_home "https://porneec.com/"
grab pe_search1 "https://porneec.com/?s=$Q"
grab pe_search2 "https://porneec.com/search/$Q/"
