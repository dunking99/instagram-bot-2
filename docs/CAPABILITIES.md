# Capability inventory: Postroom / Light table / Links / Data18 / Model dashboard

Compiled 2026-10-13 from the code in `~/instagram-bot-2`, `~/Links-3-embedded` and `~/data18-scraper`
(plus `~/video-finder`, which `data18-scraper` calls and which is outside the three folders).
Sources: every route in the four servers, every React/vanilla-JS view, the CLI scripts, HANDOFF.md, PRODUCT.md.

Legend: **[UI]** reachable in a screen today · **[API]** server endpoint only · **[CLI]** terminal only · **[auto]** runs by itself.

---

## 0. The system at a glance

| App | What it is | Port | Code | UI |
|---|---|---|---|---|
| **Postroom** | FastAPI server for the Instagram/library desk (search, library, collections, pilot, positions, analysis, jobs) | 8503 | `server.py`, `random_post.py` (CLI engine, 146 KB) | React `ui/` (original, "untouched" by rule) |
| **Light table** | Second face for the same Postroom: serves `ui-lighttable/dist`, proxies `/api/*` to 8503, adds `/d18/` proxy and `/lt/*` endpoints | 8504 (+ tailnet URL) | `lighttable_server.py`, `ui-lighttable/` | React, 8 pages. **This is the UI to redo** |
| **Links** | Scrape creators' video-page links from sites, sort, build lists, download. Embedded in an iframe | 8791 (8790 standalone) | `Links-3-embedded/ui/server.py` + vanilla JS in `ui/static/` | own UI, own CSS |
| **Data18 scraper** | Scrape data18 performers/videos/stills; run the position model on stills; find the video on other sites; download clips | 8790 | `data18-scraper/server.py`, `static/index.html` (113 KB single file) | own UI, shown in an iframe at `/d18/` |
| **Model dashboard** | Frame-by-frame review/correct/retrain page for the position model | 8765 (8777 in the last session) | `CLIP Training/scripts/review_server.py` (137 KB, page markup duplicated at ~L1200 and ~L1691) | own UI, opened in a new tab |
| **Video Finder** *(outside the 3 folders)* | Finds a data18 scene on other sites, ranks matches | 8792 | `~/video-finder` | own UI |

Start/stop: `start_all.sh` (Postroom + model dashboard), `start_lighttable.sh` (Postroom + Light table), `stop_all.sh`, `stop_lighttable.sh`.
Links, data18 and Video Finder are started on demand by the layer above them.

Light table nav today: **Search · Library · Collections · Pilot · Positions · Analysis · Data18 Scraper · Links**.
Two of those eight (Data18, Links) are just iframes around separate apps with their own look.

---

## 1. Global shell (always present) [UI]

- Top bar: brand → home, page tabs, **⌘K command palette** (go to page, open image/video folders, favourites, photos pilot, positions, analysis, data18, links, prepare an account, open refine, switch CLIP/SigLIP, session/login/storage, show jobs, draw random).
- `/` jumps to Search and focuses the query box. `⌘K` palette is keyboard-navigable.
- **Search-model switch: SigLIP / CLIP.** Separate indexes per account; stored per browser; only changes Search/Library (not position features).
- **Status pill:** free disk space (warns under 5 GB), login state (`@user`), opens the Session sheet.
- **Activity panel (jobs):** list of background jobs with progress %, progress text, pid, live log, **Stop**, **Dismiss**, "Clear finished". Jobs survive page refresh (persisted logs).
- **Lightbox tray (right side):** the favourites, always at hand. Filter All/Photos/Videos, click to preview, ✕ to remove, **Slides** (slideshow of favourites), **Open folder**, **Manage** (→ Collections › Favourites). Auto-shown on Search, hidden elsewhere/narrow windows; manual toggle.
- **Toasts**, error boundary per page ("rest of app is fine"), **stale-server banner** when the UI is newer than the API version.
- **Session sheet:** `auth.json` status, "Check which account I'm using" (runs `whoami.py`), "Log in / switch account" (opens a real browser window, 3 minutes, 2FA ok), index explanation, **storage** (free/used/total, project size, 8 biggest folders, 5 biggest thumbnail folders, Recalculate), open `picks/ favourites/ library/ pilot/ cache/` in Finder.
- **Prepare sheet:** build the whole index for one or more accounts (reads profile, thumbnails, photo + pose indexes, carousel detection), optional "also look inside N carousels".
- **Import sheets:** *Folder of images* (name + path → import job), *Watch a video folder* (name + path), *Create several at once* (up to 100 name/folder rows, videos added instantly, photos imported in background, per-row report).
- **Full-screen viewer / slideshow** (used by every grid): ← →, space pause, S shuffle, F full screen (fades controls), H favourite, Esc; seconds-per-image 2/3/5/8/15; plays video clips to the end then advances; "endless" mode fetches more clips two before the end; score bar; caption (account, slide no., date); favourite, download, open on Instagram, copy link, show in Finder; for position clips shows position, title, creator, time range, "verified by you" vs "model's guess + confidence".

