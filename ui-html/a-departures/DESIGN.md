---
name: Postroom Departures
description: A railway timetable's discipline on a media desk; near-black ground, poster yellow, line-coloured data.
colors:
  ground: "#0e0f11"
  board-black: "#0a0b0c"
  sheet: "#15171a"
  sheet-raised: "#1b1e22"
  seam: "#2a2e33"
  seam-strong: "#3d424a"
  ink: "#eeece6"
  ink-dim: "#b0ada3"
  ink-mute: "#8f8d85"
  poster-yellow: "#ffcc1a"
  yellow-hover: "#ffd94d"
  yellow-pale: "#fff1a8"
  yellow-ink: "#14120a"
  selected-wash: "#2a2406"
  on-time-green: "#5fd38d"
  older-amber: "#ff8a3d"
  failed-red: "#ff6b5e"
  info-blue: "#6cb4ff"
typography:
  display:
    fontFamily: "Barlow Condensed, Barlow, sans-serif"
    fontSize: "38px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.02em"
  headline:
    fontFamily: "Barlow Condensed, Barlow, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.04em"
  title:
    fontFamily: "Barlow Condensed, Barlow, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.05em"
  query:
    fontFamily: "Barlow Condensed, Barlow, sans-serif"
    fontSize: "clamp(28px, 3.1vw, 40px)"
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: "0.01em"
  body:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "14.5px"
    fontWeight: 500
    lineHeight: 1.4
    fontFeature: "tabular-nums"
  label:
    fontFamily: "Barlow Condensed, Barlow, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.12em"
  mono:
    fontFamily: "Overpass Mono, ui-monospace, monospace"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.3
rounded:
  hairline: "2px"
  round: "50%"
spacing:
  xs: "6px"
  sm: "10px"
  md: "16px"
  lg: "28px"
  rail: "212px"
  board: "312px"
components:
  button-primary:
    backgroundColor: "{colors.poster-yellow}"
    textColor: "{colors.yellow-ink}"
    rounded: "{rounded.hairline}"
    padding: "0 18px"
    height: "38px"
  button-primary-hover:
    backgroundColor: "{colors.yellow-hover}"
  button-default:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.hairline}"
    padding: "0 14px"
    height: "34px"
  chip:
    textColor: "{colors.ink-dim}"
    rounded: "{rounded.hairline}"
    padding: "0 10px"
    height: "28px"
  chip-on:
    backgroundColor: "{colors.selected-wash}"
    textColor: "{colors.poster-yellow}"
  input:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    rounded: "{rounded.hairline}"
    padding: "0 10px"
    height: "34px"
  panel:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.hairline}"
  rail-station-current:
    backgroundColor: "{colors.yellow-ink}"
    textColor: "{colors.poster-yellow}"
    padding: "11px 16px 11px 24px"
  header-band:
    backgroundColor: "{colors.poster-yellow}"
    textColor: "{colors.yellow-ink}"
    padding: "12px 28px"
  departure-row:
    backgroundColor: "{colors.board-black}"
    textColor: "{colors.ink}"
    padding: "10px 16px"
---

# Design System: Postroom Departures

## Overview

**Creative North Star: "The Departures Board"**

Everything on the desk is a line, a stop or a departure, so state reads at a glance. A near-black neutral ground lets photographs be the brightest thing on screen; poster yellow with black ink marks where you are and what you can do; green, amber and red are board states, not decoration; the colours of the data (one per video position) become the colours of the lines. Surfaces are separated by hairline seams and one heavy 4px rule per region, never by shadow.

The density is that of a station concourse: condensed uppercase signage for titles, tabular figures and mono for every time, count and score, small square-cornered controls. It is built for one owner in long desk sessions, so speed and scanning beat ornament.

**Key Characteristics:**
- Three-column shell: yellow rail (212px), work area under a yellow header band, persistent black Departures board (312px).
- Yellow is a signal colour: rail, band, primary action, selection, focus, active tab, progress. It is never a large fill inside the work area.
- Flat, shadowless, 2px corners, hairline seams.
- Route strips (coloured legs, station dots, mono times) are the signature data drawing.

