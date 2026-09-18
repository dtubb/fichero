# Importer — Design Spec (#TBD)

> Milestone: importer
> Manual: TBD — the user manual's Getting Started section needs "Bringing files in": drag a
> file or folder into the library, or use Data ▸ Import…; text becomes searchable
> immediately, everything else (segmentation, NLP, embeddings) happens automatically in the
> background without pegging the machine.

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** "Import, ingest, capture, and
> indexing pipeline" (GitHub milestone #188) accumulated 29 open issues with no spec anchor;
> this is that anchor, written against the code as it stands, not the standing rulings as
> written.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts a ruling (needs an issue).
>
> **Out of scope, pointed at with arrows:** what a workflow DOES to an imported document
> (transcription, extraction, chains) is `ui/workflows.md`'s; the shape a segmented/
> transcribed page takes is `kg/segment-representations.md`'s; entity/claim extraction and
> curation-persistence is `kg/kg-enrichment.md`'s. This spec owns only the pipeline from a
> file arriving to it becoming a readable, searchable library node.

## Intent (the design)

A file or folder, dropped or picked, becomes a library node with the least possible delay and
the least possible user decision. Text that already exists in the file is extracted and
searchable the moment it lands — never a later step. Everything free the machine can do on
its own (segmentation geometry, a lightweight NLP draft, a vector embedding) runs
automatically, with no toggle to find and no decision to make, and never at the cost of a
usable machine — background work throttles itself. A failure anywhere is visible (in Activity,
in the file's own status), never a silent nothing.

## Standing rulings this spec measures the code against (paraphrased, not quoted)

- **Segmentation is automatic, no toggle.** The neural line/baseline segmenter (Kraken)
  auto-provisions on first use and runs on every eligible page at import, as a free draft
  geometry layer VLM transcription later refines. Failure or offline degrades silently to no
  draft geometry — it never blocks the import.
- **The free NLP layer is automatic BY DEFAULT, with a real visible toggle (unlike
  Kraken).** A lightweight parse/NER/date pass runs on every page at import, the same way
  embeddings do — a draft layer an LLM/VLM workflow later refines and the user curates. It IS
  exposed as a Settings toggle beside auto-extract/auto-embed, defaulting ON, so a user can
  see it and turn it off — a real switch, not merely a visible indicator.
- **Curation persists across re-import.** A human's entity/claim corrections become rules the
  import-time entity checker consults on every later import, so re-importing more of a corpus
  doesn't reintroduce what was already fixed. (Lives downstream of raw import — see Out of
  scope above; this spec only notes where the pipeline WOULD need to call it.)
- **The client never touches a local file path.** The engine may run on a different machine;
  the app renders everything through storage HTTP endpoints, never a local file URL.
- **Background work never pegs the machine.** Embedding, derivative generation, and any
  future heavy import-time pass must auto-throttle (background QoS, bounded concurrency) so
  the foreground UI stays responsive — the work still happens, just never at full-machine
  cost.
- **Real data changes the ground rules.** Once a library holds a real corpus, a schema change
  is a migration, never a rebuild — mentioned here because several open issues below propose
  format/schema changes to the ingest path.

## The pipeline as built (drop → readable node)

