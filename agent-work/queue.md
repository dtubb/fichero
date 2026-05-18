# Worker Queue — 0.0.2 autonomous loop
# Generated: 2026-05-18

# ── Priority 1: Small bugs (≤12k tokens) ─────────────────────────────────────

- issue: 759
  status: pending
  title: "Engine startup: log Bundle.main.bundlePath so multi-install users know which Fichero is running"
  files: [fichero-engine/src/fichero/api/main.py]
  approach: "Add a startup log line emitting the engine binary path at INFO level on boot."
  est_tokens: 6000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 758
  status: pending
  title: "BackendConnectionView: detect engine startup failure, don't cycle 'Almost ready…' forever"
  files: [fichero/fichero/Views/]
  approach: "Add a timeout + retry-limit to the health-poll loop; display an actionable error state with a Restart Engine button after N failed polls."
  est_tokens: 10000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 783
  status: pending
  title: "Loupe (image viewer magnifier) not working properly"
  files: [fichero/fichero/Views/]
  approach: "Debug LoupeView / ImageViewer magnification calculation; fix coordinate mapping from window space to image space."
  est_tokens: 12000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 795
  status: pending
  title: "Sidebar folder click doesn't update inspector when a doc is currently previewed"
  files: [fichero/fichero/Views/]
  approach: "Force-clear the previewed document binding when a folder is selected so the inspector refreshes to folder context."
  est_tokens: 12000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1046
  status: pending
  title: "Search results icon view shows a generic placeholder, never the page thumbnail"
  files: [fichero/fichero/Views/]
  approach: "Wire the search result row to fetch and display the document's page thumbnail instead of the generic document icon."
  est_tokens: 12000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1008
  status: pending
  title: "KG Tools menu items (Embed claims / Embed entities / Generate suggested links) should run automatically, not be user-triggered"
  files: [fichero/fichero/Views/]
  approach: "Wire KG tool triggers to WorkflowExecutionObserver.workflowCompletedCount so they fire automatically post-run instead of requiring manual menu selection."
  est_tokens: 12000
  blocked_reason: null
  commit: null
  completed_at: null

# ── Priority 2: Medium bugs (12–20k tokens) ──────────────────────────────────

