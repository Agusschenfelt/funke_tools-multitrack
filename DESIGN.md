---
name: Multitrack
description: A dark studio that reads like a page of the band's chord songbook; one orange ballpoint mark for what is active.
colors:
  ink: "#141210"
  ink-raised: "#1c1a17"
  ink-lifted: "#272420"
  paper: "#ede6da"
  paper-dim: "#a59e92"
  graphite: "#6f6a63"
  rule: "#38342f"
  orange: "#fd5609"
  orange-hover: "#ff6f2b"
  orange-press: "#e24a03"
  on-orange: "#141210"
  error: "#f08b7c"
  warning: "#e3b54f"
typography:
  display:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "clamp(2rem, 1.2rem + 4.2vw, 3.75rem)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "clamp(1.5rem, 1rem + 2.5vw, 2.5rem)"
    fontWeight: 800
    lineHeight: 1.1
  title:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 800
    lineHeight: 1.2
  body:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Schibsted Grotesk, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 700
    letterSpacing: "0.06em"
  fact:
    fontFamily: "Courier Prime, Courier New, monospace"
    fontSize: "1.25rem"
    fontWeight: 400
    letterSpacing: "0"
    fontFeature: "tnum"
  fact-monumental:
    fontFamily: "Courier Prime, Courier New, monospace"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.05
rounded:
  base: "2px"
spacing:
  space-1: "4px"
  space-2: "8px"
  space-3: "12px"
  space-4: "16px"
  space-5: "24px"
  space-6: "32px"
  space-7: "48px"
  space-8: "72px"
  touch: "44px"
components:
  button-primary:
    backgroundColor: "{colors.orange}"
    textColor: "{colors.on-orange}"
    rounded: "{rounded.base}"
    height: "{spacing.touch}"
    padding: "0 24px"
  button-primary-hover:
    backgroundColor: "{colors.orange-hover}"
  button-primary-active:
    backgroundColor: "{colors.orange-press}"
  button-primary-disabled:
    backgroundColor: "{colors.ink-lifted}"
    textColor: "{colors.paper-dim}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.paper}"
    rounded: "{rounded.base}"
    height: "{spacing.touch}"
    padding: "0 16px"
  button-secondary-hover:
    backgroundColor: "{colors.ink-lifted}"
  toggle-pressed:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
  field:
    backgroundColor: "{colors.ink-raised}"
    textColor: "{colors.paper}"
    rounded: "{rounded.base}"
    height: "{spacing.touch}"
    padding: "0 12px"
  transport:
    backgroundColor: "{colors.ink-raised}"
    textColor: "{colors.paper}"
  drop-zone:
    backgroundColor: "{colors.ink-raised}"
    rounded: "{rounded.base}"
    padding: "32px"
  drop-zone-dragging:
    backgroundColor: "{colors.ink-lifted}"
  section-tip:
    backgroundColor: "{colors.orange}"
    textColor: "{colors.on-orange}"
---

# Design System: Multitrack

## Overview

**Creative North Star: "The Songbook Page"**

The song is drawn the way a band's handwritten chord songbook draws it: named sections in uppercase, bars numbered along a ruled line, repeats marked with repeat signs. The ground is warm ink, the text is cream paper, structure is hairline rules, and a single orange ballpoint mark says "this is where we are" or "this is what to press". It is a dark rehearsal-room tool for bands and producers, used on a laptop and on a phone at the rehearsal.

Density is operational: lanes, section strip and a fixed transport are always on screen; nothing is decorative. Depth comes from stepping the ink ground up in lightness and from 1px rules, not from shadows. Typography does the personality: a sturdy grotesque with uppercase headings for the songbook voice, and a typewriter mono reserved for the facts of a chord sheet.

**Key Characteristics:**
- Warm ink ground (not neutral grey), cream paper text, hairline rules.
- One accent, orange, spent on the active section, the playhead and the primary action only.
- Typewriter mono for chord-sheet facts; grotesque for everything else.
- 2px corners, 1px rules, flat surfaces.
- 44px touch targets; phone layout is a vertical feed with a monumental key/BPM readout.

## Colors

A restrained dark palette of one warm ink family, one cream paper family and one orange; two state colors appear only when a state carries meaning.

### Primary
- **Funke Ballpoint Orange** (`colors.orange`): the active mark. Primary action fill (Exportar, Guardar, Subir, play), the playhead, the bracket and edge lines of the active section, the progress fill, the drag-over border, the edge grip while hovered or dragged, and the running-job tick. Text on it is `on-orange` ink. Hover and press step to `orange-hover` and `orange-press`.

