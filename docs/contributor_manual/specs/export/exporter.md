# Exporter — Design Spec

> Milestone: export-pipeline (GitHub #316 — deliberately NOT named "exporter"/"Exporter": that
> collides case-insensitively with legacy milestone #14, "Exporter")
> Manual: TBD — the user manual needs an "Exporting your library" section: what Export as
> Markdown/Word do per-document from the Reader, what the Eleventy static-site export produces
> and how to host it, and that JSONL/Parquet/Excel/training exports exist but are reached
> through the CLI or API today, not a SwiftUI panel.

> Design-led spec (Testing Constitution). The creative director owns the intent; tests
> enforce it; code makes them pass. One line per behavior, each cited by its pinning test.
> **Status: DRAFT — PASS 1 of 2** (built behaviors only, grounded in disk 2026-09-19; the
> fold-in of legacy milestones #14 and #212's 25 open issues is PASS 2 — a fold plan follows
> this spec's own behaviors, no issues moved yet).
> Tags: **[OK]** behaves this way today · **[PARTIAL]** implemented, not fully verified/tested
> · **[BROKEN]** regression, code contradicts the line · **[GAP]** intended, never built.

## Intent (the design)

Fichero exports through ONE canonical record stream feeding several emitters, plus a
SEPARATE, deliberately different path for the knowledge graph's own RDF export. This spec
covers both: the document/entity/claim record stream (`export_service.iter_export_records`)
and its six emitters (JSONL, Parquet, Eleventy static site, Markdown folder, Word, Excel), and
the KG's own `GET /kg/export/rdf` (Turtle/N-Triples/JSON-LD/RDF-XML, schema.org JSON-LD
context, round-trip validated).

**Ratified rulings honored here, not restated:** export is DuckDB Parquet, not PyArrow — the
Parquet writer goes through DuckDB's own `COPY ... TO ... (FORMAT PARQUET)` over a JSON Lines
intermediate, never the PyArrow library some older issues in this fold still propose. The
archival format is IIIF + W3C + RDF, standards not custom — the RDF export and its schema.org
JSON-LD context are that standard, not a bespoke one. No local paths, since the server may be
remote — this is WHY the JSONL and Parquet export routes are deliberately CLI/backend-only:
their request shape takes an engine-local filesystem destination path, which no SwiftUI
save/export workflow may legitimately supply (see `scripts/check_ui_wiring.py`'s own allowlist
reason for both routes). Docs describe what is built — every behavior below is read from the
code, not from an issue's own framing of what it should do.

Surfaces: `export_service.py` (`iter_export_records`, `export_jsonl`, `export_parquet`,
`export_eleventy_site`, `export_markdown_folder`, `export_word_docx`, `export_excel_xlsx`),
`api/routes/ingest/export.py` (the seven POST routes), `api/routes/kg/sparql.py`'s
`GET /export/rdf`, `App/Menus/ReaderExportCommands.swift` + `ReaderExportRunner.swift` (the
app's own Export menu), `Services/DocumentService.swift`.

## Behaviors (each → one pinning test)

### A. The one stream, DuckDB Parquet, no PyArrow

- `export.one-stream-feeds-every-record-emitter` — **[OK]** `iter_export_records` is the
  SINGLE canonical read that JSONL, Parquet, the Eleventy site, and (through the same document
  collection) Markdown/Word/Excel all consume — one source of truth serialized differently,
  never a forked model per target. Verified at HEAD: `export_jsonl`, `export_parquet`, and
  `export_eleventy_site` (`export_service.py:124-330`) all call `iter_export_records` directly;
  each yielded record carries its own scope (`_scope_for_document`/`_knowledge_scope_records`,
  page/expediente-folder/box-collection granularity) and provenance
  (`_document_export_provenance`) — the "Found in" location provenance several fold issues ask
  for by name is already a first-class field on every record, not a gap. Pinned:
  `test_export_service.py::test_iter_export_records_page_granularity_carries_document_provenance`,
  `::test_iter_export_records_expediente_granularity_dedupes_entity_scopes`,
  `::test_iter_export_records_box_granularity_uses_top_collection_scope`.
- `export.duckdb-parquet-not-pyarrow` — **[OK]** the Parquet writer never imports or requires
  PyArrow — it writes each record type to a temp JSON Lines file, then converts through the
  managed DuckDB connection's own `COPY (SELECT * FROM read_json_auto(?)) TO '...' (FORMAT
  PARQUET)` (`db/__init__.py`'s `export_jsonl_as_parquet:6006-6021`). Verified at HEAD:
  `_write_parquet_records`'s own docstring states "without requiring PyArrow" and the
  implementation matches. Pinned:
  `test_export_service.py::test_export_parquet_uses_database_parquet_writer`,
  `::test_export_parquet_writes_typed_files_and_manifest`,
  `::test_export_parquet_empty_partitions_keep_canonical_columns`.
- `export.malformed-record-raises-never-ships-a-partial-export` — **[OK]** a claim missing its
  declared provenance source, or a page missing a declared image source, raises rather than
  silently emitting a broken or partial record. Pinned:
  `test_export_service.py::test_iter_export_records_raises_for_missing_claim_provenance_source`,
  `::test_export_eleventy_site_raises_for_missing_claim_page_path`,
  `::test_export_eleventy_site_raises_for_missing_search_page_path`,
  `::test_export_markdown_folder_raises_for_missing_declared_image_source`,
  `::test_export_word_docx_raises_for_missing_declared_image_source`.
- `export.unicode-and-unsourced-knowledge-handled-honestly` — **[OK]** Unicode and
  mojibake-ish names round-trip through export unchanged; unsourced knowledge (an entity/claim
  with no source document) exports at library scope rather than being silently dropped, and a
  scoped (folder-only) export still correctly drops what's genuinely out of scope. Pinned:
  `test_export_service.py::test_iter_export_records_preserves_unicode_and_mojibakeish_names`,
  `::test_iter_export_records_exports_unsourced_knowledge_at_library_scope`,
  `::test_iter_export_records_scoped_export_still_drops_unsourced_knowledge`,
  `::test_export_eleventy_site_renders_unsourced_entity_without_page_link`.

### B. The emitters

- `export.eleventy-site-is-buildable-and-portable` — **[OK]** the Eleventy/Netlify static-site
  emitter produces a document-only output (no stray non-document rows) from the SAME
  `iter_export_records` stream, portable and hostable with no running engine required. Pinned:
  `test_export_service.py::test_export_eleventy_site_output_stays_document_only`.
- `export.word-and-excel-and-markdown-folder-are-typed-emitters` — **[OK]** Word (.docx,
  optionally with a knowledge-graph appendix), Excel (.xlsx, documents+entities+claims), and
  the Markdown-folder emitter (aggregating a parent document's ordered page-child text) are
  all built and tested server-side, each honoring the create-vs-overwrite conflict rule (409
  unless `overwrite`). Pinned: `test_routes_export.py::TestWordExport` (4 cases, incl. the
  knowledge-graph appendix and its opt-out), `::TestExcelExport` (2 cases),
  `::TestMarkdownFolderExport` (4 cases), `::TestParquetExport` (2 cases),
  `::TestJsonlExport` (2 cases), `::TestEleventySiteExport`.

### C. The app's own Export menu — narrower than the engine's emitters

- `export.app-wires-word-and-per-document-markdown-only` — **[PARTIAL]** (→ #4873) of the
  engine's seven export routes, the app's own Export menu
  (`App/Menus/ReaderExportCommands.swift`/`ReaderExportRunner.swift`) reaches exactly TWO: Word
  (`ReaderExportRunner.exportWord` → `POST /api/export/word`, confirmed CALLED by
  `scripts/check_ui_wiring.py`'s live run — its own allowlist entry is stale and should be
  dropped) and a per-document "Export as Markdown" — which is NOT the engine's
  `markdown-folder` route at all: `ReaderExportRunner.exportMarkdown` writes the Reader's
  ALREADY-LOADED text directly to a file client-side (`Data(item.text.utf8).write(to:)`), a
  simpler, engine-independent quick-export, distinct from the structured Markdown+assets
  folder emitter Section B pins. JSONL, Parquet, and Training are deliberately CLI/backend-only
  (their destination path is engine-local, per the no-local-paths ruling above); Excel and the
  KG's RDF export have no app call site found at all. PARTIAL rather than a plain GAP list
  because two routes genuinely are wired and tested from the app; filed #4873 for a dispatch
  test asserting exactly this reachability matrix, since it was verified by reading
  `ReaderExportCommands.swift`/`ReaderExportRunner.swift` directly, not by a test.

### D. The knowledge graph's own RDF export — a separate contract, not the record stream

- `export.rdf-multi-format-with-named-jsonld-context` — **[OK]** `GET /kg/export/rdf` renders
  the library's entity+claim store as RDF in Turtle, N-Triples, JSON-LD, or RDF/XML; `context`
  selects a named JSON-LD `@context` profile, with `schema-org` the only one shipping today
  (Linked Art/CIDOC-CRM deferred, per the route's own docstring). Deliberately built as an
  in-memory, cached-per-library graph (`_cached_rdf_graph`), NOT the same streaming contract as
  `iter_export_records` — the route's own docstring states this explicitly and warns against
  conflating the two. Pinned:
  `test_jsonld_export.py::test_export_entities_claims_as_jsonld_with_context`,
  `::test_jsonld_context_is_selectable_and_named`,
  `::test_export_round_trips_for_every_non_jsonld_format`.
- `export.jsonld-round-trip-validated-before-shipping` — **[OK]** a JSON-LD export is parsed
  back into a graph before it ships — a malformed export raises a 500 rather than shipping a
  silently broken file, and the round-trip is checked for isomorphism, not merely "parses."
  Verified at HEAD: `_validate_jsonld_export` (`sparql.py`) does exactly this, with its own
  doc comment naming it "the cheap expand/compact check the spec calls for" (SHACL shape
  validation explicitly deferred, not attempted, since no shape is declared for the KG yet).
  Pinned: `test_jsonld_export.py::test_malformed_export_raises_never_ships`,
  `::test_validate_jsonld_export_raises_http_exception_directly`,
  `::test_jsonld_export_round_trips_to_isomorphic_graph`,
  `::test_jsonld_export_empty_graph_is_valid`.

## Design note (not a behavior): claim authorship is absent from every export surface

No export surface — not `iter_export_records`, not any of its six emitters, not the KG's RDF
export — emits a claim's AUTHOR or provenance kind (`created_by`/`provenance_kind`) today.
Verified precisely: `iter_export_records`'s claim record (`export_service.py:198-214`) carries
`text`/`claim_type`/`epistemic_status`/`entity_ids`/`metadata`/`source_document_id`/
`source_page_label`/`source_excerpt` — no authorship field at all; `resolve_claim_provenance_
kind` (`knowledge/_common.py`) is never called from `export_service.py` or `sparql.py`. This is
recorded as a design note, not a GAP behavior: none of the 25 issues read in this pass's fold
ask for a claim's AUTHORSHIP in an export — several ask for "provenance" as a first-class
column, but that is the "Found in" document/page/expediente LOCATION provenance
`export.one-stream-feeds-every-record-emitter` above already provides, a different sense of
the word from who-wrote-it.

**Ruled direction for the day a real ask lands**: export the STORED value under its own name
(`created_by`, exactly as the engine wrote it) and any DERIVED value under a clearly SEPARATE
name (e.g. `provenance_kind_derived`) — never substituted for each other in the same field.
PROV-O can express both honestly: an attribution (`prov:wasAttributedTo`) is asserted by the
writer; an inferred fact is the output of a derivation activity (`prov:wasDerivedFrom` /
`prov:Activity`) — the RDF export's schema.org context would need its own extension or a
second named context to carry either, since schema.org itself has no native attribution-vs-
derivation vocabulary.

## PASS 2 fold plan (not executed — no issues moved)

Legacy milestones **#14 "Exporter"** (14 open) and **#212 "Exporter - Static Site"** (11 open)
— 25 open issues total, selected by milestone NUMBER (not title, per the ledger's own method
note) — not yet read issue-by-issue against the behaviors above; that reading is Pass 2's job.
A first read while researching this spec's own grounding suggests several clusters: a
Hugging-Face-dataset-export ask repeated across at least three issues (some predating the
DuckDB-not-PyArrow ruling and still framed around PyArrow); a large "Export → GitHub" publish
sub-system (9 issues on #212 — device-flow auth, a static-site scaffold, 3-way reimport merge,
grouped undo) that reads as its own spec's territory, built ON TOP OF the Eleventy emitter
rather than being this spec's own behavior; two `fichero-web` architecture issues that are not
about export at all; and at least three issues (`#470` shared export infrastructure, `#1645`
KG RDF export endpoints, `#2180` one-source-two-emitters) that describe exactly what Section A
and D above already confirm is built — verify-close candidates, not fresh GAPs. Not decided
here — Pass 1 was the ask.
