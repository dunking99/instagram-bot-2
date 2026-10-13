---
version: 1
slug: "ui-html-a-departures-index-html"
primary_target: "ui-html/a-departures/index.html"
related_targets: []
---

# Surface brief: Postroom redesign A, Departures

Mode: Operate. Whole app shell plus six pages (Search, Saved, Sources, Videos, Sort, Fetch). Owner-only, one Mac, long evening sessions at a desk.
Task: find and keep frames and clips fast; always see what jobs are doing; keep every existing function reachable.
Information architecture: Library + Collections merged into Sources (accounts master/detail, tags, folders, imports); Positions + Analysis merged into Videos (Clips | Review); Favourites promoted to Saved; Pilot renamed Sort; Links embedded as-is as Fetch.

## Direction contract

THESIS: A railway timetable's discipline applied to a media desk: everything is a line, a stop or a departure, so state reads at a glance. Refuses the generic dark sidebar app with a centered hero and card grids.
OWN-WORLD: Near-black neutral ground so photos are the brightest thing; Swiss-poster yellow on the nav rail and page header band only, black ink on it; position colours from the data as line colours; board states green (on time), amber (older model), red (failed), yellow (boarding); condensed highway-sign grotesque with tabular figures, mono for times. Hairline seams, no shadows, no cards in cards.
STORY: The owner sees at once where to go (the rail), what is running (the departures panel), and which videos and indexes need attention (delayed/cancelled rows), then acts without leaving the page.
FIRST VIEWPORT: Left yellow rail with stations (pages) on a vertical line; yellow header band with page title, model switch, storage and session; centre composer with the account chips, one large query field and the Draw button; right persistent Departures panel listing jobs as board rows (time, job, status) with the running job boarding.
FORM: Assigned 5 of own list (railway timetable / departures board), raised by the dev-console world's persistent panels and by the transit-map world's coloured lines; seed key 2a6cd7f5.
SIGNATURE: Route strips: every video's analysed sections drawn as a transit route (coloured line per position, station dots at boundaries, time labels), used in Review, Clips and cards; plus the live departures board for jobs.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