- issue: 1042
  status: pending
  title: "Workflow editor doesn't draw the merge→catalogue edge and shows '0 connections'"
  files: [fichero/fichero/Views/WorkflowEditor/]
  approach: "Fix edge-source lookup to correctly resolve the merge node output port so the catalogue connection renders and connection count is correct."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1040
  status: pending
  title: "Activity Progress tab shows wrong node as running — says Transcribe while Extract runs"
  files: [fichero/fichero/Views/]
  approach: "Fix node-state update to clear a node's running indicator when its completed event arrives, before marking the next node running."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1036
  status: pending
  title: "Make claim SVO display easier to read and click — tappable subject / verb / object chips"
  files: [fichero/fichero/Views/]
  approach: "Render claim subject/verb/object as three individually-tappable chips with distinct styling instead of a composed sentence string."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1045
  status: pending
  title: "Activity Overview: show the document × step grid (like workflow Output Log), not a flat file list"
  files: [fichero/fichero/Views/]
  approach: "Replace the flat file list in Activity Overview with a 2D grid where rows are documents and columns are workflow nodes."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1048
  status: pending
  title: "Activity: add a per-node timing summary so runs can be optimized"
  files: [fichero/fichero/Views/]
  approach: "Compute elapsed time per workflow node from SSE events and display a timing breakdown in the Activity detail view."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1024
  status: pending
  title: "PDF viewer needs its own zoom toolbar mirroring the image viewer's ImageZoomToolbar"
  files: [fichero/fichero/Views/]
  approach: "Add a PDFZoomToolbar component wired to the existing PDFZoomController bridge; expose fit-to-page / fit-to-width / zoom-in / zoom-out."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 958
  status: pending
  title: "Artifacts inspector: structured outputs (NER, classifications) shouldn't be rendered as editable RTF"
  files: [fichero/fichero/Views/]
  approach: "Detect artifact type in the inspector and route structured JSON artifacts to a read-only formatted view instead of the RTF editor."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 764
  status: pending
  title: "Workflow run: backend appears frozen until activity finally shows up"
  files: [fichero/fichero/Views/]
  approach: "Show an immediate 'Starting…' progress indicator as soon as the run request is posted, before the first SSE event arrives."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 879
  status: pending
  title: "401s from running app despite token file in place — investigate auth path"
  files: [fichero-engine/src/fichero/api/, fichero/fichero/Services/]
  approach: "Trace the token read path on both client (Swift) and server (FastAPI middleware); confirm token file location matches what the engine startup writes."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 928
  status: pending
  title: "PDF pages: surface the same loupe / magnifier / image-preview tools we have for images"
  files: [fichero/fichero/Views/]
  approach: "Extend PDFViewer to host LoupeView overlay and image-preview toolbar, mirroring the existing ImageViewer implementation."
  est_tokens: 16000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1052
  status: pending
  title: "Color-code KG entities vs. searchable terms in the document/library view"
  files: [fichero/fichero/Views/]
  approach: "Assign distinct highlight colors per entity type (person/place/concept) in the document text view; add a legend chip in the toolbar."
  est_tokens: 16000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1031
  status: pending
  title: "KG viewer claim source link does nothing — page-child sourceDocumentId not resolved on navigation"
  files: [fichero/fichero/Views/, fichero-engine/src/fichero/api/documents.py]
  approach: "Resolve page-child sourceDocumentId to parent document ID before navigation; add /documents/{id}/parent endpoint if Swift cannot resolve alone."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1071
  status: pending
  title: "KG entities in document inspector: source-scoped aggregation + navigation + filter/search"
  files: [fichero/fichero/Views/, fichero-engine/src/fichero/api/]
  approach: "Add ?document_id filter to KG entities endpoint; wire inspector entity list to source-scoped query and add navigation-to-entity tap."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1085
  status: pending
  title: "Maps importer: pair sidecar .iffy.json files with their image/PDF on ingest"
  files: [fichero-engine/src/fichero/ingest/]
  approach: "During ingest, detect sibling <name>.iffy.json and persist its contents as metadata on the Document; use _ensure_table pattern (0.0.x no-migration rule)."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1044
  status: pending
  title: "PDF per-page progress isn't visible during a workflow run — page-child rows don't spin"
  files: [fichero/fichero/Views/, fichero-engine/src/fichero/api/]
  approach: "Emit per-page SSE progress events during transcription; display them as a sub-progress bar under the parent document in the Activity view."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

# ── Priority 3: Larger bugs + contained features (18–30k tokens) ──────────────

