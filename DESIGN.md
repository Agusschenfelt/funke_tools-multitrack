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
- **Funke Ballpoint Orange** (`colors.orange`): the active mark. Primary action fill (Exportar pack, Guardar, Subir, Abrir el estudio, play), the playhead, the bracket and edge lines of the active section, the progress fill, the drag-over border, the edge grip while hovered or dragged, the running-job mark, and the wait ruler's current-bar mark. Text on it is `on-orange` ink. Hover and press step to `orange-hover` and `orange-press`.

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
**The Ballpoint Rule.** Orange marks only the active section, the playhead and the primary action, and there is one primary action per moment: while section edits are unsaved, "Exportar pack" steps back to an outline so "Guardar" is the only orange. If something is merely selected, hovered or informational it is paper, graphite or lifted ink. The selected-for-editing section gets a paper outline; the active section gets orange.

**The Warm Ink Rule.** Every neutral leans warm (brown-tinted ink, cream paper). No cool greys, no pure black or white.

## Typography

**Display / UI Font:** Schibsted Grotesk (Latin and Latin-ext, `system-ui` fallback)
**Fact Font:** Courier Prime 400/700 (Courier New fallback), tabular numerals

**Character:** A sturdy grotesque set heavy and uppercase for headings against a typewriter mono that looks typed onto a chord sheet. Spanish glyphs are covered by both.

### Hierarchy
- **Display** (800, `clamp(2rem, 1.2rem + 4.2vw, 3.75rem)`, 1.0, -0.01em, uppercase): the upload page title.
- **Headline** (800, `clamp(1.5rem, 1rem + 2.5vw, 2.5rem)`, 1.1, uppercase): the export page title.
- **Title** (800, 1.25rem, 1.2): the song title in the song bar (dim paper, 600 when it is the "Tema sin título" fallback); 700 for lane names, uppercase and 1.25rem on phone.
- **Body** (400, 1rem, 1.5): prose and controls; button text 600. Lead and hint copy hold a `62ch` measure.
- **Label** (700, 0.875rem, 0.06em, uppercase): section names in the strip. Table headers are 600, 0.75rem, 0.06em, uppercase. Small notes and status are 0.875rem in dim paper.
- **Fact** (Courier Prime, tabular, 0 tracking): key, BPM, meter, bar numbers, section times, bars:beats readout (1.75rem 700), clock, M/S toggle letters, the "revisar" flag, file sizes. On phone the key/BPM/meter readout becomes monumental (2rem, 700, 1.05).

### Named Rules
**The Chord-Sheet Facts Rule.** Mono is for facts a musician reads off a chord sheet: numbers, times, key, BPM, section letters and short flags. Sentences, buttons and headings are never mono.

**The Songbook Heading Rule.** Headings and section/lane labels are uppercase, heavy and lightly tracked; running text stays sentence case.

## Layout

A ruled page. Studio content runs to `90rem`, other pages to `64rem` (`page-width`), with a `1rem` gutter. Spacing is a 4/8/12/16/24/32/48/72px scale and the touch target is `2.75rem`. The song bar is a four-column grid (title, facts, "?" help, Exportar pack); the help panel anchors under it. Under it, the section strip and lanes share a `15rem` head column (names, mute, solo, volume) with the timeline to its right, so bar lines align across strip and lanes. Lanes are `4.5rem` minimum, separated by rule lines, with a 1px centre line like a staff. The transport is fixed to the bottom (7rem desktop, 6.25rem phone, plus safe-area inset) and the page reserves that room; a proportional section minimap sits at its top.

The section editor never pushes the lanes: it opens in a zero-height anchor under the strip, as a one-row overlay on desktop and as a fixed bottom sheet above the transport on phone.

The studio has one toolbar row under the song bar: quick-mix presets on the left; on the right Compases/Tiempo, "Repetir esta sección" and "Descargas"; the loop state follows, and the edit controls (Deshacer, Rehacer, Guardar) join the row only while there is something to edit. The Descargas panel opens in the page flow under the row. The wait screen is a single `44rem` column: title, ruler, stage lines, one fixed-height slot, "Detalle", then the result.

**Phone (below 48rem):** song bar becomes title, "?" and Exportar pack over a monumental facts row; the title wraps and the pencil follows its last word; the presets become a "Mezcla" select and the rest folds into "Más", which opens in the page flow; a reserved 44px row holds the hint "Tocá una sección de arriba para editarla" until edits swap in the controls, so nothing shifts; the help is a bottom sheet above the transport; section chips are at least 56x44 and scroll sideways over the true time axis; the lane head collapses to a one-lane-per-page horizontal scroll-snap feed with a "n / total" pager, uppercase lane name, 44px M/S and volume; the strip sits above, with smaller labels and no drag edges; the transport is one row (play, position, Click, Guías, language) and the total time is hidden; the section editor is a bottom sheet. Coarse pointers get 44px toggles and sliders.

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

