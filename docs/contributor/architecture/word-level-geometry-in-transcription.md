# Word-level bounding boxes in transcription

**Status: audit + open decision. Written 2026-08-05 for Daniel. No code changed
by this document.**

Daniel asked for transcription to save word-level bounding boxes, suspecting the
LLMs can produce them. Most of that is already built. This records what exists,
what is verified, and the one decision that is his to make.

## What already exists and works

The geometry contract is `fichero_server/media/ocr_geometry.py`.

- `OCRGeometryBox` carries `text`, `bbox` as normalised `[x, y, width, height]`
  in `0..1` with a top-left origin, a `level` enum that already includes
  `word`, an optional `confidence`, `char_start`/`char_end` spans into the
  owning artifact's content string, `page_index`, and provenance
  (`provider`, `model`, `coordinate_space`, `source`).
- Its validator **raises** on a wrong-length bbox, negative width or height, any
  coordinate outside `0..1`, or a box extending past the page bound. Malformed
  geometry is rejected at construction, not stored and rendered later in the
  wrong place. Daniel's "reject loudly rather than store garbage" requirement is
  the existing behaviour, not something to add.
- `GEOMETRY_STATUS_KEY` / `GEOMETRY_REASON_KEY` exist precisely so an empty box
  list says *why* it is empty. An unboxed page and a blank page are not
  confusable.
- `Artifact.ocr_geometry` persists it; `save_artifact(..., ocr_geometry=)` writes
  it; `/api/documents/…/artifacts` serves it behind `include_geometry`.
- The Mac app already renders boxes: `Views/Preview/ImageViewer/OCRGeometryOverlay.swift`
  and `Views/Preview/PDFViewer/PDFPageView+OCRBoxes.swift`, with selection
  handling in `Models/OCRGeometrySelection.swift`.

## Which producers actually emit word boxes today

| Producer | Word boxes? | Where |
|---|---|---|
| PDF text layer, at ingest | **Yes** | `from_pymupdf_page` reads `page.get_text("words")` — every word and its rectangle, free, no model |
| Apple Vision transcription | **Yes** | `_vision_word_boxes` walks `\S+` runs and asks the recognised-text candidate for each range's box, with char spans, y-flipped to top-left |
| LLM vision transcription | **No, in every shipped configuration** | see below |
| Google Vision / Textract / Azure / Tesseract / Paddle / EasyOCR / docTR | Parsers exist and are tested; no live caller | `ocr_geometry.py` |

So word-level geometry is not missing from Fichero. It is missing from **the LLM
path specifically**, which is the path most of Daniel's archival material takes.

## Why the LLM path produces none

Three gates, all of which must open:

1. `transcribe` takes `return_boxes` from its node config and **defaults it to
   `False`**.
2. **No preset in `resources/default_workflows/` sets `return_boxes` at all.**
   Verified by grep across every preset JSON: zero occurrences. The toggle is
   also not exposed anywhere in the Swift app — zero occurrences of
   `return_boxes`/`returnBoxes` under `fichero/fichero`.
3. `_supports_return_boxes` hard-gates it to `provider == "google"` **and**
   `"gemini" in model`. Any other provider with `return_boxes=True` fails that
   file with `"return_boxes requires provider=google with a Gemini model"`
   (raised inside `_process_file`, caught by the per-file handler, recorded as
   that file's error).

When boxes are not requested, `_llm_geometry_unavailable` records the reason on
the artifact — correct behaviour, and the reason it looks like "the LLM path
stores nothing" rather than "the LLM path stores an empty list".

The prompt half is already written. `_build_prompt(language, return_boxes=True)`
appends a JSON schema asking for `{"text": …, "boxes": [{"text", "bbox",
"level"}]}` in **fractions of the image, top-left origin**, and
`parse_vlm_geometry` accepts `bbox`, Qwen-style `bbox_2d` (xyxy pixels), and
`{x,y,width,height}`, normalising each. `_parse_return_boxes_payload` then
requires at least one box and raises otherwise.

## What is therefore left

Not an implementation problem. A policy problem with three questions:

**1. Which providers may be asked for boxes?**
`_supports_return_boxes` is a whitelist of one. Widening it is a one-line change,
but it changes what happens on a non-compliant model: the prompt asks for JSON,
the model returns prose, `_parse_return_boxes_payload` raises, and **the file
fails** — because `text` is taken from the parsed geometry, so a parse failure
loses the transcription too. Widening the gate without changing that coupling
turns "no boxes" into "no transcription" on every model that does not comply.

This is measured, not inferred. Running `process_vision` with
`return_boxes=True`, `provider=google`, `model=gemini-2.0-flash` and a provider
that returns ordinary prose instead of JSON:

```
google/gemini-2.0-flash: text=[''] error='Expecting value: line 1 column 1 (char 0)'
```

A perfectly good transcription was produced by the model and discarded because
the geometry did not parse.

**2. Word level or line level?**
The prompt currently says `"level" is "line" or "word"` and lets the model
choose. Daniel asked for word level. Vision models are markedly worse at word
boxes than line boxes — more boxes, each smaller, each with more room to be
subtly wrong, and subtly-wrong word boxes look authoritative. Options:
   - ask for word level and validate hard (below);
   - ask for line level from the model and **derive** word boxes by
     proportional subdivision of the line box, marked as derived in
     `metadata` so the UI can distinguish measured from inferred;
   - ask for word level only where a text layer or Apple Vision is unavailable.

**3. What validation beyond the existing range check?**
The `0..1` and in-bounds checks are structural. They do not catch a box that is
well-formed but points at the wrong part of the page. Cheap additional checks
worth having if this ships:
   - every box's `text` must occur in the transcription (the prompt already
     demands this; nothing enforces it);
   - box count within a sane multiple of the transcription's word count;
   - reject a result whose boxes overlap pathologically or all collapse into one
     region — the classic failure mode when a model invents coordinates;
   - `ocr_bbox_coverage` already computes boxed-tokens/total-tokens; a minimum
     coverage threshold below which the geometry is dropped (with a reason)
     rather than stored partial.

## Recommendation, for Daniel to accept or reject

Do **not** widen the provider gate as a first move. Instead:

1. Decouple text from geometry on the `return_boxes` path so a geometry parse
   failure degrades to "transcription saved, geometry unavailable, here is why"
   instead of failing the file. This is a strict improvement regardless of
   anything else and is the precondition for every other option.
2. Add the semantic validators above (box text present in transcription;
   coverage floor) so a compliant-looking-but-wrong result is rejected loudly.
3. Only then widen `_supports_return_boxes`, one provider at a time, each with a
   fixture proving the shape it returns actually parses.
4. Expose `return_boxes` on the transcribe node in the app, defaulting off, so
   the cost of asking for boxes is a deliberate choice per workflow.

Steps 1 and 2 are contained and testable. Steps 3 and 4 are the ones that need
Daniel's call on cost and on which models he trusts with coordinates.
