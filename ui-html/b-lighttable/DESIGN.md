---
name: Postroom, Light table
description: A picture editor's light table for curating Instagram frames; cool backlit paper, black-framed images, grease-pencil marks.
colors:
  paper: "#eef1f3"
  sheet: "#ffffff"
  sheet-2: "#f6f8f9"
  ink: "#101214"
  ink-2: "#2b3036"
  mute: "#566069"
  rule: "#d3d9de"
  rule-2: "#aab3ba"
  frame-black: "#0b0c0d"
  pick-vermilion: "#e0301a"
  maybe-amber: "#f0b400"
  reject-slate: "#566b80"
  edge-code: "#ffb000"
  ok-green: "#1d8a52"
typography:
  display:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "clamp(30px, 3.6vw, 46px)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "15.5px"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "14.5px"
    fontWeight: 500
    lineHeight: 1.45
  label:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "11.5px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.1em"
  data:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: "tabular-nums"
rounded:
  none: "0"
  full: "50%"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "22px"
  page: "32px"
components:
  button:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "36px"
  button-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.none}"
    padding: "0 24px"
    height: "44px"
  tab-current:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
    padding: "0 16px"
  tag:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    padding: "0 10px"
    height: "28px"
  tag-on:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
  input:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0 10px"
    height: "36px"
  frame:
    backgroundColor: "{colors.frame-black}"
    padding: "8px 8px 22px"
  decide-keep:
    backgroundColor: "{colors.pick-vermilion}"
    textColor: "{colors.sheet}"
    height: "62px"
---

# Design System: Postroom, Light table

## Overview

**Creative North Star: "The Light Table"**

Images lie on a bright, cool, backlit surface and decisions are made by marking them. The ground is cool paper-white, every image sits in a black frame like a contact-sheet negative, and the owner's judgement shows up as grease-pencil marks drawn over the frame rather than as verb buttons. It is a light, dense, squared-off working surface for one owner on one Mac.

Chrome is ink-on-white with hard 1-2px black borders; colour is reserved almost entirely for the three decision marks (pick, maybe, reject) and for the amber edge codes on frames. Type is a modern grotesque at heavy weights for headings, with a mono for frame numbers, counts, times and edge codes.

**Key Characteristics:**
- Cool paper ground, pure-white sheets, ink-black borders; corners are square everywhere except status dots and the grease-pencil marks.
- Every image lives in a near-black frame with a mono edge-code strip beneath it.
- Decision colour is semantic and rare: vermilion pick, amber maybe, slate reject.
- Active state is always inversion to solid ink with white text.
- One paper-lift shadow; otherwise depth comes from borders and layering.

## Colors

A near-monochrome cool-grey and ink palette where the only saturated hues are decision marks.

### Primary
- **Grease-Pencil Vermilion** (pick-vermilion): the "keep" mark, picked-frame circle, Lightbox count, focus ring, the selected-facet underline, and the Keep decision button.

### Secondary
- **Maybe Amber** (maybe-amber): the "maybe/review" mark (dashed or solid circle), review tab underline, warning status dot, outlier badges.
- **Reject Slate** (reject-slate): the "reject/junk" X and ring, danger buttons, bad status dots. Rejects read as cooled-off, not alarming.

### Tertiary
- **Edge-Code Amber** (edge-code): film-edge codes and version badges printed on frame black only; not used on white.
- **Confirm Green** (ok-green): only the "all good" status dot and completed-job ring.

### Neutral
- **Light-Table Paper** (paper): page ground, with a faint white radial glow at the top; also command-field fill.
- **Sheet White** (sheet): bars, cards, popovers, sheets, inputs.
- **Sheet Tint** (sheet-2): hover and sub-surface fill, kbd, log wells.
- **Ink** (ink): text, 1-2px borders, selected/hover inversion fill. **Ink 2** (ink-2) is secondary ink.
- **Mute** (mute): secondary text, labels. **Rule** (rule) hairline dividers; **Rule 2** (rule-2) control borders and slider tracks.
- **Frame Black** (frame-black): image frames, Lightbox cells, filmstrip, triage viewer.

