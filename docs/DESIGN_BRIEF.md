# Design brief: "Postroom", a private media desk (static HTML mockup)

## What I want from you
A **static HTML/CSS (light JS for tabs, drawers, modals, hover states only) design** of the whole app.
No backend, no real data, nothing needs to work. Use realistic **fake data**. I want to see layout, hierarchy,
navigation and how dense screens feel. Single `index.html` with every page reachable by a nav (hash routes or
JS tabs), plus the key overlays (listed at the end). Show both a populated state and, where noted, a busy/running state.
You have creative freedom on look and feel, and on how pages are grouped, merged or reordered, **as long as every function below stays reachable.**

## Who and how
One person, alone, on a Mac, in long daily desk sessions with a large screen (also viewed occasionally on a phone via a private network link).
Fluent expert user: speed and density beat onboarding. Content is personal, so nothing should look public-facing or like a marketing site.

## What the app is
A local desk for a personal library of saved creator media (Instagram posts, local image folders, and videos).
An image model (SigLIP/CLIP) indexes everything so I can **find frames by describing them, by tag, by reference photo or by body pose**.
A second model labels every video by **sex position** (sections along a timeline, with confidence), so I can pull clips by position.
Around that sit tools to **collect links, download videos, scrape a reference database, and review/correct the model**.
Success = find the right frame or clip in seconds, and always know what background jobs are doing.

## Principles
1. The picture is the interface: thumbnails, frames and clips get the room; controls stay out of the way until needed.
2. Every background job is visible and never blocks work.
3. Frequent actions are one click away; rare, powerful ones are one step behind, never removed.
4. Always show what the model decided and how sure it is. **My verification outranks the model** (verified vs "model guess + confidence" must be visually distinct everywhere).
5. One product: same controls, states and language on every page (the current Links / Data18 / Model-dashboard areas are visually separate apps; unify them).

## Global chrome (on every page)
- Brand + page navigation (suggest grouping; see page list). **Command palette (⌘K)** to jump anywhere or run commands; `/` focuses search.
- **Search-model switch** SigLIP | CLIP.
- **Status pill:** free disk space (warning state), Instagram login state/account → opens Session sheet.
- **Activity (jobs) panel:** list of background jobs with progress %, status, live log, Stop, Dismiss, "clear finished"; badge shows how many are running.
- **Lightbox tray:** my favourites, a persistent side tray (collapsible): filter All/Photos/Videos, thumbnails with remove, Slides, Open folder, Manage.
- Toasts; a "server out of date" banner; per-page error state.

## Pages and what each must contain

### 1. Search (home)
Two modes via a switch: **Instagram posts** | **Videos by position**.
**Posts mode**
- Account chooser (multi-select with covers, filter, "select all ready", add new @username, "not indexed" markers) + "Prepare indexes".
- Query composer: free-text scene description; three toggleable signals: **Scene text / Reference photo / Pose** (reference and pose have image drop zones, sample pickers, a text↔image weight slider, "count flipped pose as match", scene-strictness slider). Starter idea chips.
- **Must-match tags** in groups (setting, outfit, shot, pose, arms) + tag-confidence slider.
- Controls: Best/Worst, number of posts or "everything matching (cap)", account mixing Each/Pool/Even, result mode (Instant thumbs / Save full size / Links), **Refine** drawer, Find / Draw random / Cancel.
- Refine drawer: date range presets + pickers, allow reels/videos, mix watched videos in, video/photo mix %, clip length, carousel handling (first photo vs every slide, strictness, look inside N carousels), top-N pool, cache mode (Saved / Check for new / Rebuild), save folder.
- Active-filter chips; live run log; loading skeleton.
- Results: contact-sheet grid with score pills, selection ticks, per-card star / download / open source; selection dock (Slideshow, Save thumbnails, Save full size, Favourite, Open folder); link-list variant; empty state with suggestions.
**Videos-by-position mode**
- Position chips (main positions with their sub-types, each with a video count), "all main positions", per-position rule rows (tie to specific creators, "+ another", remove, ± count in exact mode).
- Creator filter (only these / everyone except), max-per-creator, split mode (random mix N total | exact number each), clip length, confidence, verified-only.
- Results: grid of playable clips, each showing position, **verified vs model guess (+confidence)**, title, creator, clip time range; "Another video", "Show file"; Slideshow.

