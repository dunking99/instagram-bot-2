# Streaming without downloading: site findings

Tested 2026-10-13 with curl, then in Chrome for all four sites (see 'Chrome results' below). One video per site, so treat as a first read.
All four sites run the same video software (KVS): the page lists links of the form `/get_file/<server>/<hash>/<id rounded to 000>/<id>/<file>.mp4/`.
Only the hash is unguessable, and it is in the page. One page request gives all qualities. The page's video ID is enough to open it (slug ignored on freepornvideos).
Each link redirects (1-2 hops) to a CDN address that is signed (`key=`, `end=` expiry, `ip=` of the asker). Never store the final address; fetch a fresh page each time.

## freepornvideos.xxx: PROVEN in Chrome
- Qualities: 480p, 720p. Page: exact length (`duration` meta, 1614 s in the test), 100 preview frames at `img.freepornvideos.xxx/<dir>/<id>/player/1..100.jpg` (~10 KB, 390x220; even spacing NOT verified).
- Range requests: 206. CDN sends `access-control-allow-origin: *`. Works with no referrer, the site's referrer or a localhost referrer.
- Chrome: Direct mode plays and seeks (about 0.2 s). Proxy mode works but seeks slowly (about 7 s, cause unknown).

## fpo.xxx: streams, but blocks a localhost referrer
- Link is in the player settings (`video_url` = low quality, `video_alt_url` = `_720p`), each ending `?v-acctoken=...`. Other get_file links on the page are other videos' `_preview.mp4`: ignore.
- Length from `duration` meta (1648 s in the test). No numbered preview frames (only `preview.jpg`; `320x180/1.jpg` and `2.jpg` exist, `10.jpg` does not).
- Range requests: 206 with no referrer, the site's referrer, or cookies. **403 when the Referer is http://127.0.0.1:8793/**. So Direct mode would need the page to send no referrer (`<meta name="referrer" content="no-referrer">`), or use the proxy.
- Not tested: token lifetime, Chrome playback.

## porntrex.com: streams at 4 qualities, blocks a localhost referrer
- Qualities: 480p (260 MB), 720p HD (458 MB), 1080p FHD (877 MB), 2160p 4K (2.86 GB) for the same video. Settings keys `video_url`, `video_alt_url`, `video_alt_url2`, `video_alt_url3`; files `<id>.mp4`, `_720p`, `_1080p`, `_2160p`.
- Range requests: 206 with no referrer (CDN `pcdn.cdntrex.com`, `access-control-allow-origin: *`). **410 with a localhost referrer.**
- Length: not found with simple patterns. Page is 485 KB.
- Not tested: Chrome playback, preview frames, token lifetime.

## xozilla.com: streams at 2 qualities, blocks a localhost referrer
- Qualities: 540p (165 MB), 720p (259 MB). Files `<id>.mp4` and `<id>hd.mp4`. Length in settings: `duration: '736'` (12:16).
- Range requests: 206 with no referrer (CDN `ahcdn.com`, same host family as freepornvideos, address is plain http). **410 with a localhost referrer.** No CORS header seen on the final host (playback does not need it).
- Behind Cloudflare, but the page loaded normally for a plain request.
- Not tested: Chrome playback, preview frames.

## Pattern so far
- Sites that reject a localhost referrer: fpo.xxx, porntrex, xozilla. freepornvideos accepts it.
- Plan when building readers: send no referrer in the page, and keep the proxy as a fallback. A reader per site only needs: where the qualities are, where the length is, how to get preview frames (if any).
- Other sites from the Video Finder list that showed a `video_url:` block on one page: porngrey, shyfap, pornzog, porntop. xhamster uses HLS (`.m3u8`). youporn/eporner/tnaflix/pornflip/xxxbunker unclear. All untested for streaming.

## Not a source
- fapello.com: Cloudflare challenge ("Just a moment...", 403). Not scraped. Not worked around.

## Chrome results (2026-10-13, all four added to the test dashboard)
Mode Direct needs `<meta name="referrer" content="no-referrer">` (added to index.html) because fpo.xxx, porntrex and xozilla refuse a localhost referrer.
Seek to 40% of the video, then play 3 s (muted); one video per site:

| Site | Quality tested | Size / length | Direct: seek, played | Proxy: seek, played |
|---|---|---|---|---|
| freepornvideos | 480p | 853x480, 1614 s | 0.3 s, 2.96 s | 4.7 s, 2.96 s |
| fpo.xxx | LQ | 854x480, 1648 s | 1.2 s, 2.96 s | 2.1 s, 2.96 s |
| porntrex | 480p | 854x480, 2244 s (length not on the page) | 1.4 s, 2.98 s | 4.8 s, 2.96 s |
| xozilla | 540p | 960x540, 736 s | 0.9 s, 2.71 s | 2.3 s, 1.1 s (slow start) |