1. **Entry.** A file/folder arrives via drag-drop onto the sidebar/library, or Data ▸ Import…
   (`LibraryView+BottomActionBar.swift`'s `handleFileImport` → `ImportService.importFiles`).
   Both call the same `POST /api/ingest/file` or `/folder`.
2. **Validation.** The server-side path must be inside an allowed root
   (`_validate_ingest_path`/`_is_allowed_local_path`, `api/routes/ingest/core.py:37`) — this
   is the ENGINE checking ITS OWN filesystem access, not the client reading a local path (the
   no-local-paths ruling binds the Swift app, not the server that legitimately owns the disk
   it ingests from).
3. **Document creation + text extraction.** `ingest_file`/`ingest_folder`
   (`importers/ingest.py`) create the `Document` row; text-bearing files (`.md`, `.txt`,
   `.docx`) get `page_content` populated immediately — `extract_text` defaults `True` at
   every layer (Swift omits it, the engine route defaults it `True`).
4. **Derivative generation.** Eligible types (image, PDF) get an eager thumbnail derivative
   queued (`importers/derivatives.py`'s `queue_derivatives`), throttled to a bounded worker
   pool at background QoS.
5. **Embedding — automatic, deliberately deferred, not skipped.** `auto_embed` (route
   request field) defaults `False`, but that flag means "embed INLINE, blocking the
   request" — a tests/CLI-only path. The SAME `queue_derivatives` call from step 4 also
   queues embedding for every document with text (`needs_embedding`), regardless of
   `auto_embed`; the document lands with `Status.pending` and the background stage flips it
   to `completed` once embedded (2026-08-09 redesign: the old inline default made a first
   import pay the ~19s model-load before the request finished). This IS the
   throttle-don't-disable ruling, correctly built — `auto_embed=False` reads like "off" but
   means "not synchronous."
6. **Segmentation and NLP — both should be automatic, NEITHER is wired at all yet.** Nothing
   in this pipeline invokes Kraken or a spaCy/NER pass — both exist elsewhere in the codebase
   (a workflow tool, a Settings AI provider) but neither runs during import. Their TARGET
   shapes differ, though: Kraken is fully automatic with no user-facing switch at all, ever;
   the NLP layer is automatic BY DEFAULT but is meant to expose a real Settings toggle (beside
   auto-extract/auto-embed) so a user can see and turn it off — "no toggle" was never the
   ruling for NLP, only for Kraken. Corrected 2026-09-18 (an earlier version of this spec
   conflated the two).
7. **Downstream.** Once a node exists, workflows (`ui/workflows.md`) run transcription/
   extraction/entity-resolution against it — manually, today, because steps 6's automatic
   drafts don't exist yet to seed them.

## Behaviors

### What shipped

- `importer.text-extracted-by-default` — **[OK]** a text-bearing file gets `page_content`
  populated at ingest time, searchable immediately — no separate extraction step. Pinned:
  `test_ingest_default_extract_text.py::TestIngestDefaultExtractText::test_markdown_gets_page_content_by_default`,
  `::test_txt_gets_page_content_by_default`,
  `::test_extract_text_false_still_supported` (an explicit opt-out still works, for batch
  callers that defer to a workflow),
  `::test_image_file_skips_text_extraction` (no `.jpg`→`.txt` fallback attempted).
- `importer.derivative-generation-visible-failure` — **[OK]** an eligible file (image/PDF)
  gets a thumbnail derivative queued, and a failure in that stage is visible, never silent.
  Pinned: `test_post_ingest_derivatives.py::TestTheStageProducesADerivative`,
  `::TestFailureIsVisibleNotSilent`.
- `importer.embeddings-auto-at-import` — **[OK]**
  a document with text is embedded automatically after import, no opt-in needed. The
  `auto_embed` request flag defaults `False`, but that flag means "embed INLINE, blocking
  the request" (tests/CLI only) — `queue_derivatives` (the SAME call `importer.derivative-
  generation-visible-failure` pins) queues embedding for every document `needs_embedding`
  flags REGARDLESS of `auto_embed`; the document lands `Status.pending` and the background
  stage flips it to `completed` once embedded (2026-08-09 redesign, moved off the inline
  path that made a first import pay a ~19s model-load). Pinned:
  `test_post_ingest_derivatives.py::TestDeferredEmbedding::test_ingest_request_defaults_defer_embedding`
  (the flag defaults false — confirms the deferral, not an opt-out),
  `::test_text_bearing_documents_are_queued`,
  `::test_the_stage_embeds_the_document_and_its_pdf_pages`,
  `::test_pending_clears_after_deferred_embedding`,
  `::test_an_embed_failure_is_recorded_and_does_not_strand_pending`.
- `importer.background-throttled` — **[OK]** embedding and derivative work runs at bounded
  concurrency and background QoS, so a bulk import never pegs the foreground machine — the
  exact fix for the field incident (1,622-image import at 457% CPU) the ruling names.
  Pinned: `test_background_compute.py::TestBackgroundQoS`, `::TestEmbedConcurrency`.
- `importer.bulk-import-activity-visible` — **[PARTIAL]** (#3308, #4203) a running import's
  progress is visible, coalesced into Activity rather than flooding change events per file.
  Built: `test_post_ingest_derivatives.py::TestQueueEmitsCoalescedTrackerActivity` pins the
  coalescing itself. Not verified this pass: whether the specific 100,000-document scale
  target in #4203 (live toolbar progress, non-blocking at that scale) is actually met —
  the two issues describe a scale target beyond what this pass traced end-to-end.

### What has not shipped, or contradicts a ruling

- `importer.segmentation-automatic-no-toggle` — **[GAP]** (#4822, filed this pass) Kraken
  segmentation should auto-provision and run on every eligible page at import. Verified not
  wired: no reference to Kraken exists in `importers/ingest.py`, `api/routes/ingest/core.py`,
  or `importers/derivatives.py` — it exists only as an opt-in workflow tool
  (`detect_regions_kraken.json`) a user must run manually.
- `importer.nlp-auto-at-import` — **[GAP]** (#4823, filed this pass) a free NLP draft
  (spaCy parse in v1; NER and dateparser are follow-ups, not this pass's scope — issue numbers
  pending) should run on every page at import, defaulting ON and exposed as a REAL Settings
  toggle beside auto-extract/auto-embed (not merely "no toggle" the way Kraken is). Verified
  not wired: no `spacy` reference exists anywhere in the import pipeline; spaCy exists only as
  a Settings ▸ AI provider a user configures separately. The engine lane is building the
  following against this issue right now; each is its own behavior below so the acceptance
  criteria are checkable individually once landed, all [GAP] (#4823) until then:
- `importer.nlp-rows-marked-unreviewed` — **[GAP]** (#4823) every row the NLP pass writes is
  marked machine-proposed and unreviewed — never presented as if a human or an LLM already
  confirmed it.
- `importer.nlp-never-overwrites-curated-rows` — **[GAP]** (#4823) a row a human has touched,
  or one an LLM/VLM workflow produced, is never overwritten or duplicated by a LATER NLP
  pass — the draft layer only fills gaps, it never clobbers or races a more-authoritative
  layer.
- `importer.nlp-scoped-to-new-and-stranded-only` — **[GAP]** (#4823) the NLP stage runs for
  newly imported documents and stranded-pending recovery only — it never sweeps an existing
  library's already-processed documents just because the app opened.
- `importer.nlp-language-picks-the-model` — **[GAP]** (#4823) the document's own language
  picks which NLP model runs (a Spanish source yields Spanish statements, per the
  statement-language-matches-document ruling); a missing model for a document's language is a
  VISIBLE state the user can see, never a silent skip that leaves a page quietly undrafted.
- `importer.nlp-one-coalesced-event-per-document` — **[GAP]** (#4823) the NLP pass emits ONE
  coalesced change event per document, not one per row/sentence/entity it produces — the same
  no-per-item-flood discipline `observable.no-per-item-refresh-loop`
  (`harness/observable-data-layer.md`) names for the client side, applied here on the
  producer side.
- `importer.pdf-import-from-link-and-drop` — **[GAP]** (#2386) PDF import via a link and via
  drag/drop must both work. Reported broken; not independently re-verified in code this pass.
- `importer.format-coverage-gaps` — **[GAP]** (#4206) audio/video files extract no text, ~110
  sidecar files are silently missed, and five formats are unverified. Reported, not
  independently re-traced in code this pass — cited at face value from the issue's own
  survey.

## Out of scope (pointed at with arrows)

- **What a workflow does to a node once it exists** (transcription, extraction, chains) —
  `ui/workflows.md`.
- **The shape a segmented/transcribed page takes** (regions, bounding boxes, the geometry a
  Kraken/Apple-Vision pass would produce once `importer.segmentation-automatic-no-toggle`
  lands) — `kg/segment-representations.md`.
- **Entity/claim extraction and curation persistence across re-import** — the
  curation-persists-and-constrains-imports ruling's "import-time entity checker" has nowhere
  to hook into today, because NER doesn't run at import at all yet
  (`importer.nlp-auto-at-import`); once it does, the checker itself is `kg/kg-enrichment.md`'s
  to build and spec.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | text extraction defaults, image-file skip | `fichero-server/tests/unit/importers/test_ingest_default_extract_text.py` |
| Backend (pytest) | y | derivative stage produces output, failure is visible | `fichero-server/tests/unit/api/test_post_ingest_derivatives.py` |
| Backend (pytest) | y | background QoS + bounded embed concurrency | `fichero-server/tests/unit/core/test_background_compute.py` |
| Backend (pytest) | n | no test covers Kraken-at-import or NLP-at-import (neither is wired) | — (the two GAPs above) |
| Availability (Swift) | y | Data ▸ Import… reaches the focused pane; the bottom-bar/drag affordances exist | `fichero/Tests/Unit/general/App/LibraryImportFocusedValueTests.swift`, `.../Views/Library/LibraryImportAffordancesTests.swift` (not individually re-read this pass — named for completeness, not cited as proof of a behavior above) |
| Click-around (XCUITest) | n | no dedicated drop-a-file-and-see-it-readable flow test found | — |

Hard-gate: none yet — DRAFT spec; a hard-gate set is chosen once `importer.segmentation-
automatic-no-toggle` and `importer.nlp-auto-at-import` (the two genuinely unbuilt rulings)
have owners.

## Issue map (all 29 open issues on "Importer", #188)

Disposition key: **cited** = moved onto `importer` (#307), backs a behavior above by plain
citation · **related** = touches this pipeline but not folded into a specific claim above;
stays on #188 · **recommend-close** = looks superseded by what's built, or is a meta/summary
issue; the maintainer's call, not closed here · **recommend re-home** = a distinct sub-system
(capture, a specific pluggable importer, IIIF) that deserves its own spec, not this one's.

| # | Title | Disposition |
|---|---|---|
| 739 | Resumable corpus pass with content-hash skip (100K-scale) | related — dedup/resume is a distinct concern from progress visibility; stays on #188 |
| 744 | Tinderbox importer: .tbx → vector DB + KG | recommend re-home — a specific pluggable-importer feature |
| 975 | Structured transcript ingest: timecoded segments + diarization | recommend re-home — a specific format's own feature |
| 1328 | Drag-in folder/file import: smooth ingest UX | related — drag-drop works today (verified: `handleFileImport`/`ImportService`); whether it's "smooth" at scale ties to #739/#3308/#4203 |
| 1632 | Pluggable corpus importer: image+sidecar → general import | recommend re-home — its own importer feature |
| 1646 | IIIF + W3C annotation importer | recommend re-home — its own importer feature |
| 1650 | Old custom-fichero format → IIIF + W3C | recommend re-home — paired with 1646 |
| 1651 | Cluster-output → merge into a Fichero library | recommend re-home — paired with 1646/1650 |
| 1656 | IIIF importer: tests + OpenAPI sync | recommend re-home — paired with 1646 |
| 1658 | Andy→IIIF converter: always emit local images | recommend re-home — paired with 1646 |
| 2060 | Apple Vision framework as on-device OCR/vision engine | recommend re-home — a provider/OCR concern (`ai/ai-settings.md`, `ai/provider-keys.md`), not the raw import pipeline |
| 2106 | Add documents via HTTP/URL + share-in | related — a real alternate entry point, not code-verified this pass; stays on #188 |
| 2352 | Capture: session + resumable mobile upload contract | recommend re-home — the mobile-capture sub-system |
| 2353 | Capture: iPhone/iPad camera intake | recommend re-home — paired with 2352 |
| 2355 | Capture: mobile + watched-folder smoke matrix | recommend re-home — paired with 2352 |
| 2356 | Captured-image enhancement + OCR/transcription preset | recommend re-home — paired with 2352 |
| 2357 | Catalogue/entity/citation/provenance for capture batches | recommend re-home — paired with 2352 |
| 2364 | Clip intake API (URLs/pages/documents) | recommend re-home — its own intake surface |
| 2367 | Clip-to-workflow citation/provenance gate | recommend re-home — paired with 2364 |
| 2380 | Configure incoming captures by person/library/workflow | recommend re-home — paired with 2352 |
| 2386 | PDF import must work from link and drag/drop | **cited** → `importer.pdf-import-from-link-and-drop` |
| 3276 | FE forces extractText/autoEmbed=false, defeating "searchable on land" | recommend-close — re-examined 2026-09-18: both halves are true in code now (`extract_text` defaults `True` end-to-end; embeddings run automatically via the deferred `queue_derivatives`/`_embed_stage` path, `auto_embed=False` means "not inline," not "not at all") — resolved by the 2026-08-09 deferred-derivative redesign, not left open. No remainder found this pass (did not verify whether the `pending`→`completed` transition is surfaced to the user beyond the generic document-status refresh mechanism — a real but unconfirmed open question, not asserted as a defect) |
| 3280 | Capture: mobile upload non-idempotent, duplicates on retry | recommend re-home — paired with 2352 |
| 3288 | Dead/duplicated FE import surface (unused DragDropModel, two IngestMode enums) | related — a real cleanup target, not traced in code this pass; stays on #188 |
| 3292 | Fabel Review Summary — Importers, Ingest & Capture | recommend-close — a review-summary meta-issue; this spec supersedes it as the living anchor |
| 3308 | Large imports (100k images): granular Activity progress | **cited** → `importer.bulk-import-activity-visible` |
| 4203 | Ingest at scale: 100k documents, live Activity + toolbar progress | **cited** → `importer.bulk-import-activity-visible` |
| 4206 | Format coverage: audio/video no text, sidecars missed, formats unverified | **cited** → `importer.format-coverage-gaps` |
| 4210 | Row-per-record spreadsheet import: engine+CLI only, unreachable from app | related — a specific format's UI gap; stays on #188 |

Moved onto `importer` (#307) by number: **#2386, #3308, #4203, #4206**, plus the two
new issues filed this pass, **#4822** (`importer.segmentation-automatic-no-toggle`) and
**#4823** (`importer.nlp-auto-at-import`). Everything else stays on #188. Nothing closed.

## Open questions

1. Is the `pending` → `completed` transition after deferred embedding surfaced to the user
   anywhere (a status badge, a "not yet searchable" hint), or does it rely entirely on the
   generic document-status refresh mechanism (`DocumentStore+StatusRefresh.swift`) with
   nothing embedding-specific? Not verified this pass — a real open question, not a
   confirmed gap.
2. Once Kraken segmentation and the free NLP layer both run at import
   (`importer.segmentation-automatic-no-toggle`, `importer.nlp-auto-at-import`), does the
   curation-persists-and-constrains-imports checker become part of THIS pipeline (import-time
   entity resolution) or stay a `kg/kg-enrichment.md`-owned pass that runs just after?
3. The capture cluster (#2352/2353/2355/2356/2357/2364/2367/2380/3280) is nine issues
   recommended for re-homing — does it get its own `capture.md` spec, or fold into this one
   as a fifth pipeline stage ("capture" as an entry point alongside drag-drop/Data-menu)?
4. The IIIF/pluggable-importer cluster (#1632/1646/1650/1651/1656/1658) is six issues — same
   question: own spec, or a section here once one of them is actually worked?
5. Does `importer.bulk-import-activity-visible`'s 100k-scale claim (#4203) need its own load
   test/profile (the spec's Load leg, elsewhere referenced as #4634-style profiling) before
   it can honestly retag `[OK]`?