## Colors

A neutral near-black stage with one saturated poster yellow and four board-state colours; chroma lives only in the signals and in the photographs.

### Primary
- **Poster Yellow** (`poster-yellow`): the rail, the header band, the primary button, current selection outlines and focus rings, active tab underline, switched-on toggles, the running job (boarding), board title and clock, bar fills for progress.
- **Yellow Ink** (`yellow-ink`): near-black warm ink used for everything drawn on yellow (rail line, station rings, band text, borders on the band) and as the inverted current-station fill.
- **Yellow Hover / Pale** (`yellow-hover`, `yellow-pale`): hover steps for the primary button and the rail station dots only.

### Secondary (board states)
- **On-Time Green** (`on-time-green`): verified, up to date, finished, index progress, the keep pile.
- **Older-Model Amber** (`older-amber`): analysed by an older model, the review pile.
- **Failed Red** (`failed-red`): failed, cancelled, destructive actions, warning pip on the session chip, the junk pile.
- **Info Blue** (`info-blue`): defined, reserved for informational notes; no widespread use in the build yet.

### Neutral
- **Ground** (`ground`): page background and the inset fill of inputs, option drawers and logs.
- **Board Black** (`board-black`): the Departures panel only, one step darker than the ground.
- **Sheet / Sheet Raised** (`sheet`, `sheet-raised`): panels, tiles, tables; raised for hover rows and image placeholders.
- **Seam / Seam Strong** (`seam`, `seam-strong`): hairline dividers, and control borders respectively.
- **Ink / Ink Dim / Ink Mute** (`ink`, `ink-dim`, `ink-mute`): primary text, secondary text, labels and placeholders. Ink Mute (`#8f8d85`) is the floor for any text on the ground.
- **Selected Wash** (`selected-wash`): dark yellow-brown fill behind any selected row, facet, chip or palette item, always paired with yellow text.
- **Line colours:** each video position carries its own colour from the data (`D.colours`, fallback `#9aa5b1`). These are data, not palette: use them only for route legs, swatches, pile and clip-time rules, never for chrome.

### Named Rules
**The Signal Rule.** Yellow means "you are here / you can act / this is selected / this is running". If a yellow element is none of those, remove it.
**The Board States Rule.** Green, amber, red state colours appear only as text, outline, dot or 4px rule on a dark ground, never as a filled surface; the single filled state is yellow for a running job.
**The Brightest Photo Rule.** No chrome element outshines a thumbnail; the only large fills are the rail and the band, and they frame the work rather than sit in it.

## Typography

**Display / Label Font:** Barlow Condensed (700, 600, 500) with Barlow then sans-serif
**Body Font:** Barlow (400-700) with system-ui
**Mono Font:** Overpass Mono (400, 600) with ui-monospace

**Character:** Highway-sign condensed grotesque for naming things, a plain humanist grotesque for reading, and a mono for anything that is a time, count or score. All fonts self-hosted from `ui-html/fonts/`; tabular numerals are on globally.

### Hierarchy
- **Display** (700, 38px, 1, 0.02em, uppercase): the page title in the yellow band. 30px under 980px.
- **Departures title** (700, 30px, uppercase): board heading and pile headings.
- **Headline** (700, 26px, 0.04em, uppercase): results, dialog and empty-state headings; panel headings are 22px.
- **Title / Station** (600-700, 20px, 0.05em, uppercase): rail stations and tabs.
- **Query** (600, clamp 28-40px, 1.08, sentence case): the search composer's one large field.
- **Body** (500, 14.5px, 1.4): all running text and controls (13-14px for buttons and chips, 13px for hints and meta).
- **Label** (600, 12px, 0.12-0.14em, uppercase, Ink Mute): field names, table heads, board column heads.
- **Mono** (400-600, 11.5-14px; 22px for the clock, 24-26px for clip times and pile counts): times, counts, scores, log text, keyboard hints.

### Named Rules
**The Mono Is For Numbers Rule.** Every time, count, score and duration is Overpass Mono with tabular figures; words are never mono.
**The Sign Case Rule.** Uppercase condensed is for headings, stations, tabs, table heads and small field labels only; sentences, names and values stay in Barlow at sentence case.