- Page lengths matched the file for freepornvideos (1614/1615), fpo.xxx (1648) and xozilla (736). Porntrex has no usable length in the page; the file says 2244 s.
- fpo.xxx names its qualities "LQ"/"HQ" (no pixel height); the file played was 854x480.
- Gotcha: `/usr/bin/python3` (3.9, LibreSSL 2.8) cannot reach porntrex's CDN (`TLSV1_ALERT_PROTOCOL_VERSION`). The server runs on `/opt/homebrew/bin/python3` (OpenSSL 3); `./start.sh` does this.
- Gotcha: porntrex has an unrelated `duration: 5` in its page; durations under 30 s are ignored.
- Not tested: token/link lifetime, other qualities (720p/1080p/4K) in a browser, long-run seeking, more than one video per site.

## Get frames (added 2026-10-13)
- Stream test page: "Get frames" panel (every 5/10/15/30/60 s, from/to minutes, "From here", height 224/360/480). Saves to `tools/stream-test/frames/<job>/f_<seconds>.jpg`; "Delete these frames" removes the folder. Max 600 per job.
- How: resolve the site's redirects once, then one ffmpeg call per frame (`-ss T -i <final url>`), 6 in parallel (3 for fpo.xxx), 3 tries each. Resolving once cut a frame from 5.2 s to 2.0 s; parallel brings it to 0.5-1 s.
- Measured in Chrome, 19 frames each, 10 s spacing: freepornvideos 0.79 s/frame, xozilla 0.56, porntrex 0.97, fpo.xxx 2.24 (slow; refused some requests at 6 parallel, 1 of 21 failed once before retries/limit).
- `?v=<page link>&t=<seconds>&embed=1` opens the page straight into a video (used by the data18 page).

## Data18 scraper integration (added 2026-10-13)
- `tools/data18/server.py`: `/api/stream/ensure` starts `tools/stream-test/start.sh` if port 8793 is down and returns its address.
- `tools/data18/static/index.html`: when the chosen Find-on-sites result is on freepornvideos, fpo.xxx, porntrex or xozilla, the result bar shows "Watch & get frames", which opens Stream test in a pop-up iframe (`#sm`) at the minute of the frame it was opened from (still k = minute k-1). Seen working inside the Light table's Data18 page. Light table code was not changed.
- Backups: `server.py.bak-stream`, `static/index.html.bak-stream` (data18-scraper); `server.py.bak-noframes`, `index.html.bak-noframes` (stream-test).
- Limits: the iframe is http://127.0.0.1:8793, so this works on the Mac only (not from the tailnet/phone). Video Finder only searches freepornvideos, fpo.xxx and xozilla of the four (no porntrex), so porntrex results can't be chosen there yet.

## tnaflix, porneec, playvids, pornflip added (2026-10-14)
- Found by hand (your document) and confirmed by `play_test.py` in Google Chrome 155: each page names its video, the address plays and seeks straight from the site with **no referrer** (Direct mode, no proxy), 2 videos per site, seek to 40% in 0.4-1.1 s.
  - tnaflix: `<source ... size="144|240|360|480|720">` mp4 list in `<video id="video-player">`, signed (`secure=...,<unix time>`, valid about an hour or two, so the page is fetched fresh every time). `data-duration` gives the length.
  - porneec: `<meta itemprop="contentUrl" content="https://....b-cdn.net/xxx.mp4">`, a plain unsigned mp4. Length in `itemprop="duration"` (`P0DT0H25M0S`).
  - playvids and pornflip: `<source type="application/x-mpegURL" src="...master.m3u8?seclink=...&sectime=...">` (same video host `userscontent.net`, same player). **HLS plays natively in a recent Chrome** (155 yes; the Chromium 141 used for testing here no; Safari yes; Firefox no). Length for playvids is in the JSON `"duration": "T25M48S"`.
- `server.py`: `PAGE_SOURCES` + `parse_page_sources()` read those addresses first; yt-dlp / page scan stay as the fallback. pornflip was removed from `NOT_STREAMABLE`. `page_duration()` now reads `P0DT0H25M0S`, `T25M48S` and `data-duration`.
- Frames from HLS: ffmpeg reads the playlist itself. `FFMPEG_HEADERS` gives it the page as referrer (frames only; the browser sends none). Checked here with a local HLS stream: frames at 0, 12 and 31 s, no failures. Not yet checked on the real sites.
- `data18/static/index.html` `STREAM_SITES` and `video-finder/sites.py` `STREAMABLE` now include the four, so "Watch & get frames" shows for them and the Finder searches them as streamable sites.
- Still untested in a browser: eporner, pornhub, porntop, youporn, xhamster, trendyporn, xxxbunker (read through yt-dlp / page scan; frames worked in the probe). Not working yet: youcrazyx, yrprno (video id bug), pornwex, pornzog. Set aside: shyfap, porngrey (Cloudflare answers 11 bytes to non-browser requests).

