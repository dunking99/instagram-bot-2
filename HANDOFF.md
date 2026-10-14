# Handoff: 2026-10-14 (cloud session -> Claude Code in the terminal)

> Written by the Claude session that worked in the cloud (no internet, GitHub only) for the Claude Code session that continues on the owner's Mac.
> The previous handoff (12 Oct, before the folders were merged) is archived at `docs/HANDOFF_2026-10-12.md`; its model/training notes are still valid.

## 0. Read this first

**What changes now.** The cloud session could not open any website, so every site-related thing below was written against saved pages and fake servers and
marked "not yet run live". **You are on the owner's Mac with a network, ffmpeg, yt-dlp, Chrome and the real dashboard, so you can run things directly.
Do that: verify live, instead of asking the owner to paste terminal output** (that is how it was done before and it was slow).

**First five minutes**
1. `cd ~/instagram-bot-2 && git status && git branch --show-current && git log --oneline -5`. The cloud work lives on branch `claude/jolly-cannon-88sel9`
   (tip `ab7b6ff` or later). `origin/main` is behind it (`b2be86d`). The owner ran `git pull origin claude/jolly-cannon-88sel9` into their local checkout, so check which
   branch they are on and whether `pornbox_probe.py` (the newest commit) is present. Ask the owner how they want branches handled before pushing anything to `main`.
2. Run the one test that was pending when this session ended (section 5, P1): `tools/data18/.venv/bin/python tools/stream-test/pornbox_probe.py 127185`.
3. Ask the owner two things you cannot know: (a) "fix the Stream test failures now?" (they said "don't fix yet" while analysing, then moved on), (b) the chain question in P4.

## 1. The owner and how to work with them

- One person, alone, Mac (zsh), long sessions. Expert; wants speed, density, and **dashboards with buttons, not scripts or folders**.
- **Brief, simple explanations.** Plain words, short tables. When they ask for "a very brief outline", give one.
- They paste terminal output or screenshots. When you can run it yourself, do.
- **Autonomy:** when they say "you know what to do, no need to go through me", proceed. When they say "don't fix yet / brainstorming", do not edit code.
- **Do not argue with their domain judgement.** They said more frames per video are better ("Not true at all. Don't fight me on this") when I suggested diminishing returns; drop it.
  Frames are the *second* step; the first is getting the **video** (watch a segment without downloading).
- Report honestly what was verified vs inferred. **Never claim a file was saved/pushed without checking** (the cloud session once said it saved a file it had not; check with `ls`/`git log`).
- zsh paste gotchas from earlier: a `#` comment containing an apostrophe in a pasted block opened a `quote>` prompt and swallowed the whole paste. Give commands without `#` comments,
  one logical step per block; heredocs with `<<'EOF'` pasted fine.
- Content is personal and sensitive. Nothing leaves the machine except requests to the sites. They know the sites' terms probably forbid automated access and decide; keep requests polite
  (a few per second per site, small parallelism). Do not try to defeat Cloudflare/bot checks or logins.
- Disk is low (about 6 GB free): never store large image sets at full size; keep 224 px copies for the model.

## 2. The system

