# Merging a reviewed transcription onto measured word boxes

**Status:** proposal, awaiting Daniel's review
**Date:** 2026-08-28
**Raised by:** Daniel — "is there no way to merge the word regions so that a
transcription review can have its words tied to the best word region we have?"

## The problem

Two artifacts describe the same page and disagree:

- `regions` (Apple Vision): **measured** word and line boxes, with the text
  Vision *thought* it read — on a 1799 Popayán hand, largely wrong.
- `transcription_review`: the **correct** text, with no geometry at all.

So the page has accurate words with no positions, and accurate positions
labelled with inaccurate words. Neither alone lets a reader click a word in
the transcript and see it on the image.

## Why this is tractable here

`OCRGeometryBox` already carries `char_start`/`char_end` indexing into its own
artifact's text, and `attach_char_spans` establishes that link for producers
that do not build it natively. Boxes are therefore already addressable by
character range.

The merge is consequently NOT a new geometry system. It is **one
string-to-string alignment**: map character offsets in the reviewed text onto
character offsets in the regions text. Every reviewed word's range then
resolves through that map to boxes the existing code already finds.

## Algorithm: lines first, then words

**Tier 1 — lines.** Word-level matching against garbled OCR fails, but line
*structure* is far more stable than line *content*: Vision produced roughly
the right number of lines in the right vertical order even where it read
`mstruia` for `instruia`. Align reviewed lines to Vision line boxes on
textual similarity AND ordinal position. Vertical order is monotonic, so
alignments cannot cross — a strong constraint that survives bad text.

**Tier 2 — words within a matched line.** The search space collapses from the
page to a dozen words. Where Vision's text is usable, character-level
alignment maps reviewed words to word boxes directly. Where it is not,
distribute reviewed words across the line box proportionally to their
character length.

## Provenance is mandatory, not a nicety

Every merged box records how it was obtained:

| Provenance | Meaning |
|---|---|
| `measured` | matched a real Vision word box |
| `derived` | interpolated inside a matched line |
| `unknown` | no confident anchor; no box emitted |

On the Popayán page, `Popayan`, `Don`, the dates and the numerals are strong
anchors and merge as `measured`; the heavily abbreviated stretches will mostly
be `derived`. Presenting a derived box as measured is an unverified claim
about where a word sits — the same failure the VLM orphan-rejection guard
already refuses, and worse here because it would look authoritative.

## Where it breaks, and what to do about it

If Vision's line segmentation is wrong — two columns merged, a rúbrica read as
a line — the skeleton is wrong and everything derived from it inherits the
error. Detectable: line-count mismatch beyond a threshold, or an alignment
score below a floor. The response is to REFUSE the merge for that page and say
so, rather than emit confident nonsense.

## Shape

A `merge_geometry` tool taking a `regions` artifact and a
`transcription_review` artifact, emitting a new geometry artifact with
per-box provenance. Fits the existing tool model; it is the missing piece that
would make reviewed text clickable on the page.

## Open questions

1. Which artifact wins when several reviews exist — newest, or user-chosen?
2. Does the merged geometry replace the page's overlay source, or sit beside
   it as a third choice in `OCRGeometrySelection`'s ladder?
3. Is a page-level "merge confidence" worth surfacing in the Inspector?

---

# Addendum: naming the review passes (2026-08-28)

**Daniel:** "for transcription review could they not have different names so we
know the final review more easily?"

Three `transcription_review` artifacts save with `step_name` `r1`, `r2`, `r3`
and are indistinguishable in the artifact list — while the preset has already
named the nodes "Review 1 — Abbreviations & Formulary", "Review 2 —
Orthography & Consistency", "Review 3 — Final Layer".

**Attempted and reverted:** making `step_name` the node LABEL. It is the wrong
fix. `step_name` is an IDENTIFIER, not a display string: `GET
/api/documents/{id}/artifacts?step_name=…` filters on it, artifacts group by
it, and four tests pin id values. Renaming a node would silently break every
saved query and grouping — a display problem paid for with an identity bug.

**The right fix**, unbuilt: the run already persists the FULL node shape in its
workflow snapshot (#4314), labels included. So the artifact list can resolve
`step_name` → that run's node label for DISPLAY, leaving the stored identifier
alone. Client-side, no schema change, no contract break.

Falls to the Inspector's artifact rows and the Activity trace, wherever a step
is currently shown as `r1`.

---

## Update 2026-09-03 — the trust check asked the wrong question

Measured on six real Marshall diary pages with known transcripts, this merge
REFUSED five of them. Every one of those five aligns line-for-line correctly;
the refusals came from the symmetric line-count guard, which reads a page where
Vision reports more lines than the transcript has as a broken skeleton. On a
printed diary that is the ordinary case — the page carries preprinted day
headers, folio numbers and ruled-line fragments that no transcript transcribes,
and the monotonic alignment already skips them.

The guard is now directional (only reviewed ≫ measured is a defect), and its
accidental catch — a printed calendar whose short numeric lines filled their
coverage with matches at the low `MIN_LINE_SCORE` floor and produced a
scattered overlay — is caught deliberately instead, by a strong-match floor:
at least half the reviewed lines must pair at ≥ 0.60 similarity. Five of six
pages now merge, every word box landing on real ink; the calendar still
refuses, with an accurate reason.

Numbers, overlays and the alignment inspection: `vision-region-experiments.md`.