### 2. Library
Account selector (incl. "All"), tag-confidence slider. Stats (photo posts, reels, carousels, extra slides) + composition bar. **Tag browser**: facet columns (setting / outfit+shot / pose+arms) with count and % bars; clicking a tag shows its images by confidence, with "show more"; second tag asks "alone or both". Callouts/actions: Detect carousels, Build pose index, Prepare, **Index every image** panel (X of Y carousels opened, limit, 1–3 browser windows, keep-going-until-done, progress), Build/Refresh categorised library folders (folder-tree preview), table of all saved accounts.

### 3. Collections
Tabs: **Image folders · Video folders · Favourites**.
- Image folders: auto-import toggle, Import folder, Import all new (N), cards with indexed/pending counts.
- Video folders: Watch a folder, Create several at once, Check for new videos; **Find new folders** scanner (tick list, rename, add N, auto-add toggle); **Make videos searchable** (frame spacing, multi-select, time estimate); per-folder cards with stats, Random clip (with player), video grid with posters/Play/Finder, Stop watching.
- Favourites: filter by account, grid.

### 4. Pilot (screenshot sorting)
Run on 400 random screenshots. Three drag-and-drop piles **Keep / Review / Junk**, thresholds as two sliders over a score histogram, crop vs whole-screenshot toggle, per-card score + keep/review/junk buttons + Auto, manual-override marker, Undo correction, "show more".