## Layout

Fixed three-column shell filling the viewport: rail 212px, fluid work area, board 312px. The board can be closed from the rail, collapsing its column to zero with a 0.35s eased transition. The work area is a yellow band over a scrolling page padded 22px 28px 48px. Rhythm is 6, 8, 10, 12, 14, 16, 18, 28px; gaps are tight and consistent, panels sit directly against hairlines instead of floating in whitespace.

Pages are built from: a composer (stacked blocks divided by seams), result walls (auto-fill grid, 176px minimum tiles, 10px gap, 3:4), master/detail splits (1.25fr / 1fr, 18px gap), tables with sticky heads, three-column piles, and row lists with fixed column templates. Embedded Fetch fills the work area edge to edge.

Responsive: at 1280px the board narrows to 280px and splits stack; at 980px the rail shrinks to 76px (dots only, labels hidden), the board becomes a fixed overlay drawer (340px max), piles stack and the title drops to 30px.

## Elevation & Depth

Flat. There are no box-shadows or text-shadows in the build. Depth is tonal (ground, sheet, sheet raised, board black) plus rules: 1px seams between regions, a 4px yellow-ink rule under the band, a 4px yellow rule under the board header, a 6px yellow top border on dialogs and drawers, a 4px coloured rule above pile headings and clip times. Overlays use a 70% black scrim.

### Named Rules
**The Seam Rule.** Separate with a hairline or a heavy rule, never with a shadow, and never nest a bordered panel inside another bordered panel.
**The Hover Is Tone Rule.** Hover steps one tone up (sheet raised) or inverts to yellow-ink on yellow; nothing lifts or glows.

## Shapes

Square and signage-like: a 2px radius on every control, panel, chip, badge and state pill. True circles are reserved for station dots, avatars, route stations, slider thumbs and status pips. Selection is shown by outline and wash, not by shape change. Route legs and swatches are straight bars (6px legs, 8-10px swatches).

## Components

### Buttons
- **Shape:** 2px corners, 1px Seam Strong border, 14px / 600 label, 34px tall (28px small).
- **Primary:** Poster Yellow fill, Yellow Ink text, 700 weight, 38px tall, 0 18px padding; hover lightens to Yellow Hover. One primary per region (Draw is the first-viewport example).
- **Default:** transparent with ink text; hover fills Sheet Raised and brightens the border.
- **Danger:** Failed Red text and 50% red border.
- **Icon button:** 32px square on a 85% ground scrim; hover turns border and glyph yellow; on state is yellow fill (favourite). Icons are inline SVG at 16px.
- **Disabled:** 40% opacity, not-allowed cursor.

### Chips and segmented controls
- **Chip:** 28px, transparent, dim text, Seam Strong border; hover brightens. **On:** Selected Wash, yellow text and border, 700 weight. **Ghost:** dashed border for "add".
- **Segment (`.seg`):** joined cells; selected cell is solid ink on ground. The model switch uses the on-yellow variant: yellow-ink borders, selected cell inverted to yellow-ink with yellow text.
- **Band chip:** outlined yellow-ink, inverts on hover; a pip dot shows storage/session state (red when warning).

### Inputs / Fields
- Ground fill, 1px Seam Strong border, 2px corners, 34px tall, 0 10px padding; placeholder Ink Mute. **Focus:** 2px yellow outline and yellow border. Field labels are the Label style above the control.
- **The query field** is borderless, transparent, condensed 28-40px, on the composer; focus is carried by the composer, not an outline.
- **Range:** 4px track, 16px yellow-ringed round thumb; **checkbox** accent yellow; **toggle:** 34x18 square track, yellow when on with a yellow-ink knob.

### Cards / Containers
- **Panel:** Sheet fill, 1px Seam border, 2px corners, header with condensed 22px title over a seam, 16px body padding.
- **Tile (result):** 3:4, Sheet fill, 1px seam, caption on a bottom gradient to near-black, actions fade in on hover/focus (favourite stays visible when on); video badge is a small ink-on-light label top left.
- No cards in cards; groups inside a panel are separated by seams.