### Song bar
The title is a button that looks like the heading: dotted graphite underline and a drawn pencil at rest (touch included), both going to paper on hover. Click opens a text field (80 characters); Enter or blur commits, Escape cancels, empty restores the file's name. The rename lives in this browser only. A generic file name reads "Tema sin título" in dim paper with the duration in mono beside it. Key, BPM and meter follow in mono; the "?" is a 44px outlined mono button. "Exportar pack" is the orange primary; with unsaved edits it becomes a graphite outline in dim text with `aria-disabled`, and pressing it shows the warning notice with "Guardar ahora".

### Help
"Cómo funciona el estudio" is a non-modal raised-ink panel (30rem, graphite border, the sheet shadow) opened by "?" or the `?` key, and closed by Escape, Cerrar, "?" or a press outside; focus returns to the button. Sections: Cada zona, Atajos (keys as mono `kbd` boxes), Gestos, Qué significan las marcas (the legend), Mezclas rápidas. Terms in 600, descriptions in dim paper. Its copy comes from one source (`lib/studio/help`).

### Toolbar and downloads
Segmented group: one graphite-bordered strip, the pressed segment inverts to paper with ink text, "Personalizado" appears (not a button) only when mute/solo no longer match a preset. Small buttons are 2.25rem (44px on coarse pointers), 600, outlined; an open panel's trigger is lifted ink. "Descargas" opens a panel with "Cada pista (WAV sin comprimir)" as outlined download links with a square-cap arrow, "Bajar esta mezcla (WAV)" with its options, and a quiet dim note when the studio loaded a compressed preview (the exported pack keeps full quality). Downloads are secondary; the pack stays in the song bar.

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

### Wait screen
- **Ruler:** the same 12-bar staff reused as the clock (`role=progressbar`, steps done of total). Bars behind the mark turn paper-dim with a 2px floor line; the current bar carries a 4px orange floor mark and a paper bold number, and advances only when a stage completes. While work is live the mark breathes in thickness (scaleY 1 to 1.75, 1.6s), never in opacity, and only under `prefers-reduced-motion: no-preference`. When all is done the right edge closes with a 3px paper double bar.
- **Stage lines:** one row per job (min 4.25rem): square mark (hollow graphite, orange running, paper finished, error failed), uppercase task label, a 700 line of what is happening now, and mono "k/n" steps over elapsed time at the right. Queued lines are dim and regular.
- **Slot:** one fixed-height region holds the duration estimate note, then either the hint, the secondary "Avisarme con una notificación" opt-in, the granted hint, or the orange "Abrir el estudio", which takes focus and fades in only if the person watched the wait. The tab title tracks progress and is restored on leave; a browser notification fires once, only when the tab is hidden.
- **Detalle:** a native disclosure in dim uppercase 0.75rem with a drawn chevron that turns when open, holding the job table.
- **Result fill:** laid out from the start with fixed-height dashes (key, tempo, meter, duration in 4rem mono readouts) so nothing moves; values arrive in place, section chips (graphite outline, 700, `×n` in mono) stamp in one by one at 70ms steps, followed by "Acordes más presentes" in mono joined by middots. Failures stay in error-bordered notices with a retry button.

### Job table
Fixed-column table (task, status, time), hairline row rules, uppercase 0.75rem headers, times right-aligned in mono. Each row has a square 0.5rem mark: hollow graphite when waiting, orange and blinking in steps when running, paper when finished, error when failed (the row text turns error). Updates in place.

### Notices
Bordered 1px in error or warning color with the same text color, 2px corners, copy at a `62ch` measure and an action button on the right.

### Motion
Tokens: `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)`; `--duration-fast: 140ms` for color, background, border and opacity changes; `--duration-draw: 700ms` for the staff drawing in. The running-job tick is a 1.2s stepped blink; the wait ruler mark and stage-line mark breathe over 1.6s (thickness or scale, never opacity); result values arrive in 420ms. Under `prefers-reduced-motion: reduce` all animation and transition durations collapse to 0.01ms. Do not animate layout.

## Do's and Don'ts

### Do:
- **Do** spend orange only on the active section, the playhead and the primary action (The Ballpoint Rule).
- **Do** set bar numbers, times, key, BPM, meter and section letters in Courier Prime with tabular numerals.
- **Do** build separators from 1px `rule` or `graphite` lines and step surfaces ink to raised to lifted.
- **Do** use 2px corners everywhere and 44px minimum targets on interactive controls.
- **Do** use `paper-dim` for secondary text; keep `graphite` for borders, tracks and bar lines.
- **Do** keep the transport fixed and the lanes unmoved when overlays open.
- **Do** write copy in Spanish with voseo.
- **Do** keep one orange action at a time: demote Exportar pack to an outline while Guardar is live.
- **Do** reserve space for states that appear later (edit row, result values, wait slot) so nothing shifts.

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
