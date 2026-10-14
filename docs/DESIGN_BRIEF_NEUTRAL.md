# Brief: design the interface for "Postroom", a private media desk

## The task
Design the complete interface for the application described below and deliver it as a **static HTML/CSS mockup** (small amounts of JS for navigation and showing/hiding things are fine). Nothing needs to function, and there is no backend. Use invented, realistic-looking sample content.

**Everything about how it looks, feels, is organised and is navigated is your decision**: visual language, colour, type, density, layout, navigation model, how functions are grouped, which are prominent and which are tucked away, and which interaction patterns to use. I am deliberately not giving any of that. Make bold, considered choices of your own rather than producing a conventional dashboard, and be prepared to defend them. Every function listed below must be reachable somewhere in your design. You may merge, split, reorder or rename areas freely.

At the end, write a short note explaining your main design decisions and anything you made deliberately secondary.

## Who uses it
One person, alone, on a Mac, in long daily sessions. Expert and fluent; speed and density matter more than onboarding. Occasionally viewed on a phone. The content is private and personal.

## What the product is
A local desk for a personal library of saved media: social-media posts, local image folders, and videos. Software indexes everything so the owner can find frames by describing them, by attributes, by reference photo, or by body pose. A second model labels every video by position, producing sections along each video's timeline with a confidence value, so clips can be pulled by position. Around that are tools to collect links, download videos, build a reference database, and review/correct the model.

Success: find the right image or clip in seconds, and always know what background work is happening.

## Requirements that are about meaning, not appearance
- The media itself (images, frames, clips) is the main content; everything else supports it.
- Background work (indexing, analysis, downloads, imports) must always be visible and never block other work. Each has progress, status, a log, and can be stopped or dismissed.
- The model's output must always be distinguishable from the owner's own verified decisions, and its confidence must be visible. The owner's verification always outranks the model, and re-running the model must never overwrite verified work.
- Frequent actions are fast; rare but powerful actions stay available but less prominent.
- The whole product should feel like one product, not several tools bolted together.
- The owner's favourites must be reachable from anywhere at any time.
- The owner must be able to jump to any function quickly using the keyboard.
- Always visible somewhere: free disk space (with a warning state), and whether the social-media login is valid.
- Destructive or overwriting actions need a safeguard.
- Must be usable at desktop size and sensibly usable on a phone for the most frequent tasks (finding things, checking analysis, viewing favourites).

## Functions the interface must provide

### A. Finding images and posts
- Choose which accounts/collections to search (many at once; add a new one by name; see which are not yet indexed; prepare them).
- Describe what is wanted in words; and/or supply a reference photo; and/or supply a body-pose reference. Any combination, each switchable on or off; control the relative weight of text vs photo, and how strict the scene match is when combined with pose; allow left-right mirrored poses.
- Require attributes drawn from groups (setting, outfit, shot type, pose, arms) with an adjustable required confidence.
- Choose best matches or worst matches (for testing). Choose a number of results, or "everything matching" with a cap. Choose how multiple accounts share the results (each / pooled / even split).
- Choose result form: instant thumbnails, saved full-size files, or links only.
- Secondary options: date range, include videos, mix of videos vs photos, video clip length, carousel posts (first photo only vs every slide, strictness, look inside the N most promising), size of the random pool among top matches, data freshness (use saved / check for new / rebuild from scratch), save location.
- An empty request means a fully random draw.
- Starter prompt ideas when nothing has been entered. Visible record of the active options. Live progress/log for a running search, and cancel.
- Results: each with a similarity score; select several; view full-screen one by one; slideshow; favourite; download; open the original post; copy link; show in file manager; save selected as thumbnails or full size; empty-result help.

### B. Finding videos by position
- Choose one or more positions (main positions and their sub-types, each showing how many analysed videos have it).
- For each, optionally restrict to specific creators; ask for the same position more than once with different creators.
- Global creator include/exclude and a limit per creator.
- Either a random mix totalling N videos, or an exact count per position.
- Clip length (15 s to 5 min, or whole section), minimum model confidence, verified-only.
- Results are playable clips, each showing position, verified vs model guess (with confidence), title, creator, clip time range and section time range; swap any one for a different video; reveal the file; endless full-screen slideshow that keeps drawing new combinations without repeating videos.
- A single-position view that also lists which videos have that position and which do not (with time spent in it).