## The other eleven sites added (2026-10-14)
eporner, pornhub, porntop, youporn, xhamster, trendyporn, xxxbunker, youcrazyx, yrprno, pornwex, pornzog. The button (`STREAM_SITES` in `data18/static/index.html`) and `STREAMABLE` in `video-finder/sites.py` now cover every Video Finder site except porngrey and shyfap (19 of 21).
- **Not yet run against the live sites.** The session that wrote this had no internet; run `play_test.py` (see below) to find out which of these really play.
- eporner, pornhub, youporn, xhamster, trendyporn, xxxbunker: no code change here (already in `SITES`; read through yt-dlp or a page scan, frames worked in `probe_sites.py`). The pop-up plays yt-dlp sources through the local proxy (they carry a Referer).
- porntop: was missing from `SITES`; added (yt-dlp read it in `probe_sites.py`).
- youcrazyx, yrprno: crashed with `'NoneType' object has no attribute 'group'` because the video id came from the last 6+ letters/digits of the link and their links end `-85892.html` (5 digits). Fixed (`.html` allowed, 5+ characters, plus a last fallback). Otherwise they take the same path as trendyporn.
- pornwex: a normal KVS site, but its settings variable has a random name (`var t2163b28e2c = {`), which is why yt-dlp said "Unable to extract flashvars". `video_url` is `function/0/https://.../get_file/51/<hash>/...`, the first 32 letters of `<hash>` shuffled by the page's `license_code`. `kvs_license_token()` / `kvs_real_url()` are yt-dlp's method (public domain); on the saved pornwex page, and on 500 random cases, they give the same answer as yt-dlp's own function. `parse_sources()` now accepts `function/0/` addresses and pornwex is in `KVS`.
- pornzog: only embeds another site's player (`vxxx.com/embed-...`). `follow_embed()` skips the site's own frames and adverts, opens the embedded player's page (Referer = the pornzog page), reads it with the KVS reader, then the page-source reader, the page scan, and yt-dlp; the sources carry `Referer = the player page`, so they play through the proxy. **Only tested on a made-up page**: nobody has looked at vxxx's real source yet. Length comes from `duration: '08:00'` on the pornzog page.
- **Bug fixed for all sites with letters in their video id** (playvids `lW64b_dDjR0`, porneec slugs): the frame folder name used the raw id, but the file routes only accepted digits, so the pop-up's frame pictures could not load. Folder names are now letters and digits only (`playvids_lw64bddjr0_<time>`), and the two routes accept that.
- `play_test.py` default mode drives this page itself (the real pop-up, including its direct-to-proxy fallback) for every site: `tools/data18/.venv/bin/python tools/stream-test/play_test.py` (needs Google Chrome). `--direct` is the earlier address-only test for four sites.

## Free frames per site (probe_frames.py, 2026-10-14)
Goal: many frames per video without streaming (the model only needs 224 px input, so preview thumbnails are enough). `probe_frames.py` reads one video page per site and looks for (1) numbered images in the video's own folder (counts how many exist), (2) storyboard / mosaic sheets (`#` or `{n}` in an address), (3) WebVTT thumbnail tracks, (4) HLS playlists with an I-frame stream, (5) preview videos. Writes `frames_probe_results.txt/.json` and keeps the first/last frame in `frames_probe_samples/` (not in git).
What was already known from saved pages and the notes, before the first run: freepornvideos 100 numbered previews (390x220); tnaflix `data-mosaic=".../mosaic/#.jpg"` storyboard (number of sheets / frames per sheet unknown); fpo.xxx only `1.jpg` and `2.jpg`; pornwex's page links only `1.jpg` (KVS screenshots, count unknown); playvids cards carry `data-folder` + `data-rotate="preview"` and the video's folder holds oddly numbered files (773, 1033), so the pattern is unclear; porneec showed nothing.

## capture_network.py (2026-10-14)
Opens Chrome (logged out, fresh window) on any page, lets you use it, then lists the data requests that returned picture addresses and the groups of pictures that were loaded (folder, numbered or not, KB, pixel size). Use it to learn how a JavaScript page gets its pictures before writing a reader. Tokens in addresses are replaced by their length; cookies are never recorded.
Tested on a made-up page (empty shell + hidden JSON list of 64 screenshots + click to show them). First real use: pornbox's watch page, whose screenshot gallery (64+ evenly spaced frames) was seen in a screenshot.

## Pornbox (2026-10-14)
`capture_network.py` on a logged-out Pornbox watch page found one request that lists the pictures: `GET https://pornbox.com/contents/<id>` (XHR, ~76 KB JSON; ThePornDB's `scenes/networkPornbox.py` uses the same endpoint with header `X-Requested-With: XMLHttpRequest` and cookie `agree18=1`). It listed 501 picture addresses on a CDN (`cdn77-image.gtflixtv.com`), signed in the path with an expiry of 2033-01-21, so they can be stored. Likely the same pictures at several sizes; `inspect_json.py` sorts the 501 into different pictures and shows which field holds the screenshots. `/contents/<id>/related` lists 52 related scenes; `/media/<n>/stream?label_id=` returns player info (qualities).