| What | Port | Where | Notes |
|---|---|---|---|
| Postroom (FastAPI) | 8503 | `server.py`, `random_post.py`, `ui/` | **Original; leave `server.py` and `ui/` alone** unless asked. Python 3.9 (`/usr/bin/python3`): no `X \| None`, no `match` |
| Light table (the UI the owner uses) | 8504 | `lighttable_server.py`, `ui-lighttable/` (React/Vite, `npx vite build`) | Proxies Postroom, `/d18/` = data18 page in an iframe, `/lt/*` job endpoints |
| data18 scraper + dashboard | 8790 | `tools/data18/` (own `.venv`: requests, bs4, playwright; **never install torch there**) | Started on demand by the Light table. Runs the B/32 model as a subprocess in `CLIP Training/.venv` |
| Links (collect + download) | 8791 | `tools/links/ui/` | Started by Postroom |
| Video Finder | 8792 | `tools/video-finder/` (stdlib only, `start.sh`) | Finds a data18 scene on 21 other sites, scores matches. `sites.py`, `matcher.py`, `rules.json`, `data18.py` |
| Stream test | 8793 | `tools/stream-test/` (`start.sh` uses `/opt/homebrew/bin/python3`; the macOS Python cannot reach porntrex's CDN) | "Watch & get frames": plays a result from its site and takes frames with ffmpeg |
| Model dashboard | 8765 / 8777 | `CLIP Training/scripts/review_server.py` | Gitignored folder; markup duplicated ~L1200 and ~L1691: edit both |

Start/stop: `./start_all.sh`, `NO_OPEN=1 ./start_lighttable.sh`, `./stop_all.sh`, `./stop_lighttable.sh`. After editing a Python tool, restart it: `kill $(lsof -ti tcp:PORT)` (the Light table
restarts data18 / Video Finder / Stream test itself the next time they are needed). `static/index.html` files are re-read on every request.
**Everything now lives in one repo, `~/instagram-bot-2/tools/{data18,links,video-finder,stream-test}`** (they used to be separate folders `~/data18-scraper`, `~/Links-3-embedded`,
`~/video-finder`, `~/stream-test`; all paths were converted to be relative to the file). The two old GitHub repos should be archived by the owner.

## 3. What was done in this session (newest last)

1. **Merged the folders** into `tools/`; removed hard-coded `/Users/hugodyson/...` paths; untracked secrets/junk (`auth.json`, `session.json`, imgcache, .mp4, node_modules, logs, `.DS_Store`).
   **`auth.json` (Instagram cookies) and data18's old `session.json` are still in git history: the owner should rotate those logins.**
2. **Video Finder: 3 new sites** (playvids, pornwex, porneec) -> 21 sites. Card readers checked against saved pages.
3. **Streaming ("Watch & get frames") extended from 4 sites to 19 of 21.** Not streamable: porngrey, shyfap (see P2). Details in `tools/stream-test/NOTES.md`. Code:
   `server.py` `PAGE_SOURCES` + `parse_page_sources()` (tnaflix `<source>` list, porneec `contentUrl`, playvids/pornflip HLS), `kvs_real_url()` (pornwex `function/0/` addresses; port of yt-dlp's method,
   verified identical on the saved page), `follow_embed()` (pornzog -> vxxx.com player), `FFMPEG_HEADERS` (HLS frames need the page as Referer, the browser does not), frame-folder names letters+digits only,
   `page_duration()` reads `P0DT0H25M0S` / `T25M48S` / `data-duration`. The button list is `STREAM_SITES` in `tools/data18/static/index.html`; Video Finder's `sites.STREAMABLE` has the same 19.
   Chrome 154/155 plays HLS natively, so no hls.js is needed.
4. **Test and probe tools** (all in `tools/stream-test/`, all write a `*_results.txt/.json` next to themselves):
   - `probe_sites.py`: one frame per site via ffmpeg (frames only, not browser playback).
   - `play_test.py`: **default = drives the real Stream test pop-up in Chrome** for all sites (seek to 40%, play 3 s); `--direct` and `--media ADDRESS` are older modes. Needs the data18 venv (Playwright) and Google Chrome.
   - `probe_frames.py`: which sites hand out frames for free (numbered previews, storyboard sheets, WebVTT, HLS I-frames). **Never run yet.**
   - `capture_network.py URL`: opens Chrome, you click, it lists the hidden requests that returned picture addresses.
   - `inspect_json.py URL --header ... --cookie ...`: sorts a JSON's picture addresses into different pictures vs sizes.
   - `pornbox_probe.py ID`: checks a Pornbox scene as a frame source. **Pending run.**
5. **UI redesign prompt** written (no UI built): `docs/UI_DESIGN_PROMPT.md` (see P6).
6. Cloned ThePornDB's public `scrapers` repo to read it (not part of this repo).

## 4. Results so far (facts)

**`play_test.py` (real pop-up, Chrome 155, 2 videos per site)**: 28 of 38 tests played and seeked.
- Both videos play: porneec, freepornvideos, porntrex, xozilla, eporner, pornhub, porntop, youporn (slow start, about 15 s), xhamster, trendyporn, xxxbunker, youcrazyx, yrprno.
- tnaflix: 1 of 2 (the other "STALLED": played 1.6 of 3 s; probably a slow moment, recheck). fpo.xxx: 1 of 2 (the other failed: the link from a saved search contained spaces, `urllib` refused it).
- **playvids x2, pornflip x2 FAILED: a regression from the cloud session's own change.** `fetch_info` does `html.replace("&amp;", "&")`, then `parse_page_sources`/`_attr` runs `html.unescape` again, which turns `&sectime=` into `§ime`
  (`&sect` is a legacy HTML entity). The `§` breaks the address (direct load fails, then the proxy dies with `UnicodeEncodeError`). They played fine in the earlier `--direct` test (which read the raw page).
- pornwex x2 FAILED: page read and KVS address decoded, but playback failed ("Format error", proxy mode). Cause unknown (need the proxy's HTTP status or a live capture).
- pornzog x2 FAILED: `follow_embed` found nothing; nobody has looked at vxxx.com's real player page.
- The `ConnectionResetError` tracebacks printed during the run are harmless (Chrome closing idle keep-alive connections after each test). Optional tidy: override `handle_error` in Stream test's server.

**Earlier `probe_sites.py` (ffmpeg frame test)**: worked for eporner, fpo.xxx, freepornvideos, pornhub, porntop, porntrex, tnaflix, trendyporn, xhamster, xozilla, youporn, xxxbunker (1/2), playvids and pornflip (HLS, 2/2).

**Pornbox (best frame source found so far)**: `GET https://pornbox.com/contents/<id>` with header `X-Requested-With: XMLHttpRequest` and cookie `agree18=1` works logged out (also used by ThePornDB's `scenes/networkPornbox.py`).
For scene 127185 ("Casting and Creampie Skinny Supermodel Like Beauty Kyler Quinn - POV", 00:34:42, published 2022-10-19) the JSON has **`screenshots[]`: 248 different pictures, each with `small_thumbnail` and `xga_size`**
(plain CDN addresses on `cdn77-image.gtflixtv.com`, no resize parameters, path signature valid until 2033-01-21), i.e. one every 8.4 s, evenly spaced. It also has title, studio, `models`, `male_models`, release date, runtime, niches/tags,
price, `is_purchased`, `allow_guest_preview`, `video_preview`, `thumbnail.{list,small,large,mosaic}` (poster sizes), `player_poster`. `/contents/<id>/related` lists 52 related scenes; `/media/<n>/stream?label_id=` returns player/quality info.
**Unknown:** whether both sizes download without a referrer, pixel size and KB per picture, how to search Pornbox by title/performer, and coverage of the owner's creators.

## 5. Open work, in priority order

**P1. Pornbox as a frame source (the owner's current focus: "dense frames per video").**
1. Run `pornbox_probe.py 127185` (referrer needed? sizes? KB?). Decide: keep `small_thumbnail` if >= 224 px high, else resize `xga_size` to 224 px (about 15 KB each, about 4 MB per scene).
2. Find Pornbox's search endpoint: `capture_network.py "https://pornbox.com/store/search?q=kyler+quinn"` (or use the site's search box while it records). ThePornDB's list endpoint is `/niche/<id>/?skip=N&sort=recent&_=<ms>` and `/studio/<id>/`.
3. Build a **"frame source" type in Video Finder** (second kind of site entry): search by title+performers, open `/contents/<id>`, score with the existing matcher (the JSON gives performers, studio, date, length, which data18 pages lacked), show "found 248 frames", button to pull them -> model -> labels. Then make it a stage of the chain (P4).
4. Possibly other databases of the same kind; the owner may supply links. ThePornDB's own API (not the scrapers repo) may supply performers/studio/duration for matching (needs an account/key, unverified).

**P2. Fix the Stream test failures (ask the owner to confirm; diagnosed above).**
- playvids/pornflip: stop double-unescaping (`_attr` should not unescape when the page text is already unescaped; or keep `&amp;` handling in one place). Add a test: the printed source address must contain `sectime=`, no `§`.
- fpo.xxx spaces: percent-quote the page link in `fetch_info` (`urllib.parse.quote` with safe characters) before requesting.
- pornwex: capture what the proxy gets (status/body); possibly the decoded get_file link needs a Referer or cookie; compare with the browser via `capture_network.py` on a pornwex watch page.
- pornzog: save the real pornzog page and the vxxx.com embed page and read how the player gets its video.
- shyfap/porngrey (parked): the plain request gets an 11-byte `text/html` answer from Cloudflare, even with cookies and Referer; the owner's Chrome gets the file. If you try again, use Chrome's "Copy as cURL" of the working request (cookie values removed) to see which header differs; if it is a Cloudflare clearance cookie, leave them.
- Optional: quiet the `ConnectionResetError` noise; re-run `play_test.py` afterwards and update `NOTES.md` and the README.

**P3. Video Finder judge (the owner said "we'll come back to that").** In their screenshot for "Finally Getting Our Fuck On" the finder found the right videos but scored them "no match" because:
(a) `data18.fetch_scene()` re-reads the scene page live and its fixed patterns returned empty studio, performers and duration for that scene (verified: `data18.fetch_scene('1345966')` -> studio '', performers [], duration 0), although the scraper's saved results (`tools/data18/data/results/*.json`, `data18.from_link()`) have studio and performers;
(b) without performers/length the maximum score is about 60 (title 35 + studio 10 + length bonus 10 + 5) while "confident" needs 70, so a perfect title match can never be confident;
(c) `{Name} - Title` / `Studio - Title - XXX` titles lose points because the extra words count as "extras" (coverage 3/5 -> 21 of 35 points).
Plan: start from the scraper's saved studio/performers/date; segment-aware title matching (split on ` - `, `|`, brackets, `#tags`, strip filler); cross-site length consensus (the same title+length on several sites is strong evidence); learn performer names from the first confident hit and re-query; a "paste a link" box (Google can't be scripted: the page already links to Google Videos) that reads any video page (title, length, streamable?) and scores it; weight distinctive words. The README measured that extra query *formats* found no extra matches on 7 videos, so the problem is the judge, not search recall.

**P4. Chains: the owner's most crucial UI requirement.** One click from a page starts a chain, shown as ONE job with stages, pausable/retryable: *scrape creator -> find each video (Video Finder, auto-select confident matches) -> pull segments (stream or download) / frames (P1) -> run the B/32 model -> update Positions (`position_index.json`: per-video creator + seconds per position, per-section creator/position/sub/start_s/end_s/confidence/source) -> cut segment clips into the creator's collection*.
Today these are separate servers/jobs (data18 batch, autofind queue, `remote_frames.py` + model worker, `label_video.py`, `position_index.py`). Needs an orchestrator with one status model. **Unanswered question for the owner: fully automatic, or pause for approval at chosen points (e.g. after a video is matched)?**

**P5. Run `probe_frames.py`** (which of the 21 sites hand out frames for free; known: freepornvideos 100 numbered previews 390x220, tnaflix `data-mosaic` storyboard, fpo.xxx only 1-2, pornwex page shows only `1.jpg`, playvids rotating preview folder with odd numbering) and add the best sources to the frame step (spacing from `duration / count`).

**P6. UI redesign.** The owner will ask 4 different AIs for designs. `docs/UI_DESIGN_PROMPT.md` = base prompt (vision first, 3 tiers: hard rules / strong defaults / open; Stage 1 text-only skeleton, Stage 2 mockup; click-budget journeys; fake data) + 4 alternative "HOME" paragraphs (8 were discussed: 1 chains, 2 breakdown by creator, 3 review, 4 finding, 5 one creator, 6 watching, 7 sourcing, 8 teaching the model; recommended first round 1, 8, 2, 6).
The owner wants real pages, not one screen: at least **Model training**, **Scrape & links**, **Positions (breakdown by creator, e.g. "creator 1: 200 videos, 400 Standing segments...")**, plus cross-page links everywhere and chains. Last round's two designs (`ui-html/a-departures`, `b-lighttable`) had different looks but the same skeleton (search box + grid + right panel). Nothing to implement until they pick a design.

**P7. Housekeeping.** Rotate Instagram/data18 logins; archive the old GitHub repos; remaining items from the 12 Oct handoff (the `/distil` memory draft was never answered; disk cleanup of B/16 + L/14 weights, `CLIP Training/embeddings/experiments/`, stale L/14 entries in `tools/data18/data/predictions.json` was offered, never confirmed: **delete nothing without a yes**; never touch the folder `pipeline/frames_5s/Vixen ... 8m00-12m05`).

## 6. Constraints that still hold (from the earlier handoff and this session)

- Position model = **B/32 only** (`position_clf.pkl`, `subtype_clf.pkl`); do not run or push L/14 unless asked; "Unsure" stays off. The owner retrains from the dashboard, so model files change mid-session.
- Leave the original Postroom (`server.py`, `ui/`) alone; changes go in `ui-lighttable`, `lighttable_server.py` or `tools/`. After ANY edit to `lighttable_server.py` check `/`, `/api/config`, `/api/accounts`, `/api/analysis/videos`, `/api/links/status`, `/api/positions`, `/lt/data18`, `/d18/`, `/d18/api/status`, and that the built JS is served as `text/javascript` (a past edit deleted `HOP = {...}` and broke every pass-through request).
- Say how any speed/accuracy number was measured; verify which job/model is really running from code and logs before reporting status.
- Stream test and Video Finder are standard-library Python by design (Stream test calls ffmpeg and yt-dlp as programs).

## 7. Where things are

- `docs/`: `CAPABILITIES.md` (inventory of today's app, organised by today's pages), `DESIGN_BRIEF*.md` (old briefs), `UI_DESIGN_PROMPT.md` (current), `HANDOFF_2026-10-12.md` (archived).
- `tools/stream-test/NOTES.md`: findings per site (qualities, referrer rules, KVS notes, Pornbox, HLS), kept up to date; add to it when you learn something.
- `tools/video-finder/README.md`: search strategy and scoring. `tools/data18/README.md`, `tools/data18/HANDOFF_run_model_on_photos.md`: scraper and model integration.
- Run output stays local and out of git (`play_test_shots/`, `frames_probe_samples/`, `pornbox_samples/`, `tools/video-finder/data/jobs/`, `tools/data18/data/imgcache/`, logs).

## 8. Suggested first message to the owner

"I've read HANDOFF.md. I'm running `pornbox_probe.py` now. Two quick questions: should I fix the Stream test failures (playvids/pornflip are my regression), and for chains do you want fully automatic or pauses for your OK?"