### C. Understanding what is indexed
- Per account: number of photo posts, reels, carousels, extra slide photos, whether indexes (search, pose, carousel detection) exist and when last prepared.
- Browse by attribute: counts and percentages for each attribute value (including "no confident value"); open any value to see its images ordered by confidence; combine a second attribute (alone or both required).
- Jobs: detect carousels, build pose index, prepare, index every image of carousel posts (progress "opened X of Y", batch size, 1–3 parallel browser windows with a rate-limit warning, keep going until done), build categorised folders on disk (with a preview of the folder tree).
- A listing of all saved accounts with status.

### D. Managing sources
- Image folders: import a folder as a searchable collection; import only new files; automatic import of new files; show pending/indexed counts.
- Video folders: watch a folder (new videos appear automatically within seconds); create many at once (name + folder rows); check now; scan a root folder for sub-folders not yet added, rename and tick which to add, optionally add new ones automatically; make videos searchable by sampling a frame every 2–60 s for chosen folders at once, with a time estimate; play a random clip from a folder; browse its videos; stop watching.
- Favourites: browse all, filter by account, open the folder.
- Account session: see which account is logged in, check, log in or switch; storage usage (total, project, largest folders, largest thumbnail folders); open key folders.

### E. Screenshot triage
- Run a triage over 400 random screenshots from the photo library. Each is scored on whether it shows a person and sorted into Keep / Review / Junk. The owner can move any item manually (overrides persist, can revert to automatic, undo the last 50 corrections), adjust the keep and junk score thresholds while seeing the score distribution, and switch between the cropped photo and whole screenshot.

### F. Video analysis overview
- A list of every video with its state: verified, saved by owner, analysed by current model, analysed by an older model, not analysed, failed (with error), running, queued (position).
- Each video shows its sections along its timeline by position, mean model confidence, duration, number of sections, age of the analysis.
- Summary counts per state, filtering by state, text search, sorting (needs attention, title, creator, lowest confidence, longest).
- Actions: analyse everything that needs it; select several and re-run; retry a failed one; open a video in the review tool; stop after the current video. A current-run indicator (which video, how many queued/done/failed).
- Warning when re-running affects videos the owner verified (their versions stay untouched).
- Pause/resume of automatic analysis of newly added videos.

### G. Reviewing and correcting the model
- For one video: see all its frames in order, each with its label; select frames individually, as a range, or add to a selection; set a label on the selection; exclude/restore frames from training; move the boundary of a section; enlarge a frame; step through frames full-screen with keyboard label shortcuts; play 10 seconds from a frame.
- Section-level: per-section label, merge adjacent sections, move a frame to the previous/next section, jump to next/previous section or next unsure one, jump to next video needing review.
- Undo; simplify (auto-merge tiny sections); test the model on this video again; restore the previous version; mark completed; save corrections; save and retrain; remove from training; adjustable thumbnail size.
- Label management: list of labels with counts, add a label or a sub-label, promote a rarely used label into the trained set, retrain now.
- Browse all labelled frames by label; move frames between labels; mark as correct (selection / section / video / all); show only frames where the model disagrees; undo.
- Model quality: accuracy on videos it never saw, what it confuses with what (parent and sub-labels), whether training data matches the owner's corrections.
- Compare two versions of a video's labelling, ordered by biggest change, with a frame-by-frame view.