---

## 2. Search [UI] (`/api/search`, `random_post.py`)

Two sub-modes via "Search in": **Instagram posts** and **Videos by position**.

### 2a. Instagram posts
- **Accounts:** multi-select picker with filter, cover thumbnails, "Select all ready", Clear, type a new `@username` + Enter to add; warns "not indexed" per model; **Prepare indexes** shortcut.
- **Three ranking signals, each toggleable:** *Scene text* (natural language, ⌘↵ runs), *Reference photo* (drop/choose, or pick from sample thumbnails of the chosen accounts; text↔image weight slider when both), *Pose* (drop/choose pose reference; "count left-right flipped pose as match"; scene-strictness slider "best N% for scene then ordered by pose").
- Suggested prompts (5 starter ideas) when nothing is entered. Empty query = fully random draw ("Draw random" button / ⌘K command).
- **Must-match tags** (groups from `labels.json`: setting, outfit, shot, pose, arms; pose/arms need the pose index), tag-confidence slider 0.30–0.95, warning when two tags from one group.
- **Best / Worst** polarity (worst = testing the ranker).
- **Posts count** (1–1000) or **"Everything matching"** (all posts carrying the tags, with a cap up to 2000; warns about time when saving full size).
- **Account mixing:** Each / Pool / Even (hint text computes the split).
- **Result mode:** Instant thumbs · Save full size (visits Instagram, ~5 s/post) · Links only.
- **Refine drawer:** date range (Any / last 90 days / this year / last year / year before / custom from–until), allow reels & videos, mix watched-folder videos into searches, choose video/photo mix % (with explanation of repeated segments), video clip length, carousels (first photo only vs save every slide; carousel strictness slider/Auto; "look inside N most promising carousels"), top-N random pool (1–500), **cache mode** (Saved / Check for new posts / Rebuild slow), save folder.
- Filter chips summarise active refine settings; each clears itself.
- Live log of `random_post.py` while running; Cancel; skeleton loading grid; session-missing banner.
- **Results:** contact sheet with score pills, select-all/none, per-card: open viewer, open on Instagram / Finder, download, star. Dock: **Slideshow**, **Save thumbnails** (instant copy), **Save full size** (fetch job), **Favourite** (copy to `favourites/`), Open folder. Link-list view for "Links" mode (Open, Copy link, Favourite). Empty-result help ("clear tags and dates", "prepare account").

### 2b. Videos by position ("PositionMix")
- Pick any number of positions (main positions + their sub-types as chips with video counts; "All main positions"); each becomes a rule line you can tie to creators, duplicate ("+ Another"), remove.
- **Creator filter:** Only these / Everyone except; per-line creator override; **max per creator** (1/2/3/5).
- **Split:** Random mix (N total) or Exact number each (± per rule, 1–60).
- Clip length (15 s … 5 min, whole section), model confidence (any/0.4/0.5/0.6), verified-only.
- Same video is never used twice; scarce positions filled first; short sections dropped and replaced; shortfall notes.
- Results: playable clips (position, verified/model + confidence, title, creator, clip & section times), **Another video** (swap one), **Show file** (Finder); **Slideshow** that keeps drawing new combinations.
- All settings persisted per browser.

---

## 3. Library [UI] (`/api/breakdown`, `/api/describe`, jobs)