### Named Rules
**The Marks-Only Colour Rule.** Saturated colour means a decision (pick, maybe, reject) or a status. Never use vermilion, amber or slate as decoration or as a generic accent.
**The Ink Inversion Rule.** Hover, selected, pressed and current states invert to ink fill with white text; they do not tint.

## Typography

**Display Font:** Schibsted Grotesk (system-ui, sans-serif), self-hosted 400-800.
**Body Font:** Schibsted Grotesk.
**Label/Mono Font:** JetBrains Mono (ui-monospace), self-hosted 400/500/700.

**Character:** A tight, heavy grotesque with negative tracking for headings, paired with a tabular mono that reads as film-edge printing. Hierarchy comes from weight (800 vs 500) and size, not colour.

### Hierarchy
- **Display** (800, clamp(30px, 3.6vw, 46px), 1, -0.04em): page titles (`h-page`); a compact variant clamps 26-34px.
- **Headline** (800, 22-26px, 1.1, -0.03em): section, sheet and dialog titles; Lightbox heading 24px; empty states 24px.
- **Title** (700, 15.5px, 1.25): row titles, job titles, tabs at 15px/700, tab bar 17px/800.
- **Body** (500, 14.5px, 1.45): default text; hints 13.5px mute; sub-copy capped at 62ch.
- **Label** (700, 11.5px, 0.1em, uppercase): form field captions, facet group heads and table headers only.
- **Data** (JetBrains Mono, 11-13px, tabular-nums): counts, frame numbers, durations, times, edge codes, kbd; big clip times 18px/700; query field 21px/600 Schibsted.

### Named Rules
**The Numbers Are Mono Rule.** Any count, time, score or frame number is JetBrains Mono with tabular figures.
**The Heavy-Tight Rule.** Headings are 800 weight with negative letter-spacing (-0.03 to -0.04em); never light weights.

## Layout

A sticky 60px top bar (brand, five tabs, command field, model switch, status, activity, Lightbox toggle) over a two-column grid: content (`minmax(0,1fr)`, padding 26px 32px, max 1320px centered) and a 308px Lightbox tray on the right that collapses to 0 via grid transition. Contact sheets use `repeat(auto-fill, minmax(188px, 1fr))` with 22px/16px gaps; frames are 4:5. Library is a 290px sticky facet column plus content; Videos a 250px sticky position column plus rows; Triage a 1.1fr/0.9fr viewer/controls split. Spacing is a 4/6/8/12/16/22/32px rhythm. At 1180px the splits stack; at 1000px the top bar wraps to 112px with tabs on their own row; at 900px the Lightbox becomes a fixed overlay. Slide-over sheets (760px) and dialogs (640px) layer over the work with a 45% ink scrim. Reduced motion disables all animation, leaving marks fully drawn.

## Elevation & Depth

Flat and bordered. Depth is conveyed by 1px hairlines, 2px ink borders on structural edges (top bar, Lightbox, sheet headers, query bar), and white-on-paper layering.

### Shadow Vocabulary
- **Paper Lift** (`0 1px 0 rgba(16,18,20,0.06), 0 8px 24px -12px rgba(16,18,20,0.22)`): query bar, triage viewer, dialogs; popovers and the palette add a larger soft ambient shadow on top.
- **Pressed Underline** (`inset 0 -3px 0 ink`): open filter pill.
- **Input Focus** (`0 0 0 3px rgba(16,18,20,0.12)` plus ink border).

### Named Rules
**The One Lift Rule.** The only shadow is the soft paper lift, used for things that float above the sheet. No hard offset shadows, no glow.

## Shapes

Square by default (radius 0) on buttons, inputs, tags, cards, frames, sheets. Circles are reserved for status dots, spinners, range thumbs and the grease-pencil marks. Borders are 1px (controls, rows) or 2px (structure, tab bars, dialogs). Images are cropped with `object-fit: cover` in black frames with 8px padding and 22px bottom edge strip.

## Components