### H. Collecting links and downloading videos
- Creators: add many at once by pasting any mix of web addresses and plain names; choose the source site and how many pages (a number or all); scrape immediately or not. The same person on several sites is recognised and merged automatically or on suggestion; merges can be undone (unlink), a site can be removed from a person, or two people merged by hand.
- Each creator: picture (if two different pictures are found, the owner chooses), display name, download folder name (optionally renaming the existing folder), link count, last scraped date, per-site status with re-scrape, rename, remove.
- Bulk actions: re-categorise all links under current keywords (reporting what moved), create missing folders, find missing addresses by name, scrape unscraped, re-scrape all. Import existing link files.
- Browse a creator's links: category counts, length bands, text search, sort (scrape order, title, views, length), minimum views (e.g. 100k, 1.5m), copy shown links.
- Discovery: a collected directory of ~1,200 performers shown one at a time with picture, name, rank, video count, view count and verified flag; keep (adds and scrapes them), skip, undo, open their page; filters (video count, view count, rank, verified); setting for how many pages to scrape per kept performer; collect more; reset skipped; recent keeps with their scrape status.
- Site definitions: create/edit/delete the rules for a source site (address, how next pages look, how to recognise video links and durations, areas to include/ignore, view-count and picture selectors, categories as named keyword lists, a dominant category, forced-"Other" keywords, how to find a creator by name, how to detect "no such creator", delay between requests, download method), with a test that shows what would be found.
- Library of links: totals by category and length; export as text lists.
- List builder: filter by creators, categories, lengths, minimum views, skip already-downloaded; order (creator, title, category, random, scrape order, views); split into several files (none / by category / by creator); include durations/titles; reshuffle; save; send straight to downloading.
- Downloading: choose by "pick for me" (filters + count), a built list, or links typed by hand into a chosen folder. Filters: creators include/exclude, categories, several lengths, ratio between source sites, how many, skip downloaded, minimum views, max per creator, how creators share the run (equal / at least N each). Preview exactly what would be downloaded (with a per-site tally), then download. A live per-item table (state, percent, size, elapsed, file, destination) and a stop control; auto-stop after repeated failures.
- Settings: many numeric and text options (download method and quality cap, parallelism, waits, timeouts, size limits on scraped videos, default site, name-matching sensitivity, etc.) plus helpers to capture on-screen click positions/button images for the browser-automation download method.
- Frames from video links: paste several video page addresses (one per line), choose a frame interval and an optional start–end time; only the needed parts are read (nothing saved); up to 3 videos at once, others queue; each shows four-stage progress (find video, read index, take frames, run model) with percentage, frames, data read and time left; result links to review and analysis.

### I. Reference database of a public performer site
- Look up a performer by name and collect their videos with details (categories, ethnicity, tags, studio, co-stars, date, galleries) and progress.
- Filter a performer's videos: title text, studio, co-star, year, sort (newest, oldest, A–Z, most/fewest photos), categories where each can be set to required, excluded or neutral, with all/any matching, ethnicity.
- Each video expands to its photo galleries (video stills, photosets), viewable large one by one; select images and run the position model on them; each image shows its predicted position, sub-type and confidence; per-video summary of positions; favourite any image.
- Run the model across all or N random videos of a performer (only new, include photosets), with progress and cancel.
- Lists, each searchable and sortable, with a refresh-from-site action: studios (top-level vs sub-channels, grouped by parent), tags (with how many collected videos have each; expand to see them), directory of performers (name, picture, scene/movie counts, rank), all performers already collected.
- Browse all model results by position: filter by performer, image type, and minimum confidence for position and sub-type; drill from overview to position to sub-type to images.
- Favourite frames list with search.
- "Get video": for any scene or image, search other sites for that video (ranked matches per site, confident/possible, thumbnail and score), pick the right one (remembered), then either download the whole video or only a clip around a chosen still (clip length 10 s–15 min), or queue clips for many selected frames at once with status per item. Downloads automatically enter analysis.

### J. Global
- Quick keyboard jump to any function or command; shortcut to start a search.
- Notifications for completed/failed actions; indication when the server is older than the interface.
- A full-screen viewer for images and video clips used everywhere: next/previous, auto-advance with adjustable interval, shuffle, pause, favourite, download, open original, copy link, show in file manager, shows score/position/confidence/verified status/time range where relevant, continues with new items on endless sources.

## Sample content to invent
Invent your own people, accounts, titles and numbers at a realistic scale: roughly 200 accounts and folders, 200+ analysed videos of which about half are verified, 100+ favourites, about 20 recent jobs, ~1,900 collected links, 1,200 directory entries. Real people must not appear. Images may be abstract placeholders in whatever way suits your design (portrait for posts, landscape for video frames). Keep any visible labels clinical and neutral.

## Priority if you cannot do everything
1. The overall structure and the places where the owner spends most time: finding images (A), finding videos by position (B), video analysis overview (F), favourites, and always-present status and background work.
2. Sources (D), review tool (G), link collecting/downloading (H).
3. Index overview (C), reference database (I), screenshot triage (E).