- Account picker (incl. "All accounts" merge); tag-confidence slider.
- Stats: photo posts, reels (not counted), carousels (or "not detected yet"), extra slide photos indexed, composition bar; "prepared <date>", pose ready/missing.
- **Tag browser:** facet columns (setting / outfit+shot / pose+arms / others), count + % bars, "No confident tag" row; click tag → image grid sorted by confidence ("show more" pages of 24); second tag from another group asks *alone vs both*; same-group replaces. Items enriched with source (Instagram/folder/video).
- **Detect carousels** (about 2 min), **Build pose index**, **Prepare**.
- **Index every image** panel (carousel posts): progress "N of M opened", extra photos indexed, "open at most N this time", 1–3 browser windows (with rate-limit warning), "keep going until done", Start/continue.
- **Open library / Preview folders:** modal tree of `library/<account>/{setting,outfit,shot,pose}/…` with counts; **Build / Refresh library folders** job; open in Finder.
- "All saved accounts" table (posts, videos, status).

---

## 4. Collections [UI] (`/api/imports`, `/api/watch*`, `/api/favs*`)

### 4a. Image folders
- Auto-import toggle ("check for new files when Postroom opens", files imported once stable ~30 s).
- Import image folder; **Import all new (N)**; per-collection: folders, indexed count, pending count, **Import new**, Finder.
### 4b. Video folders
- **Watch a video folder**, **Create several at once**, **Check for new videos now** (also auto every 30 s while server runs).
- **Find new folders:** scan a library root, list sub-folders with unwatched videos / un-imported photos, rename, tick/untick, joins existing account if name matches, name-clash warning, **Add N folders** + report; **Add new folders automatically** toggle; saved root.
- **Make videos searchable** (frame every 2/5/10/30/60 s; per-folder or tick several → one job; estimates videos/hours/frames/minutes).
- Per folder: video count, attached-to-account flag, searchable-frame count, **Random clip** (length chooser) with inline player, **Stop** watching, newest-60 video grid with poster, **Play**, **Finder**.
### 4c. Favourites
- Filter by account chips, contact sheet (no marks), Open favourites folder. Starring copies the picture to `favourites/<account>/` and records the link (`favourites.json`).

---

## 5. Pilot (Photos screenshots) [UI] (`photos_import.py`, `/api/pilot*`)
- Run on 400 random screenshots from the macOS Photos library (read-only), a job.
- Three piles Keep / Review / Junk with drag-and-drop between piles, per-card keep/review/junk/Auto buttons, manual overrides persist.
- Keep-threshold and junk-threshold sliders with score histogram; body-found counts toward keep; toggle crop vs whole screenshot; **Undo correction** (50 deep); show-more per pile; best prompt text per card.

---