### Buttons
- **Shape:** square, 1px ink border; 36px high (small 30, primary 44, icon 32).
- **Default:** white fill, ink text, 700 weight, 14px.
- **Hover / Focus:** inverts to ink fill, white text. Focus ring is 3px vermilion outline with 2px offset on every focusable.
- **Primary:** solid ink, 44px, 15.5px text. **Ghost:** rule-2 border, 600 weight. **Danger:** reject-slate text and border.

### Chips (tags, tokens, pills)
- **Tag:** white, rule-2 border, 28px; selected inverts to ink with 700 weight; suggestion tags use a dashed border and mute text.
- **Token:** solid ink chip with 20px thumbnail, used inside the query bar.
- **Pill:** 34px filter trigger with mono value; open state gets a 3px ink bottom bar.

### Cards / Containers
White sheets with 1px rule borders, square corners, 12-16px padding. Video rows gain an ink border on hover.

### Inputs / Fields
- **Style:** white fill, 1px rule-2 border, 36px, square.
- **Focus:** border to ink plus a 12% ink 3px halo. The query bar is a 2px ink-bordered, paper-lifted field with 21px/600 type and a 35% vermilion focus-within outline.
- **Switches:** 36x20 square track with square knob, ink when on.

### Navigation
Top tabs are 15px/700 mute text, full bar height; hover tints to sheet-2; current inverts to ink with white text. Each tab carries a bordered kbd shortcut. Sub-tabs use an 800-weight tab bar with a 5px bottom border in the decision colour.

### Contact-sheet Frame (signature)
Near-black frame with 8px padding, 4:5 image, and a mono amber edge-code strip (frame number left, meta right) at the bottom. A black-on-amber version badge sits top-left; hover tools appear top-right. Under the frame: bold name and mono meta.

### Grease-Pencil Mark (signature)
An SVG hand-drawn ellipse stroke (3.2-3.6px, round caps) drawn over a frame with a 0.5s stroke-dash draw-in, once. Pick is vermilion solid; maybe is amber; reject is a slate X (5px) or pale slate stroke on dark; the badge variants (ink, dashed amber, slate) reuse the same mark family at 34px.

### Lightbox
A 308px white tray with a 2px ink left border, 24px/800 heading with a mono vermilion count, a 3-column grid of 4:5 black cells (remove button on hover), and a foot action row.

### Activity, Popovers, Sheets, Palette
Popovers and the command palette are white with 2px ink border and the paper lift; list rows invert to ink on hover/selection. Activity jobs show a ring marker (green done, spinning ink busy, slate failed). Motion uses one easing, `cubic-bezier(0.22, 1, 0.36, 1)`, at 0.2-0.35s for pop, fade and slide.

### Data (tables, meters, timelines)
Tables have mute uppercase headers on a 2px ink rule and mono right-aligned numbers. Timelines and zone meters are 18-24px bars with 2px ink borders and ink separators; meters at 6-8px use ink or semantic fills.

## Do's and Don'ts

### Do:
- **Do** put every image in a frame-black frame with an edge-code strip.
- **Do** express keep, maybe and reject with the grease-pencil mark family in vermilion, amber and slate.
- **Do** invert hover and selected states to ink fill with white text.
- **Do** set every number, time and count in JetBrains Mono with tabular figures.
- **Do** keep corners square and borders 1px (controls) or 2px (structure).
- **Do** keep a visible 3px vermilion focus outline.

### Don't:
- **Don't** use dark sidebar dashboards or dark page grounds; the table is light, only frames are dark.
- **Don't** use vermilion, amber or slate for decoration or non-decision accents.
- **Don't** add shadows beyond the paper lift, or any hard offset shadow.
- **Don't** round buttons, inputs or cards.
- **Don't** replace decision marks with verb-only coloured buttons.

## Not canonized
Defects and drift the build carries, not rules: tracked-uppercase `.lbl` is also used as ad hoc section captions ("Try", "When", "Videos", "Carousels") where it reads as an eyebrow; new surfaces should use it only for form fields, facet group heads and table headers. Off-token literals (#2f353b, #d8dde1, #9fb3c6, #5d6770, #151617, #222) are one-off values and are not part of the palette.
