# Task: run my position-classification model on the images in my data18 dashboard

You are being brought in to connect an existing image model (which you know about) to a separate web dashboard
(which you know nothing about, described below). Read this whole brief first. Ask me before doing anything
destructive or anything this brief doesn't cover.

## The dashboard in one paragraph
A standalone local tool in `~/data18-scraper` (its own Python venv at `.venv`; do NOT install torch/transformers into it).
`server.py` is a stdlib `http.server` app on http://127.0.0.1:8790; `static/index.html` is a single-file vanilla-JS front end
(no build step; the server re-reads it on every request, so HTML edits need no restart, but changes to `server.py` or
`scraper.py` need a restart: `kill $(lsof -ti tcp:8790); .venv/bin/python server.py`). `scraper.py` holds the scraping code.
It is deliberately NOT connected to `~/instagram-bot-2` or `~/Links-3`; keep it that way. Do not edit anything outside
`~/data18-scraper` except to read the model.

It scrapes data18.com performer pages. Each scraped video has galleries of images, which the dashboard shows in an
expandable "Photos" panel under each video (grid of full-size images + a lightbox).

## The images (what the model should run on)
Each video ("scene") has galleries. Labels seen in my data: `Primary` (1 poster image), `Photoset`, `Photoset 1`, `Photoset 2`,
`Video Stills`, `Video Stills 1`, `Video Stills 2`, `Videostills`, `Trailer`.
- **Video Stills** (and `Video Stills 1/2`, `Videostills`) are frames taken from the video: landscape, same kind of image my
  model was trained on. This is the main target.
- **Photosets** are posed photographs, a different image type from video frames. I want the model run on them too, but the results
  should be kept clearly separate (the model may be less reliable there), e.g. a `gallery_type` field on every prediction.
- Skip `Primary` and `Trailer` unless I say otherwise.

Where the data lives (all under `~/data18-scraper/data/`):
- `results/<performer-slug>.json`: `{slug, total, videos:[{scene_id, title, url, date, studio, performers, categories, ethnicity,
  tags, galleries:[{label, count}], ...}]}`. One file per scraped performer (e.g. kyler-quinn: 340 videos). `galleries` here is only a
  summary (names + counts), NOT image addresses.
- `scene_details.json`: `{scene_id: {categories, ethnicity, tag_slugs, galleries:[{gid, label, count, images:[{"t": thumb_url, "f": full_url}]}]}}`.
  A gallery only has an `images` list once its images have been fetched (this happens when someone opens that video's Photos panel,
  or via the API below). **Always use `f` (full size), never `t` (small thumbnail).**
- `imgcache/`: downloaded image files, keyed by sha1 of the URL (managed by the server's `/img` proxy).

How to get the image lists and bytes:
- `GET http://127.0.0.1:8790/api/photos?scene_id=<id>` returns `{"galleries":[{gid,label,count,images:[{t,f}]}]}` and fetches the
  addresses from data18 on demand if they aren't cached (about 0.3 s per video the first time; it is rate-limited and polite).
  Needs the dashboard server running. Prefer this over re-implementing scraping.
- `GET http://127.0.0.1:8790/img?u=<url-encoded full image url>` returns the image bytes. IMPORTANT: data18's image hosts
  (`bdn.dt18.com`, `i5.dt18.com`, `vs.dt18.com`) return 403 unless the request carries `Referer: https://www.data18.com/`. The
  `/img` proxy adds that and caches on disk, so use it (or send that header yourself). Do not hammer the hosts: keep to a few requests per second.
- Scene IDs: `1350614` etc. The first digit is data18's type digit, the rest is the number (the endpoints need them split; the server already handles that).
- For a quick local copy of one video's stills: `.venv/bin/python download_stills.py <scene_id> --out <folder>` writes `000001.jpg`, ... (refuses a non-empty folder unless `--append`).

Scale: a performer has ~250-350 videos, each with ~25-40 stills plus ~15 photoset images, so tens of thousands of images per performer. Plan for
batching, resumability (skip images already predicted), and a progress indicator. Work performer by performer or video by video, and let me
pick which scope to run.

## Integration contract (please follow this so the dashboard and model stay decoupled)
1. **Run the model in its own environment** (the one it already has) via a script you write, e.g. `~/data18-scraper/predict_images.py`
   run with the model's Python, NOT the dashboard's `.venv`. It reads image lists + bytes from the sources above and never imports the dashboard code.
2. **Write results to `~/data18-scraper/data/predictions.json`** (atomically: write a temp file, then rename; and merge, don't overwrite,
   so partial runs accumulate). Suggested shape, keyed by full image URL so it survives re-scrapes:
   ```json
   {
     "model": {"name": "...", "version_or_file": "...", "run_at": "2026-..-.."},
     "images": {
       "https://i5.dt18.com/pics/8/154294/11.jpg": {
         "scene_id": "1350614", "gallery": "Video Stills", "gallery_type": "stills",
         "label": "Doggystyle", "sub": "Standing", "confidence": 0.93,
         "top": [["Doggystyle/Standing", 0.93], ["Doggystyle/Other", 0.04]]
       }
     }
   }
   ```
   Use whatever label hierarchy the model actually has (main position + sub-type); keep unconfident results rather than hiding them, and record
   the confidence so the UI can threshold. If the model has a way to say "none / unsure / not a sex position", include it.
3. **Dashboard side** (after the predictions file exists; small, surgical edits only):
   - `server.py`: add `GET /api/predictions?scene_id=<id>` (and/or a performer-level summary) that reads `data/predictions.json`.
     Follow the existing pattern of the other `/api/...` handlers; stdlib only (no Flask).
   - `static/index.html`: in the Photos panel (functions `togglePhotos`, `photoSections`, `proxy`), show each image's predicted label +
     confidence as a small badge on its tile and in the lightbox caption (`openLightbox`/`lbShow`). Optionally a per-video summary line
     (e.g. counts by position) on the video row, and a filter ("videos containing X").
   - **Gotcha:** video rows are cached by `rowSig(v)` / `rowFor(v)` so expanded panels survive refreshes. If you add anything to a row that
     can change after load (prediction summaries), include it in `rowSig` or it won't update.
   - Styling uses CSS variables with light/dark support; reuse them (`--card`, `--line`, `--accent`, `--muted`, the `.chip` class).

## Things to be careful about
- Domain shift: model trained on video frames, photosets are posed photos. Report accuracy/behaviour on stills and photosets separately
  and tell me honestly how trustworthy the photoset predictions look.
- Don't re-run the model on images already in `predictions.json` for the same model version unless I ask.
- Verify your work: run on one video's stills first, show me the output, then scale up. Spot-check a few predictions against the images.
- If something about the dashboard doesn't match this brief, trust the code (`server.py`, `static/index.html`, `scraper.py`) and tell me.
- Keep changes minimal and tell me exactly which files you modified.
