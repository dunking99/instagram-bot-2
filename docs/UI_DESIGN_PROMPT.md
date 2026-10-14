# UI design prompt (v2) for "Postroom"

How to use: send the BASE PROMPT below to each AI, with one different HOME paragraph pasted into the marked slot (four to choose from at the bottom).
Attach `docs/CAPABILITIES.md` and `PRODUCT.md`. Stage 1 first: compare the four skeletons, then tell each AI to go ahead with Stage 2.

---

## BASE PROMPT

# Design the interface for "Postroom", a private media desk

## What I want from you
A **clickable HTML mockup** of the whole app: one HTML file, fake data, no backend. Nothing has to really work, but navigation, links between screens and the states described below must be demonstrable.

**Start with your own vision.** Before designing, tell me what you think this product should *be*. Challenge any assumption in this brief, including how I've described my own habits. Everything outside the "Hard rules" is yours to break. Say what you broke and why.

## Two stages: please stop after Stage 1 and wait for me
**Stage 1 (now), text only, no code, no colours:**
1. Write down what the most typical answer to this brief would look like. Then do not build that.
2. Sketch three genuinely different concepts in a paragraph each. Pick the one you would stake your reputation on.
3. A short design thesis: what you optimised, and what you deliberately gave up.
4. **The skeleton**, in plain text: what I see when I first open the app (which regions, what is in each, what is fixed and what changes), how I move between kinds of work (one sentence), and the same for one other screen of your choice. Boxes and words only.

**Stage 2 (only after I reply):** build the mockup, then end with a table of the journeys below (clicks and page changes for each, and where you missed my budget and why).

## The product
A local desk for a personal library of saved media. Image and video models index everything so I can find frames by description, reference photo or body pose. A second model labels sections of every video by body position (e.g. "Standing", "Seated", "Side-on", each with sub-types) with a confidence score. Around that sit tools that collect links, scrape a reference database for creators and videos, find the same video on other sites, play a chosen segment straight from the site (no download) and grab frames from it, download videos, and review and correct the model's labels to retrain it.

## The user
One person, alone, on a Mac, in long daily sessions. Expert and fluent: speed and density beat onboarding. The content is private. Occasionally used on a phone for the most common tasks.

## Hard rules (the only non-negotiables)
1. The model's guess and my own verified label are always visibly different, and confidence is always visible. Re-running the model never overwrites something I verified.
2. Background work is always visible and never blocks me. Each job has progress, status, a log, and Stop/Dismiss/Retry.
3. Free disk space and login state are always visible somewhere.
4. My favourites are reachable from anywhere.
5. I can reach any function from the keyboard.
6. Destructive or overwriting actions have a safeguard.

## Strong defaults (you may overrule, but say why)
- Don't cram everything onto one screen: the app does several distinct kinds of work, and each deserves room. You decide how many places there are, what they are, and what to call them.
- Fewer places to go than today's eight pages (Search, Library, Collections, Pilot, Positions, Analysis, Data18 Scraper, Links), which are really five separate tools bolted together.
- Desktop first, with a phone view for finding things, checking progress and viewing favourites.
- Expert density: the media gets the room.

## What I need to be able to do (outcomes, not pages)
- Review and correct the model's labels on frames and sections, and retrain it.
- See, for any creator, a breakdown of positions across their videos: for example "Creator 1 has 200 videos containing 400 Standing segments, 200 Seated segments, ...", with counts, time, verified versus model, sub-types, and a way into the actual clips.
- Scrape creators and videos, collect links, find the same video on other sites, watch a segment of it without downloading, pull frames from it, and download it.
- Find frames and posts by description, reference photo or pose; browse the library and collections; keep favourites.
- Manage sources and indexing.

## The most important requirement: everything is connected
Everything you design is a view of the same data: **creator → videos → segments** (position, confidence, verified or model, clip range).
- **Links everywhere.** Every count, label and name is a link. Clicking "400 Standing segments" under a creator opens exactly those clips. "Review these" opens the correction work on exactly those videos. Context travels with me.
- **Chains.** One click starts a chain of steps that already exist as separate tools. Example: *scrape the creator → find each video on a site that can be streamed → pull the segments (stream or download) → run the position model → add the results to the breakdown → cut the segment clips into that creator's collection*. Design how a chain is started, configured (fully automatic, or pausing for my approval at chosen points such as after a video is matched, which you decide), watched (as one job with stages, not six jobs), and recovered when a stage fails. Show a chain mid-run and one that failed halfway.

## Where I start each day  ← PASTE ONE "HOME" PARAGRAPH HERE

## Journeys (budgets are targets; propose better measures if you have them)
1. Find a frame or clip by description, then favourite it or watch it: 3 clicks from anywhere, no change of place.
2. Start a full chain for a creator: 3 clicks. Watching it takes 0 changes of place.
3. See one creator's position breakdown and open the clips for one position: 2 clicks.
4. Review one video's segments, correct one label (it becomes "verified"), and move to the next video: 3 clicks to start, then keyboard.
5. A video found on another site: watch the segment around a chosen frame and pull frames from it: 4 clicks, no change of place.
6. See what is running or failed and retry it: 0 changes of place.

## Fake data to use
12 creators; 209 analysed videos (115 verified); about 930 segments; 8 position types with sub-types; 3 running jobs including one chain; one failed job; disk at 6 GB free; logged in as a made-up account.

## Reference
I'm attaching a capability inventory of today's app. It lists *everything the app can do*, organised by today's pages. **Do not mirror its structure.** Since it was written I've also added a tool that finds a video on 21 other sites, ranks the matches, and can play a chosen result and pull frames from it directly (19 of the 21 sites support this).

## Deliverable (Stage 2)
One HTML file: desktop layouts for every screen and state above, plus a phone layout for three journeys. Choose your own visual language.

---

## HOME paragraphs (a different one for each AI)

**HOME 1: chains**
My day starts with starting and watching chains: what is running, what finished, what failed, what to start next. Make this the centre of gravity of the whole design; everything else radiates from it. It must be a place where this job is *done*, not a dashboard of tiles summarising everything. Everything else must still be possible.

**HOME 2: the breakdown**
My day starts with the breakdown by creator: what I have, how much of each position, and where the gaps are. Make this the centre of gravity of the whole design; everything else radiates from it. It must be a place where this job is *done*, not a dashboard of tiles summarising everything. Everything else must still be possible.

**HOME 3: review**
My day starts with the next thing that needs my eyes: model labels to check or correct. Make this the centre of gravity of the whole design; everything else radiates from it. It must be a place where this job is *done*, not a dashboard of tiles summarising everything. Everything else must still be possible.

**HOME 4: finding**
My day starts with finding: a frame or a clip, by description, photo or pose. Make this the centre of gravity of the whole design; everything else radiates from it. It must be a place where this job is *done*, not a dashboard of tiles summarising everything. Everything else must still be possible.