### Neutral
- **Ink** (`colors.ink`): page ground, minimap track, and the browser theme color.
- **Raised Ink** (`colors.ink-raised`): transport, section editor sheet, drop zone, fields, hover on the section strip, selected section.
- **Lifted Ink** (`colors.ink-lifted`): hover fill on ghost buttons, disabled primary, active-section span in the minimap, dragging drop zone.
- **Paper** (`colors.paper`): body text, pressed toggle fill, focus ring, the selected-section outline.
- **Dim Paper** (`colors.paper-dim`): secondary text, waveform stroke, bar numbers, clocks, hints. The only secondary text color that clears 4.5:1.
- **Graphite** (`colors.graphite`): control borders, bar lines, section edges, slider tracks. 3.4:1 on ink, so large or decorative marks and borders only, never text.
- **Rule** (`colors.rule`): hairline dividers, lane separators, the lane centre line, repeat lines.

### State
- **Error Salmon** (`colors.error`): failed upload or job, error notices (1px border plus text).
- **Warning Amber** (`colors.warning`): the "revisar" flag on a weakly detected section label, and the hold notice. Text-sized and small; it collapses to a dot in narrow sections.

### Named Rules
**The Ballpoint Rule.** Orange marks only the active section, the playhead and the primary action. If something is merely selected, hovered or informational it is paper, graphite or lifted ink. The selected-for-editing section gets a paper outline; the active section gets orange.

**The Warm Ink Rule.** Every neutral leans warm (brown-tinted ink, cream paper). No cool greys, no pure black or white.

## Typography

**Display / UI Font:** Schibsted Grotesk (Latin and Latin-ext, `system-ui` fallback)
**Fact Font:** Courier Prime 400/700 (Courier New fallback), tabular numerals

**Character:** A sturdy grotesque set heavy and uppercase for headings against a typewriter mono that looks typed onto a chord sheet. Spanish glyphs are covered by both.

### Hierarchy
- **Display** (800, `clamp(2rem, 1.2rem + 4.2vw, 3.75rem)`, 1.0, -0.01em, uppercase): the upload page title.
- **Headline** (800, `clamp(1.5rem, 1rem + 2.5vw, 2.5rem)`, 1.1, uppercase): the export page title.
- **Title** (800, 1.25rem, 1.2): the song title in the song bar; 700 for lane names, uppercase and 1.25rem on phone.
- **Body** (400, 1rem, 1.5): prose and controls; button text 600. Lead and hint copy hold a `62ch` measure.
- **Label** (700, 0.875rem, 0.06em, uppercase): section names in the strip. Table headers are 600, 0.75rem, 0.06em, uppercase. Small notes and status are 0.875rem in dim paper.
- **Fact** (Courier Prime, tabular, 0 tracking): key, BPM, meter, bar numbers, section times, bars:beats readout (1.75rem 700), clock, M/S toggle letters, the "revisar" flag, file sizes. On phone the key/BPM/meter readout becomes monumental (2rem, 700, 1.05).

### Named Rules
**The Chord-Sheet Facts Rule.** Mono is for facts a musician reads off a chord sheet: numbers, times, key, BPM, section letters and short flags. Sentences, buttons and headings are never mono.

**The Songbook Heading Rule.** Headings and section/lane labels are uppercase, heavy and lightly tracked; running text stays sentence case.

## Layout

A ruled page. Studio content runs to `90rem`, other pages to `64rem` (`page-width`), with a `1rem` gutter. Spacing is a 4/8/12/16/24/32/48/72px scale and the touch target is `2.75rem`. The song bar is a three-column grid (title, facts, export). Under it, the section strip and lanes share a `15rem` head column (names, mute, solo, volume) with the timeline to its right, so bar lines align across strip and lanes. Lanes are `4.5rem` minimum, separated by rule lines, with a 1px centre line like a staff. The transport is fixed to the bottom (7rem desktop, 6.25rem phone, plus safe-area inset) and the page reserves that room; a proportional section minimap sits at its top.

The section editor never pushes the lanes: it opens in a zero-height anchor under the strip, as a one-row overlay on desktop and as a fixed bottom sheet above the transport on phone.

**Phone (below 48rem):** song bar becomes title and Exportar over a monumental facts row; the lane head collapses to a one-lane-per-page horizontal scroll-snap feed with a "n / total" pager, uppercase lane name, 44px M/S and volume; the strip sits above, with smaller labels and no drag edges; the transport is one row (play, position, Click, Guías, language) and the total time is hidden; the editor hint folds into a "Cómo se editan" disclosure. Coarse pointers get 44px toggles and sliders.

## Elevation & Depth

Flat by default. Depth is tonal (ink, raised, lifted) plus 1px rules. The one exception is the section editor sheet, which floats over the lanes and carries a soft black drop shadow to separate it from the waveforms below.

