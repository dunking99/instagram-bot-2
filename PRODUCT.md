# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML/CSS/JS prototype in `ui-html/`, served locally. The shipping UI is React + Vite + Tailwind in `ui/` talking to a FastAPI server (`server.py`, port 8503); it is not touched by design work until a prototype is approved and ported. Stack decision for the prototype: delegated (plain HTML/CSS/JS so it can be edited and previewed without a build step).

## Users

One person (the owner), working alone on their own Mac, in long sessions at a desk. They use the app to curate a private personal library of saved creator media (images from Instagram accounts, local image folders, and videos). They are fluent with the tool and use it daily; speed and density matter more than onboarding.

## Product Purpose

"Postroom" is a local desk for a personal media library. It indexes saved posts and videos with an image model (CLIP or SigLIP) so the owner can find and pull frames by describing them, by tag, by reference image or by pose; it keeps the library organised (accounts, imports, favourites, tag counts), analyses videos into labelled position sections so clips can be cut by position, sorts a pile of phone screenshots into keep/review/junk, and scrapes new links through a separate Links tool. Success is: find the right frame or clip in seconds, and always know what the background jobs (indexing, video analysis, imports) are doing.

## Positioning

Everything runs on this Mac against the owner's own files, and the search is by meaning (text, picture, pose, tags) rather than by filename or date.

## Operating Context

- Runs at http://localhost:8503 (FastAPI serves the built React UI); a second tool (Links) runs on port 8791 and is embedded; a model-review dashboard runs on 8765. Started with `start_all.sh`.
- Long-running background jobs (indexing, video analysis, imports, login) are normal; the UI must always show them without blocking work.
- Two search models (CLIP, SigLIP) keep separate indexes; the active one is switched at the top.
- Content is personal and sensitive; nothing leaves the machine. Thumbnails come from the local server.

## Capabilities and Constraints

Must all stay reachable in any redesign:
- Search: accounts (multi-select, "prepare indexes"), scene text, reference image, pose, suggested prompts, must-match tags, best/worst, posts count, "everything matching", each/pool/even account mixing, result mode (instant thumbs / save full size / links), refine drawer (dates, video include/mix/ratio/length, carousels, margin, cache mode), draw random, slideshow of results, favourite toggle, save, describe image, download, reveal in Finder.
- Library: per-account stats, tag-confidence slider, tag groups with counts (setting, outfit, shot, pose, arms), tag browsing with second-tag and/or logic, indexing of carousel posts ("index every image") with limits and browser windows, prepare, open library folder.
- Collections: image folders (import folder, import new, per-folder Finder), video folders (watched folders, discover/add/rescan, random pick), favourites, auto-import toggle.
- Pilot: run on N random screenshots, whole-screenshot vs crop toggle, keep/junk score thresholds, undo correction, move item between keep/review/junk, three piles.
- Positions: pick a position, videos, clip length, confidence, optional video/creator filter, verified-only, show clips, slideshow, which videos have it.
- Analysis: all videos with section strips, status (verified, up to date, older model, waiting, failed, running), filters, search, sort, select/re-run, "analyse everything that needs it", per-video review.
- Links (separate app, stays embedded as-is): creators, discover, sites, library, lists, download, settings.
- Global: jobs (list, active job log, stop/dismiss), session/login state, storage (free space, largest folders), command palette (Cmd-K), "/" focuses search.
- Python is 3.9 on the server; any UI change must keep every existing endpoint call working.

## Brand Commitments

Name: Postroom. The current look (dark warm ground, serif headlines, orange signal accent, four-square mark) is incumbent evidence, not a commitment; the owner asked for a complete redesign with creative freedom, including reordering, merging, adding or removing pages and changing colours, as long as every function remains.

## Evidence on Hand

Real data is available from the running app: accounts and thumbnails (`/api/thumb/...`), tag counts, 209 analysed videos (115 verified), 20 jobs, 111 favourites, 14 image folders, a 400-item pilot run. Captured page markup is in `ui-html/_original/index.html`. There are no user testimonials or metrics and none should be invented.

## Product Principles

1. The picture is the interface: results, thumbnails and clips get the room; controls stay out of the way until needed.
2. Every background job is visible and never blocks the desk.
3. Frequent actions are one click from the front door; rare, powerful ones are one step behind it, never removed.
4. Say what the model decided and how sure it is; the owner's verification always outranks the model.
5. One product: the same controls, states and language on every page.