### Navigation (the Line)
- Yellow rail with the Postroom mark and a vertical yellow-ink line running through station dots (18px, ringed). Stations are 20px condensed uppercase; the current station inverts (Yellow Ink fill, yellow text, dot filled yellow); a mono count badge sits at the right. Rail foot holds two outlined buttons (Departures toggle with count, Go to... with the command-palette shortcut). Tabs are 20px condensed uppercase with a 4px yellow underline when selected. Collapses to dots at 980px.

### Header Band
- Yellow, Yellow Ink text, 4px yellow-ink bottom rule: page title (Display) and one-line subtitle at 80% opacity on the left, model switch, storage and session chips on the right.

### Departures Board (signature)
- Board Black panel with a 4px yellow rule under its header: yellow condensed title, yellow mono clock, column heads, then rows of time (mono, 50px column), job title with mono meta, and a status pill. The running job is "boarding": yellow time and a solid yellow pill with a 4px yellow progress bar. Rows expand to a mono log (140px max). Foot carries actions.
- **Status pills (`.state`):** condensed 13px uppercase, 1px currentColor outline, 2px corners; go / late / stop are outline-only in their colour, live is the yellow fill, wait is dim, done is bare mute text.

### Route Strip (signature)
- A 16px high flex row of legs (6px, one per analysed section, colour from the position) joined by 10px ink station dots at boundaries and a hollow 12px end station; unaffected legs may dim to 28%; mono 11.5px time labels sit beneath. Used in Review, Clips and cards; a legend (`route-key`) uses 18x6 bars. Sections lists, split meters and stacked bars reuse the same bars.

### Tables, lists and overlays
- Tables: sticky label-style heads, 8px 10px cells, seam row rules, mono right-aligned numbers, selected row is Selected Wash with yellow text. Facet and position rows use the same selected treatment, with a 2px yellow bar for relative size.
- Dialogs and drawers: Sheet fill, 6px yellow top border, condensed heading; command palette uses a condensed 24px input and Selected Wash for the active item. Toast is an ink slab with ground text.

### Motion
Short and eased: 0.2s tone changes, 0.25-0.35s `cubic-bezier(0.22, 1, 0.36, 1)` for drawers, chevrons, toggle knobs and the board collapse. `prefers-reduced-motion` disables all animation and transition.

## Do's and Don'ts

### Do:
- **Do** keep yellow to the signals named in The Signal Rule and keep Yellow Ink as the only ink on yellow.
- **Do** colour video positions only with their data colour, and draw sections as route strips.
- **Do** show job and index state as a board row or state pill (time, title, status) and let the running job board in yellow.
- **Do** set times, counts, scores in Overpass Mono with tabular figures.
- **Do** keep controls at 2px corners and separate regions with seams and 4px rules.
- **Do** give every interactive element a 2px yellow focus outline (offset 2px).

### Don't:
- **Don't** add shadows, glows or lifted hovers; depth is tone and rule only.
- **Don't** fill surfaces with green, amber or red; they are text, outline, dot or rule.
- **Don't** put a bordered panel inside a bordered panel, or build card grids for settings and lists; use rows.
- **Don't** use a centred hero, a dark sidebar with icon-and-label tiles, or rounded pill shapes; the rail is the yellow line of stations.
- **Don't** set sentence copy in uppercase condensed or in mono.
- **Don't** let a coloured line or state colour leak into page chrome.

### Not canonized (defects the build carries)
- Uppercase letter-spaced micro-labels (`.lbl`, field labels, column heads, tag-group names) are functional table/field heads here; they must not be copied as free-standing eyebrow or kicker text above headings on new surfaces.
- Info Blue is declared but effectively unused; not a rule for new work.
- The rail's footer `Go to…` uses a literal ellipsis glyph and `⌘K` text; the only glyph-based affordance, not a model for icons (use inline SVG).
- Raw hex values repeated in the Sort score ramp (`#ff6b5e` through `#5fd38d`) and in `app.js` instead of tokens; drift, not a token.
