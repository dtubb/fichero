# Reading as work: checks, margin notes, coding, and comparison

**Status:** ruled by Daniel 2026-08-30 (evening, live-testing stream).
First cut of items 1 and 7 implemented same day; the rest are designed
lanes. Reference points he named: Marked (the Mac markdown previewer that
SHOWS what's highlighted in a reader view), qualitative coding practice.

## The rulings (paraphrased)

1. **Check-mark tool** (especially iPad): click (or draw) in a page's left
   or right margin to CHECK the adjacent paragraph/line — once, twice, or
   three times ("so I know to come back to it"). Checks are a reading
   discipline, not decoration.
2. **Word-boundary marquee tool**: select words (not pixels) to delete
   region boxes easily, or to add them — a second word-aware tool beside
   the free marquee.
3. **Margin writing**: put SMALL TEXT directly in the margin (not a square
   box) — "in our case it would be like an audio note, transcribed."
4. **A coding system in markup**: any highlight / check / tag can be
   CODED — highlight then tag it; a tag, a highlight, or a triple-check
   carries a code. (The Annotation model already has `tags: [String]` —
   the missing part is UI + querying.)
5. **See annotations somewhere**: a reader/library view that shows what is
   highlighted/checked/noted, cited properly to its page — the Marked
   idea: a review surface over the markup, not just marks on pages.
6. **Workflow bar: compare**: "compare — run the selection's workflow with
   ALL models" as first-class grammar; the outputs land in a reader
   compare view with a labeled diff.
7. **Workflow bar: user context**: a system-prompt slot at the start of
   the bar — "this is a historical diary" — travels with every step's
   prompt so the model knows what it is looking at.

## Built 2026-08-30 (first cut)

- **#7 context**: the bar's sentence gains a leading "about [context]"
  token; the text persists per window (SceneStorage), rides the run as
  `user_context`, and the engine's LLM/vision bases prepend it to every
  step's prompt as "Context from the user: …". Empty = absent.
- **#1 checks**: a ✓ tool in the annotation bar (sticky mode like the
  others). A click on the canvas snaps to the nearest LINE box (margin
  clicks included — nearest line at that height) and saves a
  `kind=rating` annotation (`rating` 1). Clicking an already-checked line
  cycles ✓→✓✓→✓✓✓→clear (rating 1‑3, then delete). Renders through the
  existing saved-boxes layer for now (per-kind glyph rendering is lane
  work, below).

## Lanes to dispatch (in rough order)

- **Annotation review surface (#5)**: `/view/document?representation=annotations`
  — the one WebKit renderer lists highlights/checks/notes/tags grouped by
  page with page citations, colors, and jump-to-page. Library-side: an
  "Annotated" filter and a per-row badge count.
- **Compare grammar (#6)**: bar chip "Compare models…" fans one step out
  over the configured models (the engine already runs per-model steps);
  results tagged `compare_group` + model name; reader gains a compare
  representation (columns per model, diff highlighting, labeled).
- **Margin notes (#3)**: small-text margin rendering for `kind=note`
  annotations anchored in margin space; audio-note capture that
  transcribes into one (the capture machinery exists on iOS).
- **Word-boundary marquee (#2)**: a marquee variant that selects WORD
  boxes (AnnotationWordSnap is the substrate) feeding region
  delete/add — the same seam the region verbs use.
- **Coding UI (#4)**: tag entry on the highlight split-button menu +
  annotation rows; tags become facets in the review surface and library
  filters.
- **Per-kind rendering**: lines as lines, underline under the word,
  strikethrough through it, checks as margin glyphs.
