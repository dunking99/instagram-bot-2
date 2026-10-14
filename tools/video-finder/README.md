# Video Finder

Standalone. Finds a data18 scene on other sites and shows the best match per site, with thumbnail and score.

    ./start.sh        # opens http://127.0.0.1:8792      ./stop.sh to stop

- Input: a data18 scene link (read from the data18 scraper's SAVED results, read-only) or `Title - Performer`.
- Fixed rules, no AI: `matcher.py` + `rules.json` (editable in the page). Same input, same ranking.
- `sites.py`: one search address + one card reader per site. To fix a site that changed its layout, edit only its entry there.
- Python 3.9, standard library only. Listens on 127.0.0.1 only. Touches no other tool.
- Searches are saved in `data/jobs/` (last 30) so a page reload keeps the results.

## Search strategy (changed 2026-10-14)
- Sites: 21 (added playvids, pornwex, porneec on 2026-10-14; before that porntrex, trendyporn, youcrazyx, yrprno, pornhub). pornwex and porneec use page 1 only. `STREAMABLE` now has every site except porngrey and shyfap (19 of 21): tnaflix, porneec, playvids, pornflip were play-tested in Chrome on 2026-10-14; the other eleven added the same day are not yet run against the live sites (`tools/stream-test/play_test.py`). `sites.STREAMABLE` = every site except porngrey and shyfap.
- Per site, in `search_site`: **main queries** (page 1 only): `{title_core} {performer}`, `{performer}`, `{title_core}`, `{performer} {studio} {title_core}`; stops at a confident match.
  If nothing was found: **extra formats** (only on `extra_sites`): `{performer} {title_core}`, `{title} {performer}`, `{title_key} {performer}`, `{title_key}`;
  then **deep pages** of the performer query (only on `deep_sites`).
- Order of sites: streamable sites first. The others are skipped when a streamable site has a strong match (confident, or "possible" with real title evidence AND the same length as data18).
  Page button "Search all sites" (or `all_sites: true` in the request) searches them anyway. `rules.json` `streamable_only: 1` never searches them (about a third of the requests).
- Measured on 7 saved videos (final replay): every earlier streamable match kept (8/8, same top result), 7 new ones found, 4.2 requests per site-search (was 4.5, now with 18 sites and more formats), about 59 s per video.
  Per format, matches that no other format found: `{title_core} {performer}` 8, `{performer}` 13, `{title_core}` 7, `{performer} {studio} {title_core}` 2; the permutation and keyword formats 0 (kept as extras).
- Scoring: dates ("2026 02 23"), "full/video/hd" and similar filler no longer count as extra title words, so an exact match on trendyporn-style titles reaches "confident". No saved verdict changed (568 re-scored).
- Google/DuckDuckGo cannot be searched by a script (Google redirects, DuckDuckGo returns a bot challenge). The pages show "Google: All" / "Google: Videos" links that open the search in your own browser.
- Backups: `*.bak-speed` (before this change).