### 5. Positions (clip finder)
Position picker, number of videos, clip length, confidence, verified-only, optional video/creator filter, Show clips / Shuffle, **▶ Slideshow** (endless). Clip cards (player, position, verified/model, title, creator, times, Another video, Show file). Second tab "Which videos have it" (has / doesn't, with seconds in that position).

### 6. Analysis (every video and what the model made of it)
Status summary bar + clickable counts: Verified, Model up-to-date, Model older version, Not analysed, Failed (also Saved, Running, Queued #n). Filter chips, search, sort. **Rows**: checkbox, status pill, title + creator, **horizontal timeline strip coloured by position** (with legend), confidence meter, duration/sections/age, error text, per-row action (Analyse / Retry / Re-run / Frames). Toolbar: "Analyse everything that needs it (N)", select all, "Re-run on N selected", Model dashboard. Live "analysing X · N queued · Stop after this one" banner. Confirmation dialog when re-running verified videos (their saved version is never touched).

### 7. Model dashboard (review and training)
Video list drawer; **Frames view** (grid of frames with label colours, multi-select by click/shift/cmd, set label, exclude/restore, draggable START/END boundary tags, enlarge on hover, full viewer with ←→, 1–9 label keys, play 10 s) and **Sections view** (table: label dropdown, start/end, time, length, example frame, merge ticked rows, move to previous/next section); Next unsure / Next to review; Undo; Simplify; Test model on this video; Restore previous version; **Mark completed**; Save corrections; Save & retrain; Remove from training; frame-size slider. Sub-pages: **Category overview** (labels, counts, add label/sub-type, promote, Retrain now), **Browse** (all frames per category, move/mark correct, show only where model disagrees), **Models** (accuracy on unseen videos, confusion "what it confuses with what", training-data health), **Compare versions** (diff two label versions, frame by frame).

### 8. Links (collect and download)
Tabs: **Creators · Discover · Sites · Library · Lists · Download · Settings**.
- Creators: add box (paste links or names, site select, pages number/"all", scrape-after-adding), import existing link files, toolbar (sort, Re-categorise, Create folders, Find addresses, Scrape unscraped, Re-scrape all). **Creator cards**: avatar, name, download folder, link count, last scraped, per-site rows (Re-scrape / Unlink / Remove), Rename, Remove, Merge into…; "two pictures, which one?" chooser; expandable full-width **link panel** with category tiles, length chips, search, sort, min-views, copy.
- Discover: **swipe cards** (picture, name, rank, video count, views, verified) with Skip / Undo / Open / Keep, keyboard hints, filters, settings, collect more, recently-kept list with status.
- Sites: list of site profiles + a big editor form (base URL, page template, regexes, selectors, categories as "name: keywords", download method, etc.) + "Try it" test panel.
- Library: totals per category/length, export lists.
- Lists: list builder (filters, order, split, durations/titles, shuffle, save, "use for downloading") with live preview.
- Download: mode switch (Pick for me / Use a list / Enter links myself), filters (creators include/exclude, categories, lengths, site-mix ratio, how many, skip downloaded, min views, max per creator, share between creators), Preview then Download, **per-item live progress table**, Stop.
- Settings: many numeric/text options, download method, click-position capture helpers.
- Also a **"Frames from video links"** panel: paste several page links, frame spacing, optional from–to time, per-video 4-stage progress (find → read index → take frames → run model), results with "Open in model dashboard".

### 9. Data18 (reference database + model on stills)
Tabs: **Performers · Studios · Tags · Pornstars · Scraped creators · By position · Favourites**.
- Performers: name box → Scrape (progress); filter panel (title search, studio, co-star, year, sort; categories as **tri-state chips: click once = require, twice = exclude**, match all/any toggle; ethnicity chips); **video rows** (title, date, studio, co-stars, categories) that expand into **Photos** galleries (stills/photosets) with grid and lightbox, per-image predicted position + confidence badge, ♥, **Get video**, tick-boxes → "Run model on selected"; creator-level **batch panel** (all / N random, only new, include photosets, progress, cancel, see results by position).
- Studios / Tags / Pornstars: searchable, sortable lists or grids with counts and a refresh-from-site action.
- By position: creator + image-type + confidence thresholds; overview table → position → sub-type → image grid (breadcrumbs).
- **Get video** modal: per-site best match (thumbnail, score, "confident/possible"), choose, download whole video or **only a clip around the chosen still** (window length control), multi-select frames → "Download clips…" modal with queue status.

### 10. Session / storage sheet (overlay)
Login status and "which account", Log in / switch, storage meter + biggest folders, shortcuts to open folders (picks, favourites, library, pilot, cache).

## Overlays/states to show in the mockup
Command palette · Activity panel (one running, one failed, one done) · Refine drawer · Session/storage sheet · Prepare sheet · Slideshow/full-screen viewer (image and video-clip variants, with side meta panel) · Get-video modal · confirmation dialog (re-run verified videos) · empty state · a page with a running job banner · low-disk warning.

## Data and tone to use in the mock
- Invent creators, e.g. `@maya.ellis`, `@sofia_rain`, `Nora Vale`; use grey/colour placeholder rectangles or gradients for images (portrait for Instagram posts, 16:9 for video frames). No real people.
- Position names appear as in the product: Blowjob, Missionary, Doggystyle (sub-types Standing, Leg raised…), Cowgirl, Reverse Cowgirl, Spooning, Eating out, Facefuck, etc. Keep labels clinical and neutral; thumbnails stay abstract.
- Realistic numbers: ~200 accounts/folders, 209 analysed videos (115 verified), 111 favourites, 20 jobs, ~1,900 scraped links, 1,230 swipe cards.
- Verified = clearly confident (e.g. solid mark); model guess = visibly provisional with a confidence number.

## Constraints
- Desktop-first (≥1280 px) with a sensible narrow/phone behaviour for at least Search, Analysis and the Lightbox.
- Dark or light is your call; offer both if cheap. Must feel calm for hours of use (not neon, not marketing).
- Plain HTML/CSS/JS, no build step, no framework required; system or Google fonts fine.
- Prioritise: Search, Analysis, Positions, Lightbox, shell. Then Collections, Library, Links, Data18, Model dashboard, Pilot.
- Briefly explain at the end how you grouped the navigation and which functions you deliberately made secondary.