## 6. Positions [UI] (`/api/positions*`, `query_positions.py`)
- Position dropdown (parents then their sub-types, video counts), videos count (1–60), clip length, model confidence, verified-only, optional "only this video / creator" text filter.
- **Show clips / Shuffle again**, **▶ Slideshow** (endless). Per clip: player, position, verified/model(+conf), title, creator, clip + section time, **Another video**, **Show file**.
- Tab **Which videos have it**: two lists (has / doesn't) with seconds in that position and verified flag.
- Header: analysed videos, verified videos, missing files skipped, total minutes for the chosen position.

---

## 7. Analysis [UI] (`/api/analysis/*`, `auto_analyse.py`)
- Every library video + every draft with status: **Verified · Saved by you · Model up to date · Model older version · Waiting · Failed · Running · Queued #n**.
- Summary bar + clickable cards; filter chips (All, Needs analysis, Verified, Up to date, Older model, Waiting, Failed, Running/queued); search; sort (needs-attention, title, creator, lowest confidence, longest).
- Per row: position **timeline strip** coloured by position (with legend), mean-confidence meter, duration, section count, drafted-ago, error text, "draft older" flag for verified videos.
- Actions: **Analyse everything that needs it**, select all/none, **Re-run model on N selected** (confirmation when verified videos included — their saved version is never touched), per-row Analyse/Retry/Re-run, **Frames** (open that video in the model dashboard), **Model dashboard** button, **Stop after this one** (clears queue).
- Live run banner: current video, queued, done this run, failed.

---

## 8. Links (embedded app, port 8791) [UI]

Tabs: **Creators · Discover · Sites · Library · Lists · Download · Settings**, plus a global Activity log with Stop.

### 8a. Creators
- **Add creators** from pasted text: any mix of links (quotes/bullets/commas/zero-width characters cleaned) and plain names; choose Site; "Pages" (number or `all`); "Scrape right after adding". Names are looked up with the site's "addresses to try".
- **Cross-site matching:** same person on several sites auto-linked (name similarity, min length, ask-threshold); suggestions to confirm/reject; manual **Merge into…**, **Unlink**, per-site **Remove**.
- **Import existing `*_links.txt` files** under a chosen site (replace earlier imports, keep underscores in folder names).
- Creator cards: avatar (auto-fetched; two-picture "Keep current / Use new" chooser), display name, download folder, link count, last scraped, per-site rows (count, "all pages", Re-scrape, Unlink, Remove), **Scrape / Re-scrape**, **Rename** (display name, folder name, optionally move existing folder), **Remove** (and delete links), merge dropdown.
- Toolbar: sort (A–Z, Z–A, most/least links), **Re-categorise all** (reports what moved), **Create folders**, **Find addresses for imported** (look up by name then scrape), **Scrape unscraped**, **Re-scrape all**.
- Expandable per-creator **link panel**: category tiles with counts, length-bucket chips, search, sort (scrape order / A–Z / Z–A / most / least viewed / shortest / longest), min-views filter (`100k`, `1.5m`), copy shown, per-category copy, "show all N".
### 8b. Discover (swipe cards)
- Collect the Pornhub performer directory (pages, slow & polite, stops on rate-limit), 1,230 performers saved with pictures.
- Swipe deck: **Keep** (→ adds creator, scrapes all their links), **Skip** (←), **Undo** (Z), **Open** (O), Re-shuffle (R), Filters (F: min/max videos, views, rank, verified-only), settings (pages to scrape per kept performer), "reset skipped", recently-kept list with status (added / queued / scraping / done + link count).
### 8c. Sites (scraper profiles)
- Add/edit/delete site profiles: name, base URL, next-page template, video-link & duration regexes, key-attribute + link template, scope / ignore / views / avatar CSS selectors, multi-page "sections", slug-strip endings, creator-address patterns (add by name), "not found" text, categories as `Name: keywords`, dominant category, forced-"Other" keywords, per-site download method (VDH or yt-dlp), request delay, keep query string.
- **Try it:** Test a URL; Find a creator by name. Currently configured: PimpBunny, Pornhub, Pornhub Charts, plus "Your script" (`necessary/scrape_fruitsvids.py`).
### 8d. Library
- Totals, per-category/length-bucket counts, downloaded count, **Export .txt lists** (ordered/random, per category, per length).
### 8e. Lists
- Build a list: filter creators/categories/lengths/min-views/skip-downloaded; order (creator, title, category, random, scrape order, views); split into files (none/category/creator); include durations/titles; **Shuffle again**; **Save to folder**; **Use this list for downloading**.
### 8f. Download
- Modes: **Pick for me**, **Use a list**, **Enter links myself** (into any library folder).
- Filters: creators include/exclude, categories, lengths (multiple), **mix sites in a ratio**, how many, skip downloaded, min views, **max per creator**, share between creators (equal / at least N each). **Preview** (links, per-site tally, seed) → **Download these**.
- Per-item live progress table (state, %, MB, elapsed, file, destination folder), Stop. Stops after N consecutive failures.
- Methods: **yt-dlp** (parallel, no browser, max height cap) or **Video DownloadHelper** (clicks Chrome by on-screen template match; max parallel 3, waits, timeouts) and a page-grab fallback (`pagegrab.py`) for sites yt-dlp can't read. Files filed into creator folders; every download logged to `download_log.jsonl`.
### 8g. Settings
- Scraper script path, scrape pause, length-bucket edges, download dir, library dir, download method, max height, VDH click positions + **capture mouse position / capture button pictures** helpers, image-match threshold, waits, parallelism, timeouts, pause between links, target successes, attempts, startup delay, min/max video minutes for scrapes, default site, "all pages by default", name-match toggles/thresholds.
- Server self-restarts when its code changes (Mac), stale banner otherwise.

### 8h. Frames from video links (panel on the Light table's Links page) [UI] (`/lt/frames/*`, `remote_frames.py`)
- Paste one or many page links (one per line), a frame every 2/5/10/15/30 s, optional from–to time. Reads only the needed parts of each video (HTTP range requests via local caching proxy; direct file, embedded player, HLS, or yt-dlp lookup); video is **never saved**.
- Up to 3 jobs at once (rest queue), one resident model worker; per-video 4-stage progress (find → index → frames → model), % / frames / MB / ETA, results line, **Open in model dashboard**, **Show in Analysis**, Clear finished. Frames land in `pipeline/frames_5s/<name>/` and a B/32 draft is created.

---

## 9. Data18 Scraper (port 8790, iframe `/d18/`) [UI]

Tabs: **Performers · Studios · Tags · Pornstars · Scraped creators · By position · Favourites**.

- **Performers:** type a name → Scrape (listing, then details per video: categories, ethnicity, tags, studio, co-stars, date, gallery list; polite rate limit; progress). Re-scrape, Copy links. Filters: title search, studio, co-star, year, sort (newest, oldest, A–Z, most/fewest photos); **category chips click-once = require, twice = exclude, match all/any**, ethnicity chips; Clear filters.
- Per video row: expand **Photos** (galleries: Primary, Photoset(s), Video Stills, Trailer) with grid + lightbox (← →, ♡ favourite, **Get video**), **Run the model** on this video or on hand-picked images (tick-boxes), per-image predicted position + confidence + sub-type badges, per-video position summary.
- **Batch panel:** run the model on all / N random videos of this creator, only new, include photosets, progress, Cancel, **See results by position**.
- **Studios:** scrape/refresh studio list; search; top-level vs sub-channel; parent filter; sort; group by channel; copy links.
- **Tags:** scrape tag list; counts of how many scraped videos have each; "only tags with videos"; expand a tag to list its videos.
- **Pornstars:** directory scrape (name, picture, scenes, movies, rank), search, sort, only-with-photos, paged load.
- **Scraped creators:** every performer already scraped, searchable, open to see videos/photos/results.
- **By position:** creator, image type (stills/photosets/both), position-confidence and sub-type-confidence thresholds; overview table → position → sub-type → image grid (sort, paging, hash routes `#positions/Doggystyle/Standing`).
- **Favourites:** ♥ any frame; search by title/creator/position.
- **Get video (Video Finder):** search the other sites for this scene (rules-based ranking, "confident/possible"), see per-site best result with thumbnail, choose the right one (remembered), **download the whole video** through Links, or **download only a clip** around a chosen still (still *k* ≈ minute *k−1*, window 10–900 s, default 180), **multi-select frames → Download clips** (queue, 2 at a time), clip queue indicator. After download the model pipeline picks the video up automatically.
- Session: `setup_session.py` once (age-gate cookie); "session expired" notice.
- Extra CLI: `download_stills.py <scene>`, `test_video.py <scene>`.

---

## 10. Model dashboard (port 8765/8777) [UI, separate tab]

Pages: **Review (video list + frames/sections)**, **Category overview**, **Browse**, **Models**, **Compare versions**, **Classic view**.
- **Review a video:** Frames tab (select by click / shift-range / cmd-add; set label; exclude/restore; drag START/END tags to move boundaries; hover to enlarge; full viewer with ←→, 1–9 label, P plays 10 s clip), Sections tab (per-section label dropdown, merge ticked rows, move to previous/next section, section/unsure navigation J/K/U, "Next unsure", "Next to review"), Categories panel (add label, add sub-type "Parent - Sub", promote holding label → trained, label stats, **Retrain model now**), Undo, **Simplify**, **Test model on this video** (redraft; optional "refined sections (test)"), **Restore previous version**, **Mark completed ✓**, **Save corrections**, **Save & retrain**, **Remove from training**. Frame-size slider. Unsure label is OFF by request.
- **Browse:** every labelled frame by category; move frames between labels, mark correct (selected / section / video / all), show only where model disagrees, undo, refresh model view, size slider.
- **Models:** parent and sub-position model quality on held-out videos (from `suggestions.json`), what each confuses with what, training-data health vs saved corrections.
- **Compare:** diff two versions of a video's labels, frame by frame, 3/6/any-frame length filter, swap.

---

## 11. Background and automatic behaviour [auto]

- **Auto-analysis loop** (every 45 s): new library videos (stable, >1 MB, not partial) → frames → model → draft → position index. 3 retries then parked; pause file `CLIP Training/auto_pipeline_off`. Endpoints `GET /api/analysis/status`, `POST /api/analysis/enabled`, `POST /api/analysis/run` exist **but no screen uses them: pausing/resuming auto-analysis has no UI.**
- **Watch loop** (every 30 s): registers new videos in watched folders; optionally adds new sub-folders and imports their photos.
- **Resident model worker** (`model_worker.py`): TCP on localhost, 15-min idle exit, reloads when `position_clf.pkl` changes.
- **Position index** rebuilt on every dashboard save and every auto-analysis (verified wins over model; excluded frames split sections; Prone→Doggystyle, Foreplay→Start for search).
- Heavy-job lock: only one heavy Postroom job at a time (409 otherwise); Links also single-job; data18 one scrape at a time.
- Tailscale serve exposes the Light table on the tailnet (no phone layout yet).

---

## 12. Capabilities with no UI [CLI / API only]

- `random_post.py`: `--convert-all`, `--shrink-saved`, `--accounts-file` + `--account-gap` (batch many accounts with pauses), `--cache-hours`, `--max-scrolls`, `--limit`, `--fetch <post URLs>`, `--import-videos`, `--index-videos-many`, `--list-tags --json`.
- `library_cleanup.py` (merge duplicate creator folders, dry-run / `--apply` / `--undo <run>`), logs in `library_cleanup_logs/`.
- `CLIP Training/scripts`: `new_video.py`, `grab.py` (download link → frames → draft), `extract_frames.py`, `embed.py`, `train.py`, `subtypes.py`, `suggest.py`, `benchmark.py`, `evaluate.py`, `learning_curve.py`, `spacing_test.py`, `classify_images.py` (any images, `--model b32|l14`), `label_l14.py` / `train_l14.py` (experimental L/14, switched off), `position_index.py --summary`, `query_positions.py --which/--list`.
- Postroom: `POST /api/links/stop`, `GET /api/favs/ids`, `POST /api/jobs` kinds all reachable from UI except the pause endpoints above.
- Old Streamlit `app.py`/`app_v2.py` (+`backup_classic/`) still exist: Discover / Breakdown / Library (accounts, videos, images, pilot) / Favourites tabs; parity target per memory notes.
- Loose shell scripts from the first Links version (`good too/*.sh`, `necessary/*.sh`, `vdh_*.py`, `scrape_pimpbunny.py`) are superseded by the Links UI.

---

## 13. Cross-app data flow (what a redesign must keep wired)

1. Links downloads video → `library/<creator>/` → Postroom watcher registers it → auto-analysis drafts positions → Positions/Analysis/Search-by-position use it.
2. Data18 "Get video" → Video Finder → Links `POST /api/download` (manual mode) **or** `remote_clip.py` for a clip → library → same pipeline.
3. Data18 stills → `classify_images.py --model b32` → `predictions.json` → By-position tab.
4. Frames-from-link → `pipeline/frames_5s` → `label_video.py` via model worker → draft in model dashboard.
5. Links' library dir setting is shared by Data18 (reads Links `settings.json`).
6. Postroom starts/stops Links (`/api/links/*`); Light table starts Data18 (`/lt/data18`) and finds the model dashboard (`/lt/review`).

---

## 14. Findings that matter for the redesign

- **PRODUCT.md is out of date.** Its "must stay reachable" list omits: Search by position (PositionMix), Frames-from-links, Data18 Scraper, Find-new-folders / auto-add folders, Make-videos-searchable bulk, the Lightbox tray, the model dashboard, and Video Finder. It still says Links is "stays embedded as-is".
- **The original Postroom `ui/` lacks** Data18, PositionMix, Lightbox, and the Frames panel; the Light table is the current superset.
- **Three apps with their own UIs** (Links, Data18, model dashboard) look and behave differently from the Light table. Data18's index.html is 113 KB of vanilla JS; the dashboard's markup is duplicated twice in `review_server.py`.
- **Missing UI:** pause/resume auto-analysis; no phone layout (Model dashboard/Frames buttons point to localhost); the "Unsure" option is hidden by request.
- **Port inconsistencies:** Links defaults to 8790 (same as Data18) but runs on 8791 when embedded; review dashboard is 8765 in scripts/docs and 8777 in the last session.
- **Safety rules the UI must preserve:** verified videos are never overwritten by re-runs; Light table never edits Postroom's `server.py`/`ui/`; Python 3.9 on the server; model = B/32; be polite to sites (8 images/s, 6 workers/video, 3 videos at once).
- **Dangerous actions currently guarded by `confirm()`/`alert()` in Links:** remove creator, merge, unlink, remove site; Analysis re-run of verified videos; Stop job. Keep a confirmation pattern.

## 15. What I did not read line-by-line

`random_post.py` internals (only its CLI surface and its docstring-level behaviour), `app_v2.py`/`app.py` beyond their tab/button structure, `review_server.py` backend handlers (page labels and docstrings only), Links' `discover.js` and Sites editor JS (HTML + server side read), `video-finder` internals (README + routes). If any of those matter for the redesign they should get a second pass.
