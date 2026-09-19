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
6. **Segmentation and NLP — different states now.** Kraken segmentation is STILL not wired:
   nothing in this pipeline invokes it, it exists only as an opt-in workflow tool a user runs
   manually. **The NLP draft stage IS wired now** (177fc6cd3) — `derivatives._nlp_stage` runs
   on the same bounded, background-QoS executor as thumbnails/embeds, scoped to new/
   stranded-pending documents, gated on `auto_nlp_enabled()`. Their TARGET shapes still
   differ: Kraken is fully automatic with no user-facing switch at all, ever; the NLP layer is
   meant to default ON with a real Settings toggle beside auto-extract/auto-embed — it SHIPS
   with that gate reading OFF until the Settings row and the purge UI exist (#4830) — "no
   toggle" was never the ruling for NLP, only for Kraken.
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

  Redirected here from the legacy "Settings - Models & Providers" milestone while folding
  `ai-settings.md`'s pass 2: **#4268** ("Embeddings run automatically after import, visible as
  activity") asks for exactly this behavior — the automatic-background half is confirmed
  built above; whether embedding progress specifically surfaces in the status island/activity
  popover (the issue's own second half) was not independently re-verified this pass.
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
  segmentation should auto-provision and run on every eligible page at import. Re-verified at
  HEAD (2026-09-19): the RUNTIME layer is real and working — `get_kraken_runtime().status()`/
  `.start_install()` (`api/routes/ai/local_models.py:55-92`) can report install state and
  provision Kraken on request — but that capability is still never CALLED from the import
  path: no reference to Kraken exists in `importers/ingest.py`, `api/routes/ingest/core.py`,
  or `importers/derivatives.py`, so it stays an opt-in workflow tool
  (`detect_regions_kraken.json`) a user must run manually, exactly as behind the ratified
  "auto-provision + auto-run at import, no toggle" ruling as before. The gap is the wiring
  between two things that both already exist, not a missing capability.
- `importer.nlp-auto-at-import` — **[PARTIAL]** (#4830 — the original filing issue for the
  NLP-draft stage is closed, its engine half landed 177fc6cd3) the free NLP draft stage itself is BUILT: `run_nlp_draft`
  (`fichero-server/src/fichero_server/importers/nlp_draft.py`) writes real entity/claim rows
  through the one audited writer, wired into `derivatives._nlp_stage` on the same bounded,
  background-QoS executor thumbnails/embeds already share. What keeps this [PARTIAL] rather
  than [OK]: the ratified default is ON, but it SHIPS OFF —
  `auto_nlp_enabled()`'s documented temporary default (`_DEFAULT_ENABLED`'s docstring) is False
  until a real Settings row exists and a way to take rows back exists (the purge action below
  covers "take rows back"; the Settings ▸ AI row itself, plus a maintainer's review of draft
  output, is #4830, distinct from the original (now-closed) filing issue). Pinned (default-off, explicit on/off read):
  `test_nlp_draft_import.py::TestSettingGatesQueueing::test_default_is_off_for_now`,
  `::test_explicit_on_setting_is_read`, `::test_explicit_off_setting_is_read`,
  `::test_setting_off_queues_no_nlp_stage`, `::test_setting_on_queues_the_nlp_stage`.
- `importer.nlp-rows-marked-unreviewed` — **[OK]** (177fc6cd3) every row the NLP pass writes is
  marked machine-proposed and unreviewed via the EXISTING `curation_state` field — no new
  field, no migration — never presented as if a human or an LLM already confirmed it. Pinned:
  `test_nlp_draft_import.py::TestTheStageProducesADraft::test_new_rows_are_unreviewed_drafts`.
- `importer.nlp-never-overwrites-curated-rows` — **[OK]** (177fc6cd3) a row a human has
  touched, or one an LLM/VLM workflow produced, is never overwritten or duplicated by a LATER
  NLP pass — proven against the ACTUAL update/link/merge/authority-link paths, not a hand-set
  metadata flag: renaming (`entity.update`), merging (`entity.merge`), an authority link, a
  note reference, a claim link, or a corroborating LLM claim all independently protect a row
  from the companion purge action, and curation itself survives a second identical NLP run
  without duplicating. Pinned:
  `test_nlp_draft_import.py::TestCurationSurvivesAndConstrains::test_a_human_reviewed_entity_is_not_reset_or_duplicated_by_a_rerun`,
  `::test_a_claim_suppression_rule_prunes_the_draft_before_it_is_written`,
  `test_nlp_draft_import.py::TestWriterIdempotency::test_the_same_page_proposed_twice_does_not_duplicate_rows`,
  `test_nlp_draft_purge_action.py::TestSurvivorsAreNeverTouched::test_a_human_reviewed_entity_survives_the_purge`,
  `::test_an_entity_also_evidenced_by_a_non_draft_claim_survives`,
  `::test_a_claim_corroborated_by_another_extractor_survives`,
  `::test_a_reviewed_claim_survives`,
  `test_nlp_draft_purge_action.py::TestF2IndependentTouchProtection::test_a_renamed_but_unreviewed_entity_survives`,
  `::test_an_entity_with_a_note_survives`,
  `::test_an_entity_with_an_authority_link_survives`,
  `::test_a_merge_survivor_survives`, `::test_a_claim_with_a_link_survives`.
- `importer.nlp-scoped-to-new-and-stranded-only` — **[OK]** (177fc6cd3) the NLP stage runs for
  newly imported documents and stranded-pending recovery only (`needs_nlp` mirrors the
  existing `needs_embedding` population) — it never sweeps an existing library's
  already-processed documents just because the app opened. Pinned:
  `test_nlp_draft_import.py::TestExistingLibrariesAreNotSwept::test_needs_nlp_matches_needs_embedding_population`,
  `::test_opening_a_library_with_only_completed_docs_queues_nothing`.
- `importer.nlp-language-picks-the-model` — **[OK]** (177fc6cd3) the document's own language
  picks which NLP model runs (a Spanish source yields Spanish statements, per the
  statement-language-matches-document ruling); a missing model for a document's language is a
  VISIBLE state the user can see (an explicit error, never a silent empty result, and never a
  silent fallback to English when the resolved language's model is missing). Pinned:
  `test_nlp_draft_import.py::TestMissingModelIsVisible::test_model_not_installed_is_a_visible_error_not_a_silent_empty_result`,
  `::test_missing_model_for_the_resolved_language_never_falls_back_to_english`,
  `test_nlp_draft_import.py::TestNlpStageInDerivatives::test_missing_model_records_visible_metadata_never_flips_processed`.
- `importer.nlp-one-coalesced-event-per-document` — **[OK]** (177fc6cd3) the NLP pass emits ONE
  coalesced change event per document, not one per row/sentence/entity it produces — the same
  no-per-item-flood discipline `observable.no-per-item-refresh-loop`
  (`harness/observable-data-layer.md`) names for the client side, applied here on the
  producer side; and emits NO event at all when nothing was written. Pinned:
  `test_nlp_draft_import.py::TestChangeEventIsCoalescedOncePerDocument::test_one_call_for_the_whole_document`,
  `::test_no_event_when_nothing_was_written`.
- `importer.nlp-draft-quality-gate` — **[OK]** (177fc6cd3) `passes_draft_quality_gate` ports
  the app's existing OCR-garbage heuristic (letter-ratio, length floor, stop-word/pronoun
  exclusion, concept-type exclusion) to the draft layer, so OCR noise and function words never
  become entity rows; a visible per-document cap (`_DRAFT_MAX_ENTITIES_PER_DOCUMENT`, default
  200) truncates rather than silently exploding a noisy page, and the truncation is recorded
  on the document's own metadata, not just logged. Pinned:
  `test_nlp_draft_import.py::TestDraftQualityGate::test_the_gate_table` (18-row table: good
  Spanish/accented/paleographic/multi-word names pass; OCR noise, timestamps, single letters,
  all-numeric, low letter-ratio, stop words, and excluded types all fail),
  `::test_a_garbage_span_never_reaches_the_writer`,
  `::test_concept_type_is_excluded_from_the_draft_layer_entirely`,
  `::test_per_document_cap_truncates_visibly`, `::test_truncation_is_recorded_on_the_document_visibly`.
- `importer.nlp-audited-purge` — **[OK]** (177fc6cd3) `entity.purge_nlp_draft` is the audited
  way back: dry-run by default (counts, deletes nothing), scoped to one document or the whole
  library, idempotent (a second purge finds nothing), and removes ONLY rows nothing else has
  touched — reporting `protected_count`/`protected_reasons` so a dry run shows exactly what it
  will and won't remove before anyone commits to it. Routed through `registry.invoke`, the
  same audited choke point every other action uses. Pinned:
  `test_nlp_draft_purge_action.py::TestDryRunIsTheDefault::test_dry_run_counts_but_deletes_nothing`,
  `test_nlp_draft_purge_action.py::TestRealPurgeRemovesDraftRows::test_document_scoped_purge_removes_the_draft`,
  `::test_purge_clears_nlp_processed_at_so_a_rerun_is_possible`,
  `::test_idempotent_second_purge_finds_nothing`, `::test_library_scoped_purge_spans_every_document`,
  `test_nlp_draft_purge_action.py::TestF2IndependentTouchProtection::test_dry_run_reports_protected_breakdown`.
- `importer.pdf-import-from-link-and-drop` — **[GAP]** (#2386) PDF import via a link and via
  drag/drop must both work. Reported broken; not independently re-verified in code this pass.
- `importer.format-coverage-gaps` — **[GAP]** (#4206) audio/video files extract no text, ~110
  sidecar files are silently missed, and five formats are unverified. Reported, not
  independently re-traced in code this pass — cited at face value from the issue's own
  survey.

### Legacy milestone fold (#188 "Importer," #65 "Importer - Source Archives"), pass 2

All 35 open issues read fresh by body. One methodological note first: `gh issue list
--milestone "Importer"` (by TITLE) silently merges this legacy milestone (#188) with the
spec's OWN milestone (#307, titled lowercase `importer`) — GitHub's milestone-title matching
is case-insensitive. Every count and list below is filtered by milestone NUMBER
(`.milestone.number == 188`), not title, to avoid re-folding issues already moved.

- `importer.spreadsheet-import-reachable-from-app` — **[GAP]** (#4210) row-per-record
  spreadsheet import exists at the engine and CLI layers but has no route reachable from the
  app. Not independently re-verified in code this pass.
- `importer.dead-fe-surface-cleanup` — **[GAP]** (#3288) the import surface carries dead and
  duplicated code. Verified PARTIALLY at HEAD: two SEPARATE `IngestMode` enums genuinely exist
  — `Document.IngestMode` (`Models/Document.swift:536`, raw values `link`/`copy`/`move`,
  lowercase) and `ImportServiceTypes.IngestMode` (`Services/ImportServiceTypes.swift:7`, raw
  values `"LINK"`/`"COPY"`/`"MOVE"`, uppercase) — a real, confirmed conflict. NOT verified as
  claimed: `DragDropModel.swift` is referenced across at least nine other files (sidebar
  actions, focused commands, drop handlers) — it reads as actively used, not dead code; that
  specific half of the issue's claim does not hold as stated.
- `importer.url-and-share-in-entry-point` — **[GAP]** (#2106) adding documents via HTTP/URL
  and OS share-in (Share extension / macOS Services) is a real alternate entry point, distinct
  from drag-drop. Not verified as built.
- `importer.drag-in-is-smooth-at-scale` — **[PARTIAL]** (#1328) drag-in folder/file import
  works today (`handleFileImport`/`ImportService`, confirmed by an earlier pass), but whether
  it stays "smooth" at scale ties directly to `importer.bulk-import-activity-visible` above
  (#739/#3308/#4203) rather than being a separate mechanism — cited together, not duplicated.
- `importer.resumable-content-hash-skip` — **[GAP]** (#739) a resumable corpus pass should
  skip already-imported content by hash at 100k-document scale, distinct from progress
  VISIBILITY (`importer.bulk-import-activity-visible`) — resuming a partial import and
  reporting one already in progress are two different capabilities. Not verified as built.
- `importer.bilingual-content-does-not-duplicate-kg-rows` — **[GAP]** (#1798, redirected from
  the legacy "Importer - Source Archives" milestone) when a source's transcription duplicates
  the same content in two languages (reported against the Marshall corpus specifically,
  English + Spanish), the importer should not produce duplicate KG entities/claims from the
  translated duplicate. No dedup-by-language mechanism was found in
  `importers/`/`workflows/tools/` this pass. Stated as a generalizable defect class, not
  assumed to be Marshall-specific plumbing — not independently reproduced against a second
  corpus this pass.

**Verify-close — evidence posted, left OPEN, not closed here:**

- **#3276** ("FE forces extractText/autoEmbed=false, defeating 'searchable on land'") —
  re-verified at HEAD (2026-09-19), same finding an earlier pass through this file reached
  2026-09-18: both halves are true in code NOW — `extract_text` defaults `True` end-to-end,
  and embeddings run automatically via the deferred `queue_derivatives`/`_embed_stage` path;
  `auto_embed=False` means "not inline," not "not at all." Resolved by the 2026-08-09
  deferred-derivative redesign. Not verified: whether the `pending`→`completed` transition is
  surfaced to the user beyond the generic document-status refresh mechanism (a real,
  unconfirmed open question, not asserted as a defect).

**Redirected to an existing spec:**

- **#2060** ("Apple Vision framework as an on-device OCR/vision engine") →
  `ai/provider-keys.md` as `keys.apple-vision-is-a-capability-not-only-a-key-check` — a
  provider/capability question, not the raw import pipeline.

**Waiting on a spec that does not exist (left on the legacy milestone, not moved):**

Two clusters, neither with a spec today:

- **Mobile/watched-folder capture** (9 issues): #3280, #2380, #2367, #2364, #2357, #2356,
  #2355, #2353, #2352 — session/upload contract, camera intake, capture-batch workflows,
  configuration by person/library/workflow, the smoke-test matrix, and the non-idempotent
  mobile-upload-duplicates bug. One coherent sub-system (capture SESSIONS, distinct from a
  plain file drop), consistently reasoned as its own spec's territory by an earlier pass
  through this file — re-confirmed, not re-litigated.
- **Specific/pluggable importers** (9 issues): #1658, #1656, #1651, #1650, #1646, #1632, #744
  (from "Importer"), plus #1708, #1654 (from "Importer - Source Archives") — the IIIF/W3C
  annotation importer family (manifest/collection consumption, the old-format converter,
  cluster-output merge, its own OpenAPI/CLI test suite, the Andy→IIIF converter), the
  pluggable image+sidecar corpus importer, the Tinderbox `.tbx` importer, the Marshall IIIF
  reliability EPIC, and the Black Pacific maps importer (whose image-region-anchoring half
  also touches `segment-representations.md`, noted but not split into two issues). Each is a
  DISTINCT importer implementation this general pipeline spec should not absorb — they need
  their own spec (an "importer implementations" or per-format spec), not this one's behaviors.

**Maintainer triage, no home found:**

- **#3292** ("Fabel Review Summary — Importers, Ingest & Capture") — a review-summary meta
  issue; this spec is positioned to supersede it as the living anchor, but retiring a tracking
  issue is the maintainer's call, not asserted here.
- **#975** ("Structured transcript ingest: timecoded segments + speaker diarization") — a
  specific format's own feature (audio/video transcripts), not cleanly capture, not cleanly
  IIIF, not a general pipeline behavior — no home found among the specs read this pass.
- **#2464** ("ICANH library shows no PDFs — verify data present, fix listing") — a
  data-verification task against one specific, already-imported real library, not a
  generalizable importer behavor to state as a spec line.
- **#2209** ("Archivos Nuestros importer + reproducible library QA"), **#2208** ("ICANH/
  Andagoya importer + Spanish Script transcription QA") — building and QA-ing specific
  real-archive importers; same "needs its own spec" reasoning as the pluggable-importers
  cluster above, but framed as one-off data-loading projects for named collections rather than
  a generalizable capability — TRIAGE rather than folded into that waiting cluster, since
  grouping them together would understate how dataset-specific each one is.
- **#1667** ("Marshall SMB staging logs missing 1928 enhanced image files during rsync") — an
  operational/infrastructure bug in one collection's staging pipeline, not an app behavior.
- **#1331** ("Black folder + Maps folder metadata fusion") — dataset-specific metadata work
  for one named collection.
- **#1235** ("import Sergio Mosquera notebooks"), **#1233** ("import already-catalogued GHC
  materials") — literal data-loading tasks for named collections, not spec behaviors.

**Milestones**: neither #188 nor #65 reaches zero this pass. #188 (25 open) loses 6 (5 fit,
moved onto #307; 1 redirected to `provider-keys`), retaining 19 — 1 verify-close, 9 capture-
waiting, 7 pluggable-importer-waiting, 2 triage. #65 (10 open) loses 1 (fit, moved onto #307),
retaining 9 — 2 waiting (joining the pluggable-importer cluster), 7 triage. Neither closed.

Moved onto `importer` (#307) this pass, by number: **#4210, #3288, #2106, #1328, #739, #1798**.
Redirected to `provider-keys` (#305): **#2060**. Left in place, dispositioned above, not moved:
everything else.

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
| Backend (pytest) | y (NLP) / n (Kraken) | NLP-at-import IS covered now (62 tests, `importer.nlp-*` above); Kraken-at-import is still not wired | `test_nlp_draft_import.py`, `test_nlp_draft_purge_action.py` (NLP) — none yet (Kraken) |
| Availability (Swift) | y | Data ▸ Import… reaches the focused pane; the bottom-bar/drag affordances exist | `fichero/Tests/Unit/general/App/LibraryImportFocusedValueTests.swift`, `.../Views/Library/LibraryImportAffordancesTests.swift` (not individually re-read this pass — named for completeness, not cited as proof of a behavior above) |
| Click-around (XCUITest) | n | no dedicated drop-a-file-and-see-it-readable flow test found | — |

Hard-gate: none yet — DRAFT spec; a hard-gate set is chosen once `importer.segmentation-
automatic-no-toggle` and `importer.nlp-auto-at-import` (the two genuinely unbuilt rulings)
have owners.

## Issue map (all 29 open issues on "Importer", #188) — HISTORICAL, 2026-09-18 pass

Superseded by "Legacy milestone fold... pass 2" above (2026-09-19), which re-read every issue
against this vocabulary's exact fits/redirect/waiting/verify-close/triage rubric and reflects
the CURRENT open set (25 on #188, not 29 — four moved between this table and the pass 2 fold).
Kept for the reasoning trail, not as the live disposition; the pass 2 section above is
authoritative.

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

Moved onto `importer` (#307) by number: **#2386, #3308, #4203, #4206**, plus **#4822**
(`importer.segmentation-automatic-no-toggle`) and **#4830** (`importer.nlp-auto-at-import`'s
remaining Settings-row/purge-UI/maintainer-review scope — the original NLP-draft filing issue
from this pass shipped and closed at 177fc6cd3). Everything else stays on #188.

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
