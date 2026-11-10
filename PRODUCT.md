# Product

## Platform

web

## Stack

Next.js in `apps/web` (from the project brief, confirmed by the user 2026-10-26). Backend is the FastAPI
service in `apps/api`; audio processing runs in RQ workers. Deployed with Docker Compose on a VPS behind Caddy (see `infra/prod/README.md`).

## Users

- Live bands and gigging musicians preparing a song for the show: they need multitracks with click, spoken
  guide cues and a split track, named for Playback, Prime or a DAW.
- Producers who remix or study a song: stems, key, tempo, sections.
- Both use it at a desk and on a phone during rehearsal.

## Product Purpose

A free web tool that takes any song and returns what a musician needs to play it live or remix it: stems,
analysis (tempo grid, key, sections, loudness) and ready-to-import packs. The result is not a download
button but a studio in the browser where the user listens, corrects and only then exports. Success: a band
loads the exported Stage Pack into their playback software and it lines up sample-exact with no fixing.

## Positioning

Spanish-first and free per song, built by the design agency funke as part of a series of tools for artists.
Packs are sample-aligned (every file the same length, count-in included) and named for the destination
software, with spoken cues in Spanish. Code is open source (AGPL); no ads or sponsors.

## Operating Context

- Upload a file, wait in a queue while analysis and separation run (separation takes minutes), then work in
  the browser: mixer per stem, section editor, export.
- Rehearsal rooms: phone in hand, loud environment, quick glances, touch targets.
- Destinations: Playback (MultiTracks.com), Prime (Loop Community), Ableton/Logic/Reaper.
- Files expire after 24 h; there is no public gallery and no account.

## Capabilities and Constraints

- Available backend capabilities: upload with hash reuse, analyze (+ automatic sections), separate
  (htdemucs_6s / htdemucs_ft), edit sections, Stage Pack export (destination playback|daw, count-in 1-2 bars,
  click sound classic|cowbell|woodblock|rimshot, eighth subdivision, straight grid, 44.1/48 kHz, include
  vocals, cue language es|en), signed downloads.
- Section labels are heuristic suggestions with a confidence value; the editor exists to correct them.
- Separation on CPU is slow (minutes per song); progress and queue position must be visible.
- Prime destination is not available yet (pending a real import test).
- Rights notice required on every upload screen: the tool separates audio and grants no rights.
- Out of MVP: grid editor, pitch/tempo, piano roll, score, chords/lyrics, setlists, Producer Pack.

## Brand Commitments

- Agency: funke (funke.cc, Instagram bio "Hacemos ke funke").
- Logo: jagged hand-lettered "funke" wordmark with ®. Primary version is the orange one (#FD5609);
  white and black versions exist. Source files are in the Funke brand kit (not in this repo); exported rasters live in
  `apps/web/public/brand/`.
- Dark mode by default (brief).
- UI copy in Spanish (Rioplatense, voseo); pack file names follow the destination.

## Evidence on Hand

- Working backend and an end-to-end smoke test that produces a real Stage Pack ZIP.
- No testimonials, user counts, press or real-song accuracy numbers exist yet; do not fabricate them.

## Product Principles

1. Trust before export: the user hears and sees the result (stems, click, cues, sections) before downloading.
2. Sample-exact or nothing: alignment and naming are the product; never hide a misalignment risk.
3. Honest about machines: show confidence and limits (bleed, heuristic labels, slow separation) plainly.
4. Rehearsal-ready: every core action works one-handed on a phone.

## Accessibility & Inclusion

Usable on phones with touch targets and in loud, dim rehearsal rooms; keyboard operable on desktop.
