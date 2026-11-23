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
> transcribed page takes is `source/segment-representations.md`'s; entity/claim extraction and
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
  Pinned: `fichero-server/tests/unit/api/test_post_ingest_derivatives.py::TestTheStageProducesADerivative`,
  `::TestFailureIsVisibleNotSilent`.
  The thumbnails are made before heavy local work queued after them (#5585,
  `activity.lane.thumbnails-first` in `ui/activity-pane.md`), and a folder the import
  fills is laid out on its canvas as filed (#5585, `library.canvas.arranged-at-import` in
  `ui/library-view-modes.md`).
- `importer.import-roots-checked-resolved` — **[OK]** (#6261) a file may be imported only when its RESOLVED path lies under a resolved allowed root (or a sandbox staging place or a folder the owner picked): a symlink placed in Documents that points elsewhere is refused, judged by where it points; iCloud's ~/Documents, itself a link into ~/Library/Mobile Documents, still imports. Tested in `fichero-server/tests/unit/security/test_a_link_out_of_an_import_root_is_refused_6261.py`.
- `importer.a-folder-is-never-one-file` — **[OK]** (2026-10-11) a folder is never recorded as a single file:
  the files import (`POST /api/ingest/file`, `/files`) and document create refuse a folder in words ("Not a
  file: X is a folder. Add it as a folder, and its files come in one by one."), and a document already recorded
  that way has no picture made, said once, not a failed open on every ask (seen in a dev engine's log: "Image
  generation failed for CACIQUES_INDIOS,17,D.5 (.5): Is a directory", again and again). `folder_is_not_a_file`,
  `storage._generate_image`; `fichero-server/tests/unit/importers/test_a_folder_is_never_one_file.py`.
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
- `importer.folder-status-names-its-folder` — **[OK]** (#5584; built: `_made_folder_id` in
  `api/routes/ingest/core.py`, the `import.folder` action's `folder_id`; tested in
  `fichero-server/tests/unit/recipes/test_setup_through_mcp_edges.py`) a folder import's status
  (`GET /api/ingest/status/{task_id}`, MCP `fichero_ingest_get_status`) names the folder document
  the import made for the folder dropped (`folder_id`), so a caller can open, organise or run on it
  without searching for it by name. Null while it runs, and for an import that made no one folder.

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
**Cross-spec note (moved 2026-09-19):** the maintainer's Kraken-overlay-refresh finding
(running the opt-in tool above produced bounding boxes that didn't appear until clicked) is
NOT this spec's own behavior — the verified cause is a change-stream gap on the artifact/
segmentation side, not the import-trigger path. It now lives at
`source/segment-representations.md`'s `segment.overlay.refreshes-when-segmentation-finishes`
(#4890), not restated here.
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
- `importer.resumable-content-hash-skip` — **[PARTIAL]** (#739) a resumable corpus pass should
  skip already-imported content by hash at 100k-document scale, distinct from progress
  VISIBILITY (`importer.bulk-import-activity-visible`) — resuming a partial import and
  reporting one already in progress are two different capabilities. Verified 2026-11-20: a
  second drop onto the same place does skip what is already in and completes the folder; what
  is owed is in `importer.resumable-redrop-skips-without-reading` and
  `importer.resume.an-interrupted-import-is-offered-again` below.
- `importer.bilingual-content-does-not-duplicate-kg-rows` — **[GAP]** (#1798, redirected from
  the legacy "Importer - Source Archives" milestone) when a source's transcription duplicates
  the same content in two languages (reported against a multi-volume diary corpus specifically,
  English + Spanish), the importer should not produce duplicate KG entities/claims from the
  translated duplicate. No dedup-by-language mechanism was found in
  `importers/`/`workflows/tools/` this pass. Stated as a generalizable defect class, not
  assumed to be specific to that corpus — not independently reproduced against a second
  corpus this pass.
  Checked 2026-10-17 on a scratch copy of a multi-volume diary library (read-only): none of its 4,309
  transcription artifacts carries an English block followed by a Spanish block (26 mix English with
  Spanish loanwords and names only), and no KG claim is Spanish (2,813 `en`, 388 unset). The reported
  duplication is not present in this library, so there is nothing to red-test; it stays a GAP until a
  library that shows it is available.

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
  `ai/ai-settings.md` (section K, provider keys) as `keys.apple-vision-is-a-capability-not-only-a-key-check` — a
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
  pluggable image+sidecar corpus importer, the Tinderbox `.tbx` importer, a diary IIIF
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
- **#1667** ("Diary SMB staging logs missing 1928 enhanced image files during rsync") — an
  operational/infrastructure bug in one collection's staging pipeline, not an app behavior.
- **#1331** ("Black folder + Maps folder metadata fusion") — dataset-specific metadata work
  for one named collection.
- **#1235** ("import a notebook corpus"), **#1233** ("import already-catalogued
  materials") — literal data-loading tasks for named collections, not spec behaviors.

**Milestones**: neither #188 nor #65 reaches zero this pass. #188 (25 open) loses 6 (5 fit,
moved onto #307; 1 redirected to `provider-keys`), retaining 19 — 1 verify-close, 9 capture-
waiting, 7 pluggable-importer-waiting, 2 triage. #65 (10 open) loses 1 (fit, moved onto #307),
retaining 9 — 2 waiting (joining the pluggable-importer cluster), 7 triage. Neither closed.

Moved onto `importer` (#307) this pass, by number: **#4210, #3288, #2106, #1328, #739, #1798**.
Redirected to `provider-keys` (#305): **#2060**. Left in place, dispositioned above, not moved:
everything else.

## Import and derivatives at scale (review 2026-11-20, measured)

What a project of 5,000 page images needs from import, the derivative queue and its originals, written as what
should be and tagged against the code. Measured 2026-11-20 on a scratch engine and scratch libraries (an M4 with
24 GB, sources and library on a USB solid-state disk, the machine shared with test runs): 500 and 2,000 real page
photographs and scans (JPEG, PNG, TIFF; 2.0 GB per 500, 4 MB a page on average). Not measured here: PDFs, a
network volume, 5,000 pages in one run (the 5,000 figures are the 2,000 figures scaled).

| Step | 500 pages | 2,000 pages | 5,000 pages (scaled) |
|---|---|---|---|
| Link import, drop to last row saved | 29.5 s (17 files/s) | about 105 s | about 4.5 min |
| Copy import (same disk, cloned, no extra space) | 35.5 s (14 files/s) | not run | about 6 min |
| Thumbnails, two at a time (284 ms mean, 568 ms p95) | 83 s (6.0/s) | 207 s per 1,000 after a restart (4.8/s) | 14 to 17 min |
| Embed jobs for pages with no text (48 ms each, nothing embedded) | 24 s | 45 s per 1,000 | about 4 min |
| Drop to "Processing imported pages completed" | 134 s | not run in one piece | about 25 min |
| Engine memory (process tree, peak) | 1.34 GB importing, 1.45 GB on thumbnails | 1.22 GB | not measured |
| Disk in the project (link) | 92 MB thumbnails (184 KB a page), 3.3 MB database | 375 MB thumbnails, 16 MB database | about 0.95 GB |
| "Which originals are missing?" (none are) | 1.0 s | 4.0 s | about 10 s on a fast disk |

### Throughput and what a page costs

- `importer.scale.five-thousand-pages-budget` — **[PARTIAL]** (#4203) a folder of 5,000 page images linked from a
  solid-state disk is all rows within 5 minutes, shows its first thumbnail within a minute of the drop, has every
  thumbnail within 20 minutes, keeps the engine under 1.5 GB and adds under 1 GB to the project. *Measured:* the
  table above meets the import, memory and disk figures at 500 and 2,000 pages. *Not met:* the first thumbnail waits
  for the last file (`importer.resume.jobs-are-queued-with-each-batch`). *Not built:* a load leg that holds these
  numbers; the 100,000-file target of #4203 is not measured.
- `importer.scale.a-linked-file-is-read-once` — **[PARTIAL]** (→ #6832; nearest #4203) a link import reads each file's
  bytes once and asks the disk about it a handful of times. Today each file is read three times and asked about 32
  times (measured on 100 files, 390 MB: 2.99 times the bytes read, 25.8 `stat`, 6.3 `lstat`, 3 opens per file):
  `ingest_folder` hashes it for the skip test (`_file_checksum`), `ingest_file` hashes it again as the
  changed-while-read check (`_extract_file_metadata`, `known_checksum=None` for a link), and reading the image's
  size and EXIF reads it a third time (`_extract_image_metadata`; all in `importers/ingest.py`). On a network volume the read is the whole cost of an import. The
  changed-while-read check can be the size and date before and after one read.
  *Built:* the skip test's hash is the one read: `ingest_file` takes it as `known_checksum`, the changed-while-read
  check compares the file's size and date before and after (`_raise_if_changed_while_read`), and the image's size
  and EXIF come from the header (`open_image_header_checked`, `loaders/image_loader.py`). Counted in the test, a
  link import of six JPEGs reads 1.0 to 1.15 times the folder's bytes. *Not built:* the `stat`, `lstat` and open
  counts per file are not reduced or measured; a copy import still reads each file for the copy as well.
  Test: `fichero-server/tests/unit/importers/test_a_linked_file_is_read_once.py`.
- `importer.resumable-redrop-skips-without-reading` — **[PARTIAL]** (#739) dropping a folder again onto the place it
  was imported to brings in only what is missing and makes no second copy of anything. *Built:* the skip by source
  path and checksum, scoped to the destination (`ingest_folder`, `Database.ingest_dedup_keys`;
  `fichero-server/tests/unit/importers/test_ingest_dedup_scope.py`); measured, a 2,000-file folder cut off at 1,000
  was completed by a second drop in 59.5 s with no page twice and its 1,602 folders made once. *Not built:* the
  skip reads every byte of every file already imported to hash it; a file whose path, size and date match what was
  recorded is skipped without a read (today only an online-only cloud file is skipped that way).
  *Built:* (#6832) a file whose path, size and date match what its import recorded is skipped without being opened
  (`ingest_folder`, `Database.ingest_dedup_source_stamps`, scoped to the destination); a re-drop of six linked JPEGs
  reads no bytes, and a file whose size changed is read and imported again. *Not built:* a file whose date matches
  but whose bytes changed is not noticed.
  Test: `fichero-server/tests/unit/importers/test_a_linked_file_is_read_once.py`.
- `importer.scale.no-embed-job-for-a-page-without-text` — **[GAP]** (→ #6833; nearest #5954) a page with no text gets
  no embed job: its thumbnail landing is what ends `pending`. Today every image gets one (`queue_derivatives`:
  `embed_queued = queued`), which embeds nothing, costs 48 ms a page on the embed lane (24 s per 500 pages, at over
  one core) and is the only thing that turns the page from `pending` to `completed` (`_embed_stage`,
  `importers/derivatives.py`).
  *Built:* `queue_derivatives` queues an embed job only for a page with text, and the thumbnail stage ends a page
  with no text (`pending` to `completed`, unless the thumbnail failed). Test:
  `fichero-server/tests/unit/api/test_post_ingest_derivatives.py`.
- `importer.scale.prepare-pages-counts-what-lands` — **[PARTIAL]** (→ #6833; nearest #5954) the "Prepare pages" row
  counts a page when its thumbnail lands, so the count moves through the whole wait. *Built:* the row's stages
  carry their own counts (`queue_stages`, `importers/derivatives.py`). *Not built:* the row's own count moves only
  when an embed job ends (`_progress_tick` is called from `_embed_stage` alone), so it reads 0 of N for the whole
  thumbnail stage (83 s at 500 pages, about 15 min at 5,000) and then runs to N in seconds.
  *Built:* for a page with no text, its thumbnail stage ticks the count, so the count moves as those thumbnails land
  (`_thumbnail_stage`). *Not built:* a page with text still counts when its embed job ends. Test:
  `fichero-server/tests/unit/api/test_post_ingest_derivatives.py`.
- `importer.scale.edited-image-cache-is-bounded` — **[GAP]** (→ #6834; nearest #1590) an edited page's picture is
  made once per saved edit, off the request, and the copy of an earlier edit is removed when a later one is saved.
  Today `resolve_edited_source` (`db/storage.py`) writes a full-size PNG of the edited page into the project, inside
  the thumbnail or display request that first asks for it, one file per version of the edit chain, and nothing
  removes an older version. Read in the code; the size was measured outside the engine: an 18-megapixel photograph
  of 4.3 MB becomes a 24.6 MB PNG in 0.83 s, so one crop over 5,000 such pages is about 120 GB.
- `importer.scale.thumbnail-alias-costs-no-space` — **[OK]** each page's thumbnail is one file with two names (a hard
  link), not two copies: 1,000 files for 500 pages, every one with a link count of 2, 92 MB in all
  (`_sync_alias_to_cache`, `db/storage.py`;
  `fichero-server/tests/unit/db/test_thumbnail_alias_sync.py::test_the_same_inode_case_short_circuits`).

### A quit or a crash in the middle

- `importer.resume.held-queue-is-not-stalled` — **[PARTIAL]** (→ #6827; nearest #6584, #6209) after a restart the
  pages whose thumbnails and embeds wait for Continue are shown as held, counted from where they were, and are
  never called stalled. Today, measured twice: the engine was killed at 1,000 of 2,000 files; at the next open
  `resume_pending_derivatives` (`db/manager.py`) queued the 1,000 pending pages and armed the in-memory queue at
  "0 of 1,000" (`_progress_add`), `jobs.resume` then paused every one of those rows ("Stopped when Fichero quit"),
  and 61 s later the watchdog wrote "Processing imported pages stalled at 0 of 1000" (`_arm_stall_watchdog`:
  `queue_state` in `execution/jobs.py` says nothing for a queue whose rows are all paused). The row stays "running,
  0 of 1,000" until Continue; killed again with 121 thumbnails made, it came back as "0 of 1,000". Two thumbnail
  jobs ran before the pause reached them. The open also reads every pending page whole
  (`db.query(Document, status=pending)`) to do this. The run-resume half is its own work (`runner.soak.*`).
  Test to add: open a library whose pages are pending and whose rows are paused; no queue is armed and no stall is
  said after the deadline; after Continue the count starts at the thumbnails already made.
  *Built:* the open's re-queue runs after `jobs.resume`, makes its rows paused and arms no count; `queue_state`
  (`execution/jobs.py`) answers "held" for a queue whose rows are all paused, and the stall watchdog says nothing for
  it; Continue arms the count with the pages it lets go. *Not built:* that count starts at 0 of the pages still held,
  not at the thumbnails already made; the open still reads every pending page whole.
  Test: `fichero-server/tests/unit/importers/test_held_queue_is_not_stalled.py`.
- `importer.resume.jobs-are-queued-with-each-batch` — **[PARTIAL]** (→ #6829; nearest #739) a page's thumbnail job is
  written in the transaction that saves the page, batch by batch, so thumbnails start while the folder is still
  coming in and a quit leaves no page without its job. Today `import_folder_impl` (`api/routes/ingest/core.py`)
  calls `queue_derivatives` once, after the last file: killed at 1,000 of 2,000, the project held 1,000 pending
  pages and no job row, and at 5,000 pages the first thumbnail comes about 4.5 minutes after the drop.
  *Built:* `ingest_folder` calls `on_saved` inside the transaction that saves each batch (a per-file retry and a
  single save too), and the route queues that batch's thumbnail jobs there; nothing is queued after the last file.
  *Not built:* the synchronous `import.folder` action's own import row (below); the first-thumbnail time at 5,000
  pages is not measured again. Test: `fichero-server/tests/unit/importers/test_import_survives_a_quit.py`.
- `importer.resume.an-interrupted-import-is-offered-again` — **[PARTIAL]** (→ #6829; nearest #739) an import a quit or
  crash cut off is remembered in the project and offered at the next open with the rest of what the quit stopped:
  "Import of Box 3 stopped at 1,000 of 2,000 files", Continue or Dismiss. Today the task lives only in the engine's
  memory (`_tasks`, `api/routes/ingest/core.py`): after the restart nothing says the folder is half in, and the
  half that is in looks like a whole folder. Dropping it again completes it
  (`importer.resumable-redrop-skips-without-reading`), if the person knows to.
  *Built:* the folder route writes a job row for the import (`importers/interrupted_import.py`, kind
  "import-folder", its request and file count in the row); a row left running by a dead engine is held at open,
  listed by `stopped_at_quit`, and Continue runs `import.folder` again from the stored request with no page made
  twice. *Not built:* the launch alert reads "Import of Box 3 · 1,000 of 2,000 files", not "stopped at"; Dismiss is
  untested; the synchronous `import.folder` action (the CLI) writes no import row; a library opened a second time
  while an import runs would hold its running row, which has no live thread id.
  Test: `fichero-server/tests/unit/importers/test_import_survives_a_quit.py`.
- `importer.resume.launch-alert-is-one-row-per-queue` — **[PARTIAL]** (→ #6830; nearest #6584) what the quit stopped
  is listed as one item for the import's queue ("Prepare pages, 1,000 pages"), and Continue is one statement however
  many pages it holds. Today `stopped_at_quit` (`execution/jobs.py`) answers one item per page job (1,998 items and
  323 KB for 1,000 pages) and `continue_after_quit` updates them one at a time: 18.9 s for 1,998 rows and 24.9 s for
  1,879, the request held the whole time; about two minutes at 5,000 pages.
  *Built:* `stopped_at_quit` lists the held jobs of a registered queue (`QUEUES`) as one item whose id is the queue's
  ("Processing imported pages, 5,000 pages"), and `continue_after_quit` on that id reads the held rows once and lets
  them go with one UPDATE: 10,000 held rows continue in under a second in the test. *Not built:* the item's name is
  the queue's own ("Processing imported pages"), not "Prepare pages"; the alert view (Swift) is unchanged and not
  run against the one-item list; a page the person paused is not in the list, as before.
  Test: `fichero-server/tests/unit/jobs/test_continue_is_one_statement.py`.
- `importer.resume.no-twin-rows-at-open` — **[PARTIAL]** (#6209, #6595) the open leaves one job row per page and
  stage. *Built:* a waiting or paused row is reused (`enqueue_many`, `execution/jobs.py`). A page whose job was running at the kill is
  reused too (the open's re-queue runs after `jobs.resume`). *Not built:* a page whose job was already done while the
  page is still pending gets a second row: after one kill during thumbnails, 2,124 thumbnail rows stood for 2,000
  pages (124 settled at once as done by `settle_made_thumbnails`). Test:
  `fichero-server/tests/unit/importers/test_held_queue_is_not_stalled.py`.

### Files of one name

- `importer.same-name.files-from-different-folders-both-import` — **[PARTIAL]** (→ #6831; nearest #4579) files of the
  same name from different folders all come in, each a page of its own keeping its name, by every way in. A layout
  file that could belong to two images of one name pairs with neither and is listed as unpaired with that reason; a
  name never refuses the whole drop. Today the answer depends on the way in. A folder drop and a drop by path take
  them (`POST /api/ingest/folder`, `POST /api/ingest/files`: measured, eight pages sharing each of four names in the
  2,000-page import, and two files of one name from two folders dropped by path, both imported). The upload route
  refuses the whole batch with 422 "two files in the drop have the same name" (`import_files_together`,
  `api/routes/document/documents.py`), because `import_dropped_set` stages every upload under its bare name in one
  folder. That route is the one a remote client, the command line and the soak script use, so a camera's
  `IMG_0001` from two cards cannot be sent together. Test to add: two uploads of one name make two pages; two
  images of one name and one layout file of that name make two pages and one unpaired entry.
  *Built:* `import_files_together` no longer refuses a repeated name; `import_dropped_set` stages the first file of a
  name (compared case-folded) in the staging folder and each later one in its own `same-name-<i>/` folder, so each
  upload is a page keeping its name. A layout file whose name matches several images is moved to the unpaired list
  with the reason "N images in the drop are named ..." and imports as an ordinary file. *Not built:* a layout file
  that states the image's name inside it is not matched against the twins; there is no folder upload for #4579 (it
  stays open).
  Test: `fichero-server/tests/unit/importers/test_same_named_uploads_import.py`.

### Linked and copied originals

- `importer.originals.link-records-what-a-relink-needs` — **[OK]** a linked page records its path, a bookmark, its
  size, its checksum and its source date at import, which is what Locate Originals matches on (`ingest_file`,
  `_extract_file_metadata`, `importers/ingest.py`; `relink_plan`, `importers/relink.py`;
  `fichero-server/tests/unit/importers/test_locate_originals_5672.py`).
- `importer.originals.copy-is-a-clone-on-the-same-disk` — **[OK]** a copy import onto the disk the files are on takes
  no extra space (`_try_apfs_clone`, `_verify_copied`, `importers/ingest.py`): measured, 500 pages and 1.9 GB copied
  in 35.5 s with the disk's used space unchanged but for the thumbnails; the stored path is relative to the
  project, so a renamed project still finds them
  (`fichero-server/tests/unit/importers/test_ingest_package_paths.py`).
- `importer.originals.missing-check-is-bounded` — **[PARTIAL]** (→ #6828; nearest #6733) asking which originals are
  missing costs one listing per source folder (or one `stat` per page), reads only each page's id and recorded
  paths, answers a volume that is not mounted with one question for all its pages, gives up on a volume that does
  not answer within 10 seconds and says so, and is asked once per open and after a relink, not on every folder
  selected. Today, measured on 500 linked pages that are all present: `missing_originals`
  (`importers/relink.py`) made 311,382 `lstat` and 38,502 `stat` calls, about 700 a page, 161 of them on the source
  volume, because each page resolves its path and the project's allowed folders again and again (`_linked_missing`,
  `original_is_there`, then `resolve_source` and `resolve_document_source_path`); it also reads every document
  whole (`db.query(Document)`). It took 1.0 s at 500 pages and 4.0 s at 2,000 on a solid-state disk; at 5,000
  pages it is 3.5 million calls, 800,000 of them on the source volume, which on a volume that answers in a few
  milliseconds is the many-minute stall seen in a stall dump on 2026-11-20. The app asks at open and again each
  time a folder is selected (`LocateOriginalsPresenter` and `MissingOriginalsNotice`,
  `fichero/fichero/Views/Library/LocateOriginals.swift`), and the answer lists every missing id, which the app searches as
  an array for each cell (`OriginalsStore.isMissing`). Test to add: 500 linked pages in 5 folders are checked with
  at most one filesystem call a page and one listing a folder, counted; a volume that is not there is one call.
  *Built:* `missing_originals` reads id and path only, lists each folder once and confines it once
  (`path_security.prepare_roots`), and a volume under /Volumes that is not mounted is one `stat`. *Not built:* the
  10-second give-up on a volume that does not answer, the app's one ask per open and after a relink, and
  `OriginalsStore.isMissing`'s array search; a page the listing does not show still costs the full
  `original_is_there`. Test: `fichero-server/tests/unit/importers/test_missing_originals_is_bounded.py`.

## Build order

From the review of 2026-11-20 ("Import and derivatives at scale" above), its ranked fixes in rank order, one step each.

### Stage 1 — Import at 5,000 pages (the review's ranked fixes)

#### Step 1.1 — Held is not stalled; no twin rows at open (#6827, #6209)
- Behaviours: `importer.resume.held-queue-is-not-stalled`, `importer.resume.no-twin-rows-at-open`
- Tests: test_held_queue_is_not_stalled.py (not yet written), fichero-server/tests/unit/jobs/test_durable_5357.py
- Size: M

`importers/derivatives.py`, `execution/jobs.py`, `db/manager.py`: `queue_state` answers held when a queue's live rows
are all paused; the open's re-queue runs after `jobs.resume`, held, and arms nothing; Continue arms the count from the
job table; the open queries pending ids, not whole documents.

#### Step 1.2 — Which originals are missing: one call a page (#6828, #6733)
- Behaviours: `importer.originals.missing-check-is-bounded`
- Tests: test_missing_originals_is_bounded.py (not yet written), fichero-server/tests/unit/importers/test_locate_originals_5672.py
- Size: M

`importers/relink.py`, `db/storage.py`, `security/path_security.py`, the route, `OriginalsStore.swift`,
`LocateOriginals.swift`. Test: counted filesystem calls for 500 pages in 5 folders (at most 505); one call for a
volume that is not there.

#### Step 1.3 — An import survives a quit (#6829, #739)
- Behaviours: `importer.resume.jobs-are-queued-with-each-batch`, `importer.resume.an-interrupted-import-is-offered-again`
- Tests: fichero-server/tests/unit/importers/test_import_survives_a_quit.py
- Depends on: 1.1
- Size: M

`api/routes/ingest/core.py`, `importers/ingest.py`, `importers/derivatives.py`. Test: killed after batch 3, every saved
page has a thumbnail row; the launch alert lists the import; Continue finishes it with no page twice.

#### Step 1.4 — Continue in one statement; one alert item per queue (#6830, #6584)
- Behaviours: `importer.resume.launch-alert-is-one-row-per-queue`
- Tests: fichero-server/tests/unit/jobs/test_continue_is_one_statement.py
- Size: S

`execution/jobs.py`, `api/routes/system/activity.py`, the alert view. Test: 10,000 paused rows continue in under a
second; the list answers one item.

#### Step 1.5 — Uploads of one name both import (#6831, #4579)
- Behaviours: `importer.same-name.files-from-different-folders-both-import`
- Tests: fichero-server/tests/unit/importers/test_same_named_uploads_import.py
- Size: S

`api/routes/document/documents.py` (`import_files_together`, `import_dropped_set`), `importers/interchange_pairing.py`.

#### Step 1.6 — A linked file is read once; a re-drop skips by size and date (#6832, #739)
- Behaviours: `importer.scale.a-linked-file-is-read-once`, `importer.resumable-redrop-skips-without-reading`, `importer.resumable-content-hash-skip`
- Tests: fichero-server/tests/unit/importers/test_a_linked_file_is_read_once.py, fichero-server/tests/unit/importers/test_ingest_dedup_scope.py
- Size: S

`importers/ingest.py`. Test: counted reads equal the folder's bytes; a re-drop reads none.

#### Step 1.7 — No embed job for a page without text; Prepare pages counts thumbnails (#6833, #5954)
- Behaviours: `importer.scale.no-embed-job-for-a-page-without-text`, `importer.scale.prepare-pages-counts-what-lands`
- Tests: fichero-server/tests/unit/api/test_post_ingest_derivatives.py
- Size: S

`importers/derivatives.py`. Tests: an image import queues no embed row; the count moves with thumbnails.

#### Step 1.8 — The edited-image cache is bounded (#6834, #1590)
- Behaviours: `importer.scale.edited-image-cache-is-bounded`
- Tests: test_edited_image_cache_is_bounded.py (not yet written)
- Size: M

`db/storage.py`, the edit actions. Test: three edits leave one file.

#### Step 1.9 — The import load leg (#6864, #4203)
- Behaviours: `importer.scale.five-thousand-pages-budget`
- Tests: test_import_soak.py (not yet written), fichero-server/tests/unit/scripts/test_soak_run_6732.py
- Depends on: 1.1, 1.3
- Size: M

A script like `scripts/soak_run.py` for import only: 500 pages, a kill mid-import and one mid-thumbnails, checked
against the budget in `importer.scale.five-thousand-pages-budget`. Its nightly run on the M4 is the manager's.

## Out of scope (pointed at with arrows)

- **What a workflow does to a node once it exists** (transcription, extraction, chains) —
  `ui/workflows.md`.
- **The shape a segmented/transcribed page takes** (regions, bounding boxes, the geometry a
  Kraken/Apple-Vision pass would produce once `importer.segmentation-automatic-no-toggle`
  lands) — `source/segment-representations.md`.
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
| Load | y, by hand | 500 and 2,000 real pages on a scratch engine, killed mid-import and mid-thumbnails (2026-11-20, the table under "Import and derivatives at scale"); no test holds the numbers yet (`importer.scale.five-thousand-pages-budget`) | — |

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
| 2060 | Apple Vision framework as on-device OCR/vision engine | recommend re-home — a provider/OCR concern (`ai/ai-settings.md`, `ai/ai-settings.md` (section K, provider keys)), not the raw import pipeline |
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

1. **Answered** (maintainer 2026-10-04: failed index → Activity + health): Indexing state, including failure, shows in Activity and health. Is the `pending` → `completed` transition after deferred embedding surfaced to the user
   anywhere (a status badge, a "not yet searchable" hint), or does it rely entirely on the
   generic document-status refresh mechanism (`DocumentStore+StatusRefresh.swift`) with
   nothing embedding-specific? Not verified this pass — a real open question, not a
   confirmed gap.
2. **Answered** (design lead 2026-10-04, by the existing design): The curation guard already runs inside the one KG writer import uses (`importers/nlp_draft.py`, `workflows/curation_guard.py`), so there is no separate pass. Once Kraken segmentation and the free NLP layer both run at import
   (`importer.segmentation-automatic-no-toggle`, `importer.nlp-auto-at-import`), does the
   curation-persists-and-constrains-imports checker become part of THIS pipeline (import-time
   entity resolution) or stay a `kg/kg-enrichment.md`-owned pass that runs just after?
3. **Answered** (design lead 2026-10-04, applying the spec's lean): Fold capture in here as an entry point beside drag-and-drop. The capture cluster (#2352/2353/2355/2356/2357/2364/2367/2380/3280) is nine issues
   recommended for re-homing — does it get its own `capture.md` spec, or fold into this one
   as a fifth pipeline stage ("capture" as an entry point alongside drag-drop/Data-menu)?
4. **Answered** (design lead 2026-10-04, applying the spec's lean): A section here once one of them is worked. The IIIF/pluggable-importer cluster (#1632/1646/1650/1651/1656/1658) is six issues — same
   question: own spec, or a section here once one of them is actually worked?
5. **Answered** (design lead 2026-10-04, applying the spec's lean): Yes, a load profile comes first. Does `importer.bulk-import-activity-visible`'s 100k-scale claim (#4203) need its own load
   test/profile (the spec's Load leg, elsewhere referenced as #4634-style profiling) before
   it can honestly retag `[OK]`?

## Rulings

- **2026-09-28, restated 2026-10-04 (#5183):** the image ingest limit is 200 megapixels; it is owed
  (`importer.image-ingest-limit-200-megapixels`).

## Triaged from the backlog (2026-10-04)
- `importer.remote-folder-upload` — **[GAP]** (#4579) a remote client can import a folder through one upload endpoint with a shared task id, batching and dedup pre-scan, not N single-file uploads.
- `importer.no-agpl-pdf-dependency` — **[GAP]** (#4609) PyMuPDF is removed; the page-splitting fallback uses pypdfium2 (fitz is still imported in importers/ingest.py, workflows/tools/split_images.py and others).
- `importer.language-detection-says-not-reliable` — **[PARTIAL]** (#5572) `multilingual.detect_language` is one function, the character-range heuristic (no cld3 import): a Latin-script or empty text answers language `und` with is_reliable False, never `en`; scripts it can tell (Japanese, Korean, Chinese, Arabic, Cyrillic, Hebrew, Thai, Devanagari) keep their code; a real detector comes later as a model card the recipe offers (ruled 2026-10-17); still owed: `llm/lang_detect.detect_language` and `knowledge/spacy_ner.detect_language` are separate detectors that remain, to fold into the same one; pinned by fichero-server/tests/unit/llm/test_language_detection_not_reliable_5572.py.
- `importer.repair-redrop-no-reembed` — **[PARTIAL]** (#4617) a repair-only re-drop embeds only new or changed text: an entity or claim whose stored vector row has the same text and model is skipped; pinned by fichero-server/tests/unit/db/test_embed_skips_unchanged_4617.py. Still owed, its own later issue: lance compaction (a re-embed that does happen appends a version rather than replacing).
- `importer.timecoded-transcript-ingest` — **[PARTIAL]** (#975) .srt/.vtt/.sbv ingest as timecoded segments { start_ms, end_ms, speaker?, text } in an artifact of type transcript on the document, with clean dialog (no timestamps, cue numbers or markup) as page_content; whisper/pyannote-style segment JSON parses by the same parse_transcript; plain .txt transcripts stay flat text; pinned by fichero-server/tests/unit/loaders/test_transcript_loader.py. Still owed: routing of .json files to it, the Inspector timecoded panel with click-to-seek, and attaching to a same-basename audio/video parent.
- `importer.folder-jsonl-corpus-manifest` — **[GAP]** (#1632) a folder holding one `fichero.jsonl` (one line per image/doc with transcript, entities, claims, metadata, images referenced not copied) imports idempotently and resumably through the same importer as the v1 manifest (manifest_import.py handles the JSON manifest only).
- `importer.merge-portable-library-output` — **[GAP]** (#1651) the output of a portable workflow run elsewhere (a library.duckdb or an IIIF+W3C directory) merges into a target library idempotently through the engine's save paths, upserting by canonical ids (no DuckDB merge path found in the code).
- `importer.capture-queue-camera-intake` — **[GAP]** (#2353) iPhone/iPad capture queues photos locally to a cached library/folder destination, survives relaunch, and uploads when the paired Mac is reachable and signed in, with no per-photo cataloguing UI.
- `importer.capture-batches-are-normal-evidence` — **[GAP]** (#2357) a capture batch flows through catalogue, entity, claim and citation generation with provenance back to the original image, enhanced derivative and workflow run, as normal Fichero evidence, not a capture-only record type.
- `importer.clip-intake` — **[GAP]** (#2364) a URL, web page, document, PDF or page selection can be clipped into a library with source URL, accessed_at and citation metadata, keeping the original snapshot and the clean markdown as separate artifacts (no clip code exists).
- `importer.clip-is-first-class-material` — **[GAP]** (#2367) a clip is searchable, workflow-processable, citeable and provenance-preserving like any imported document, pinned by a clip-to-workflow integration test.
- `importer.capture-rules-by-person` — **[GAP]** (#2380) the Mac Settings Capture tab maps each person to a library and a workflow; the device never chooses destination or workflow, the signed-in user determines the rule.
- `importer.ios-import-is-copy-only` — **[PARTIAL]** (#3282) *Built:* nothing iOS-only names an ingest mode or calls an ingest route; the phone adds through the capture queue's upload, never LINK, which is a macOS bookmark on the engine's filesystem (`fichero-server/tests/unit/scripts/test_ios_never_links_ingest_3282.py`). *Not built:* the engine refusing a LINK from a client-picked path with a typed error (`X-Fichero-Client` is attribution only, never authz, #4469, so it needs a capability answer, not a header check), and the audit that every iOS visual comes from storage endpoints.
- `importer.capture-upload-is-idempotent` — **[GAP]** (#3280) a mobile capture upload is one idempotent request keyed by a client-generated id, so a retry after a half-finished upload or a post-upload edit never creates a duplicate document (MobileCaptureQueue.swift:197 still does import then update).
- `import.folder-shows-at-once` — **[PARTIAL]** (#7066; 2026-11-23) app + engine, macOS and iOS. The moment an import (a dropped folder or files, Data ▸ Import…) or a IIIF add is accepted, its folder is in the sidebar, revealed, with a spinner on its row; items fill in as they arrive; the spinner goes when the import finishes; a failed import leaves the row with an error mark and its reason (Inspector, Activity), never a vanished row. The engine creates the destination folder and answers its id before any item is copied or fetched; the app inserts that one row in place (no sidebar reload, #4522). Related: #7040, #4235. *Built:* the folder route makes the destination folder and announces it before answering, and answers `folder_id`; the IIIF add answers `folder_id` with the job id, the folder named for the URL host until the manifest label replaces it; the app marks the row importing (`FolderImportTracker`), opens its ancestors, clears it on the status or job finish, and keeps it marked with the reason on a failure. Not run here: the Swift tests (no build in the worker); the sidebar drawing (spinner, error mark, reveal) is untested beyond the tracker; a corpus or 1.0 archive answers no folder id. *Tests:* `fichero-server/tests/unit/importers/test_folder_shows_at_once.py`; `fichero/Tests/Unit/general/Models/FolderImportTrackerTests.swift`.
- `import.dock-drop-folder-reliable` — **[GAP]** (#4182) dropping a folder on the Dock icon imports it cleanly and the sidebar updates live.
- `import.content-pane-drop-scoped` — **[GAP]** (#4458) the external-file drop target attaches to the content column only, not the whole NavigationSplitView including the sidebar.
- `importer.alto-multi-page-reads-every-page` — **[OK]** (#5310) a multi-page ALTO file imported on its own brings in every `<Page>` through an `alto.read_pages` used by import_file_as_pages, each page's lines under its own page, as TEI already does; pinned by fichero-server/tests/unit/importers/test_alto_multi_page_reads_every_page.py.
- `importer.move-import-leaves-file-at-destination` — **[OK]** (#5313) after a MOVE import the file is at its destination and gone from the source, pinned by fichero-server/tests/unit/security/test_library_membership_and_ingest_mode_api.py::test_ingest_file_mode_link_copy_move_apply.
- `importer.image-ingest-limit-200-megapixels` — **[PARTIAL]** (#5183, #5515) the ingest decompression-bomb limit is 200 MP (loaders/image_loader.py, with PIL's own guard moved to match; a refusal names the pixel count, and the 74.8 MP Reichsanzeiger page from #5183 ingests; pinned by fichero-server/tests/unit/loaders/test_ingest_limit_200mp.py); still owed: images above about 64 MP shown through tiles or downsampled previews so memory stays bounded. (Ruled 2026-09-28.)
- `importer.copy-mode-drop-pairs-layout-with-image` — **[GAP]** (#5220) a COPY-mode drop of loose files pairs a layout file with its image like link and move do (case-blind pairing landed in ad8b7c4bc, e6db06f05, 964470d1b).
- `importer.originals.bookmark-followed` — **[GAP]** (#6733; app + engine; owner 2026-11-19) on open, and on "Original unavailable", each
  document's stored bookmark is resolved first; a file the bookmark finds after a rename or a move is relinked silently, its
  new path and a fresh bookmark saved at once. A bookmark the engine cannot resolve in its own process is resolved by the app,
  which hands the engine paths (or the engine uses the app's resolved scope). Whenever an original is found (a bookmark that
  resolves somewhere new, Retry, a folder relink, or a stale bookmark that still resolves) its new path and a fresh bookmark
  are saved, and a stale bookmark is always refreshed, so the next move is followed too. Test: a moved and renamed file is
  found by its bookmark; a file moved twice is followed both times without asking.
- `importer.originals.locate-folder-relinks-all` — **[GAP]** (#6733; app + engine; owner 2026-11-19) File ▸ Locate Originals takes a folder
  and relinks every missing original found under it, matching by file name and size, then by content hash, and reports N
  relinked and M still missing; it never errors on the ones it cannot match, and an error it does show names what failed.
  Test: a folder holding three moved files relinks three and reports none missing.
- `importer.originals.retry-finds-and-relinks` — **[GAP]** (#6733; app + engine; owner 2026-11-19) a thumbnail that says "Original unavailable"
  offers Retry. Retry resolves the bookmark, then searches the last folder used and the library's known roots; on finding the
  original it relinks it and offers to relink the other K missing originals in that folder too. Test: Retry finds one and
  offers the rest.
- `importer.originals.one-is-it-there-test` — **[PARTIAL]** (#6733; app + engine; owner 2026-11-19) one test of "is this original there?" is used by
  the Locate Originals sheet, the thumbnail and Retry, so they cannot disagree (today the sheet says every linked original is
  where the project says while thumbnails say "Original unavailable"; a volume the engine cannot read must count as missing,
  not as found). The sheet's words are plain: nothing missing, "All N originals were found."; some missing, "N of M originals
  can't be found. They were last in: …" with "Choose the folder they're in now…"; after a relink, "Relinked N. Still missing: M."
  The sheet can still point at a new folder when nothing is missing ("Move originals to a new folder…"). Related: #5818.
  *Built (checked 2026-11-20):* the engine's one test, `original_is_there` (`importers/relink.py`), is what
  `missing_originals` asks, the thumbnail's own answer; `fichero-server/tests/unit/importers/test_original_is_there_6733.py`.
  *Not built:* the sheet's counts ("All N originals were found." says no N today) and Retry using the same test;
  what the test costs at scale is `importer.originals.missing-check-is-bounded`.
- `importer.missing-original-fails-in-words` — **[GAP]** (#5818) a page whose original is not where it was imported from fails its thumbnail job in words, "<file> isn't where it was imported from: Locate Originals…" (the sentence #5811 gives a try), so the job row ends `failed` naming the file instead of finishing silently; the batch ends with each failed page named. A run waiting behind thumbnails says what it waits for (the stage, the pages that failed and why): `activity.waiting-says-why` (`execution/jobs.py` `first_reason`: the held row appends up to four thumbnail pages that failed since it was queued, newest first; tested in `tests/unit/jobs/test_a_waiting_run_says_what_it_waits_for_5818.py`).
- `importer.derivative-source-found-for-resumed-documents` — **[BROKEN]** (#5408) resuming derivatives finds each pending document's source (pages of a notebook corpus fail with 'source not found') or says why.

## Future (ideas, not scheduled)
- (#1233) already-catalogued corpus is a demo/test dataset awaiting the Source Archives home; Future section, not current engine work.
- (#1235) a notebook corpus + catalogue spreadsheet as a release demo library (its import script exists but corpus unfinished); Future section; note notebook corpus data rulings (train yes, release no).
- (#2208) ICANH/Andagoya corpus import + Spanish Script transcription QA is corpus-specific work for the Source Archives program, not a pipeline behaviour.
- (#2209) Archivos Nuestros corpus import + library QA is corpus-specific Source Archives work, not a pipeline behaviour.
- (#4183) Browser extensions (Safari, Chrome, Firefox) and a system share-sheet target to add content to Fichero.
- (#4184) Full review of drag-in ingestion asymmetries (folders, Finder promises, link/copy/move, progress and errors); likely folds into import specs once reviewed.