- issue: 1038
  status: pending
  title: "Activity view is too complex — 8 tabs, much of it low-value; simplify to what users actually need"
  files: [fichero/fichero/Views/]
  approach: "Audit all 8 Activity tabs for usage; collapse low-value tabs into 3-4 tabs (Overview grid, Progress, Log, Timing)."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1111
  status: pending
  title: "KG: deterministic paragraph rendering with bidirectional citation links"
  files: [fichero-engine/src/fichero/kg/, fichero-engine/src/fichero/api/]
  approach: "Build a renderer composing subject + slug_verb + object into deterministic prose paragraphs with source citations; expose via /kg/render endpoint."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1032
  status: pending
  title: "Unify search into one always-visible top search bar with consistent scope (documents + vectors + KG)"
  files: [fichero/fichero/Views/]
  approach: "Add a single top-level SearchBar visible in all modes; route queries to the unified search endpoint with scope toggle chips."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1102
  status: pending
  title: "User-extensible epistemic statuses + claim kinds (registry, companion to #874)"
  files: [fichero-engine/src/fichero/models/, fichero-engine/src/fichero/api/, fichero-engine/src/fichero/db.py]
  approach: "Add EpistemicStatus and ClaimKind registry tables with seed defaults; CRUD endpoints; plumb into KnowledgeClaim model. Use _ensure_table pattern (no ALTER TABLE)."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1059
  status: pending
  title: "Consolidate model/provider selection — ~6 separate picker UIs, inconsistent behaviour"
  files: [fichero/fichero/Views/]
  approach: "Audit all 6 provider/model picker sites; extract a single ModelProviderPicker component reused everywhere with consistent state."
  est_tokens: 22000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 926
  status: pending
  title: "Translation + modernization workflow nodes: archaic → modern, source → user language"
  files: [fichero-engine/src/fichero/workflows/nodes/, fichero-engine/src/fichero/workflows/tools/]
  approach: "Add translate_node and modernize_node using LLM with configurable source/target language; follow the existing node pattern (catalogue.py as template)."
  est_tokens: 22000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 975
  status: pending
  title: "Structured transcript ingest: timecoded segments + speaker diarization as artifacts"
  files: [fichero-engine/src/fichero/ingest/, fichero-engine/src/fichero/models/]
  approach: "Parse .srt/.vtt/.sbv as timecoded segment arrays; persist speaker+timestamp metadata per segment as Artifacts."
  est_tokens: 25000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1101
  status: pending
  title: "Bibliographic metadata: add canonical BibTeX field + import-time sidecar reader (.bib / .ris / .csl.json / Zotero)"
  files: [fichero-engine/src/fichero/ingest/, fichero-engine/src/fichero/models/, fichero-engine/src/fichero/db.py]
  approach: "Add bibtex_raw column to Document via _ensure_table; parse .bib/.ris/.csl.json sidecars at ingest and store normalized BibTeX string."
  est_tokens: 25000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1043
  status: pending
  title: "Dependency audit + update sweep (langchain/langgraph et al.) — post-0.0.2"
  files: [fichero-engine/requirements.txt, fichero-engine/pyproject.toml]
  approach: "Run pip-audit + pip list --outdated; update langchain/langgraph/litellm/lancedb to latest compatible; run unit tests to confirm nothing breaks."
  est_tokens: 8000
  blocked_reason: null
  commit: null
  completed_at: null

# ── Blocked (architecture decision needed — do not pick up) ───────────────────

- issue: 873
  status: blocked
  title: "pytest integration test: workflow-execution end-to-end"
  files: [fichero-engine/tests/integration/, fichero-engine/tests/fixtures/]
  approach: "Write pytest test that boots fixture-managed backend, posts Catalogue workflow, polls thread to terminal, asserts status/nodes/artifacts."
  est_tokens: 20000
  blocked_reason: "Requires novel pause/resume pattern for interactive workflow execution. Architecture decision needed: pause mechanism, decision storage, SSE interactive protocol."
  commit: null
  completed_at: null

- issue: 1097
  status: blocked
  title: "Catalogue: human-in-the-loop confirmation for ambiguous groupings"
  files: [fichero-engine/src/fichero/workflows/nodes/catalogue.py, fichero-engine/src/fichero/api/]
  approach: "Add HITL interrupt after grouping-proposal step; surface candidate groupings via SSE for user confirmation before committing catalogue artifacts."
  est_tokens: 28000
  blocked_reason: "Same blocker as #873: requires novel pause/resume pattern for interactive workflow. Architecture decision needed."
  commit: null
  completed_at: null

- issue: 971
  status: blocked
  title: "Cross-page paragraphs / quotes: NER loses context when text spans a page boundary"
  files: [fichero-engine/src/fichero/workflows/tools/extract_all.py, fichero-engine/src/fichero/ocr/]
  approach: "Overlap adjacent page text windows by configurable token margin before feeding extract_all so cross-boundary spans appear in at least one window."
  est_tokens: 20000
  blocked_reason: "Architecture review needed for cross-page dedup strategy; requires design for result merging to avoid duplicate entities/claims."
  commit: null
  completed_at: null