### Shadow Vocabulary
- **Sheet lift** (`box-shadow: 0 0.5rem 1rem rgb(0 0 0 / 0.4)`; inverted on the phone bottom sheet): the section editor only.

### Named Rules
**The Tonal Step Rule.** Raise a surface by stepping to the next ink tone and drawing a rule, not by adding a shadow. Shadows are for surfaces that overlay content.

## Shapes

Almost square. Everything is `2px` (`rounded.base`): buttons, fields, notices, drop zone, slider thumbs. Rectangles bounded by hairlines, bar lines and brackets are the recurring form. The only circles are the small status dots (the warning dot in narrow sections). The active section is bounded by two 1px orange edge lines on the waveforms and a 2px orange bracket on top of the strip, never filled.

## Components

### Buttons
- **Primary:** orange fill, ink text, 600, 44px tall, `0 24px` padding, 2px corners. Hover lightens, press darkens, disabled falls back to lifted ink with dim text. One per view region: Exportar, Guardar, upload, and the 3.25rem square play button.
- **Secondary / ghost:** transparent, 1px graphite border (paper on hover in the upload view, lifted-ink fill elsewhere), 600, 44px tall. Used for Deshacer, Rehacer, Cerrar, section tools.
- **Toggle:** ghost; pressed state inverts to a paper fill with ink text (Click, Guías, M, S). Pressed is paper, never orange.

### Fields
Raised ink fill, 1px graphite border, 2px corners, 44px tall (3.25rem on phone), paper text. Language and section selects share the style. Focus is the global 2px paper outline at 3px offset.

### Section strip
Uppercase labels at each section's left edge behind a 1px graphite bar line, with repeat signs and times in dim mono, bar numbers on a ruled row beneath. Hover raises to raised ink. Active gets the orange bracket; selected for editing gets raised ink with a 1px paper outline. Drag edges (desktop, fine pointer) show an orange grip and an orange tooltip with the new boundary while hovered or dragged.

### Lanes and waveform
Name (700) with M and S square toggles and a hairline volume slider (2px track, paper 2px-corner thumb). The waveform is a dim-paper canvas on the lane's centre line; non-audible lanes drop to 0.28 opacity. The playhead is a 2px orange vertical line across all lanes.

### Transport
Raised ink, rule on top. Play (orange), position as bars:beats in mono 1.75rem 700 ("CUENTA" word in uppercase during count-in), clock in dim mono, toggles at the right.

### Upload drop zone and bar progress
Raised ink panel with a rule border; drag-over switches border to orange and the fill to lifted ink. Progress is drawn as a 12-bar staff with numbered bars in dim mono and a 4px orange fill; the staff draws in left to right on mount.

### Job table
Fixed-column table (task, status, time), hairline row rules, uppercase 0.75rem headers, times right-aligned in mono. Each row has a square 0.5rem mark: hollow graphite when waiting, orange and blinking in steps when running, paper when finished, error when failed (the row text turns error). Updates in place.

### Notices
Bordered 1px in error or warning color with the same text color, 2px corners, copy at a `62ch` measure and an action button on the right.

### Motion
Tokens: `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)`; `--duration-fast: 140ms` for color, background, border and opacity changes; `--duration-draw: 700ms` for the staff drawing in. The running-job tick is a 1.2s stepped blink. Under `prefers-reduced-motion: reduce` all animation and transition durations collapse to 0.01ms. Do not animate layout.

## Do's and Don'ts

### Do:
- **Do** spend orange only on the active section, the playhead and the primary action (The Ballpoint Rule).
- **Do** set bar numbers, times, key, BPM, meter and section letters in Courier Prime with tabular numerals.
- **Do** build separators from 1px `rule` or `graphite` lines and step surfaces ink to raised to lifted.
- **Do** use 2px corners everywhere and 44px minimum targets on interactive controls.
- **Do** use `paper-dim` for secondary text; keep `graphite` for borders, tracks and bar lines.
- **Do** keep the transport fixed and the lanes unmoved when overlays open.
- **Do** write copy in Spanish with voseo.

### Don't:
- **Don't** use orange for selection, hover, pressed toggles, links or decoration.
- **Don't** set text in graphite (3.4:1 on ink).
- **Don't** use cool greys, pure black or pure white.
- **Don't** set sentences, buttons or headings in the mono face.
- **Don't** add rounded cards, large radii, or glow and shadow to resting surfaces.
- **Don't** fill the active section; bound it with lines and the bracket.
- **Don't** let a state color (error, warning) stand without its words or its row context.

## Not canonized

The review captures show the Next.js dev-tools badge (a round "N") at the bottom-left over the transport; it is a development overlay, not part of the system. In the studio capture the song title can render as a single letter ("t") from test data, which is content, not a style rule.
