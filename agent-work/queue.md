# Worker Queue — 0.0.2 autonomous loop
# Generated: 2026-05-18

# ── Priority 1: Small bugs / quick wins (≤12k tokens) ────────────────────────

- issue: 743
  status: done
  title: "Engine: lazy-import heavy ML modules to drop cold-start from 25s to ~3s"
  files: [fichero-engine/src/fichero/api/main.py, fichero-engine/src/fichero/workflows/nodes/]
  approach: "langgraph imports already moved (aa7a3be2); verify + move any remaining torch/spacy/transformers imports inside the functions that use them."
  est_tokens: 10000
  blocked_reason: null
  commit: a3ee484d
  completed_at: 2026-05-18T22:25:39-03:00

- issue: 1061
  status: done
  title: "Establish a QA review process — review agents (frontend/backend/security) + offload build/lint/test to subagents"
  files: [docs/agent-workflow/, agent-work/]
  approach: "Document the QA review gate in docs/agent-workflow/parallel-execution.md; write constitution snippets for backend-reviewer, silent-failure-hunter, code-reviewer teammates; wire into commit flow."
  est_tokens: 10000
  blocked_reason: null
  commit: b0d78e77
  completed_at: 2026-05-18T22:31:21-03:00

# ── Priority 2: Medium bugs (12–20k tokens) ──────────────────────────────────

- issue: 764
  status: done
  title: "Workflow run: backend appears frozen until activity finally shows up"
  files: [fichero/fichero/Views/Activity/, fichero/fichero/Views/WorkflowEditor/]
  approach: "Show an immediate 'Starting…' progress indicator as soon as the run request is posted, before the first SSE event arrives."
  est_tokens: 15000
  blocked_reason: null
  commit: 1b56d84d
  completed_at: 2026-05-18T22:42:16-03:00

- issue: 1038
  status: pending
  title: "Activity view is too complex — 8 tabs, much of it low-value; simplify to what users actually need"
  files: [fichero/fichero/Views/Activity/]
  approach: "Audit all 8 Activity tabs; collapse low-value tabs into 3-4 tabs (Overview grid, Progress, Log, Timing). Do #1038 before #1045 and #1048."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

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
  files: [fichero/fichero/Views/Activity/]
  approach: "Fix node-state update to clear a node's running indicator when its completed event arrives, before marking the next node running."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1045
  status: pending
  title: "Activity Overview: show the document × step grid (like workflow Output Log), not a flat file list"
  files: [fichero/fichero/Views/Activity/]
  approach: "Replace the flat file list in Activity Overview with a 2D grid where rows are documents and columns are workflow nodes. Do after #1038."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1048
  status: pending
  title: "Activity: add a per-node timing summary so runs can be optimized"
  files: [fichero/fichero/Views/Activity/]
  approach: "Compute elapsed time per workflow node from SSE events and display a timing breakdown in the Activity detail view. Do after #1038."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1024
  status: pending
  title: "PDF viewer needs its own zoom toolbar mirroring the image viewer's ImageZoomToolbar"
  files: [fichero/fichero/Views/Document/]
  approach: "Add a PDFZoomToolbar component wired to the existing PDFZoomController bridge; expose fit-to-page / fit-to-width / zoom-in / zoom-out."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 958
  status: pending
  title: "Artifacts inspector: structured outputs (NER, classifications) shouldn't be rendered as editable RTF"
  files: [fichero/fichero/Views/Inspector/]
  approach: "Detect artifact type in the inspector and route structured JSON artifacts to a read-only formatted view instead of the RTF editor."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 928
  status: pending
  title: "PDF pages: surface the same loupe / magnifier / image-preview tools we have for images"
  files: [fichero/fichero/Views/Document/]
  approach: "Extend PDFViewer to host LoupeView overlay and image-preview toolbar, mirroring the existing ImageViewer implementation. Do after #1024 (PDF infra)."
  est_tokens: 16000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1036
  status: pending
  title: "Make claim SVO display easier to read and click — tappable subject / verb / object chips"
  files: [fichero/fichero/Views/KG/]
  approach: "Render claim subject/verb/object as three individually-tappable chips with distinct styling instead of a composed sentence string."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1052
  status: pending
  title: "Color-code KG entities vs. searchable terms in the document/library view"
  files: [fichero/fichero/Views/Document/, fichero/fichero/Views/Library/]
  approach: "Assign distinct highlight colors per entity type (person/place/concept) in the document text view; add a legend chip in the toolbar."
  est_tokens: 16000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1031
  status: pending
  title: "KG viewer claim source link does nothing — page-child sourceDocumentId not resolved on navigation"
  files: [fichero/fichero/Views/KG/, fichero-engine/src/fichero/api/routes/documents.py]
  approach: "Resolve page-child sourceDocumentId to parent document ID before navigation; add /documents/{id}/parent endpoint if Swift cannot resolve alone."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1071
  status: pending
  title: "KG entities in document inspector: source-scoped aggregation + navigation + filter/search"
  files: [fichero/fichero/Views/Inspector/, fichero-engine/src/fichero/api/routes/kg.py]
  approach: "Add ?document_id filter to KG entities endpoint; wire inspector entity list to source-scoped query and add navigation-to-entity tap. Companion to #1031."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 768
  status: pending
  title: "Workflow editor: migrate provider picker from legacy LLMProvider to OpenAPI-typed ProviderResponse"
  files: [fichero/fichero/Views/WorkflowEditor/]
  approach: "Replace legacy LLMProvider enum binding in workflow editor provider picker with the OpenAPI-typed ProviderResponse from the API client. Do before #797 and #1059."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 797
  status: pending
  title: "Workflow run context-menu: model picker submenu (Transcribe → Provider → Model)"
  files: [fichero/fichero/Views/WorkflowEditor/, fichero/fichero/Views/Library/]
  approach: "Add a nested submenu to the workflow context menu that lets users pick a provider and model per-node before running; wire to existing LLM config path. Do after #768."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 735
  status: pending
  title: "Pre-run cost estimate on workflow execute button"
  files: [fichero/fichero/Views/WorkflowEditor/, fichero-engine/src/fichero/api/routes/workflows.py]
  approach: "Add a /workflows/{id}/estimate endpoint returning token/cost estimate from node configs; surface as an info badge on the run button before execution begins."
  est_tokens: 16000
  blocked_reason: null
  commit: null
  completed_at: null

# ── Priority 3: Larger bugs + contained features (18–30k tokens) ──────────────

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
  files: [fichero/fichero/Views/Activity/, fichero-engine/src/fichero/api/routes/workflow_execution.py]
  approach: "Emit per-page SSE progress events during transcription; display them as a sub-progress bar under the parent document in the Activity view."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1032
  status: pending
  title: "Unify search into one always-visible top search bar with consistent scope (documents + vectors + KG)"
  files: [fichero/fichero/Views/Search/, fichero/fichero/Views/ContentView.swift]
  approach: "Add a single top-level SearchBar visible in all modes; route queries to the unified search endpoint with scope toggle chips."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1059
  status: pending
  title: "Consolidate model/provider selection — ~6 separate picker UIs, inconsistent behaviour"
  files: [fichero/fichero/Views/Settings/, fichero/fichero/Views/WorkflowEditor/]
  approach: "Audit all 6 provider/model picker sites; extract a single ModelProviderPicker component reused everywhere with consistent state. Do after #768 and #797."
  est_tokens: 22000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1111
  status: pending
  title: "KG: deterministic paragraph rendering with bidirectional citation links"
  files: [fichero-engine/src/fichero/kg/, fichero-engine/src/fichero/api/routes/kg.py]
  approach: "Build a renderer composing subject + slug_verb + object into deterministic prose paragraphs with source citations; expose via /kg/render endpoint. Reuse slug_verb from kg/_common.py."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1102
  status: pending
  title: "User-extensible epistemic statuses + claim kinds (registry, companion to #874)"
  files: [fichero-engine/src/fichero/models/knowledge.py, fichero-engine/src/fichero/api/routes/kg.py, fichero-engine/src/fichero/db.py]
  approach: "Add EpistemicStatus and ClaimKind registry tables with seed defaults; CRUD endpoints; plumb into KnowledgeClaim model. Use _ensure_table pattern (no ALTER TABLE)."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 916
  status: pending
  title: "KG: user-created entities / claims / annotations (full CRUD parity with extractor-emitted)"
  files: [fichero-engine/src/fichero/api/routes/kg.py, fichero-engine/src/fichero/models/knowledge.py, fichero/fichero/Views/KG/]
  approach: "Add POST/PATCH/DELETE endpoints for KnowledgeEntity and KnowledgeClaim alongside existing GET; plumb CRUD into the SwiftUI KG inspector panel. Do after #1102."
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

- issue: 1101
  status: pending
  title: "Bibliographic metadata: add canonical BibTeX field + import-time sidecar reader (.bib / .ris / .csl.json / Zotero)"
  files: [fichero-engine/src/fichero/ingest/, fichero-engine/src/fichero/models/document.py, fichero-engine/src/fichero/db.py]
  approach: "Add bibtex_raw column to Document via _ensure_table; parse .bib/.ris/.csl.json sidecars at ingest and store normalized BibTeX string."
  est_tokens: 25000
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
  files: [fichero-engine/src/fichero/workflows/nodes/catalogue.py, fichero-engine/src/fichero/api/routes/]
  approach: "Add HITL interrupt after grouping-proposal step; surface candidate groupings via SSE for user confirmation before committing catalogue artifacts."
  est_tokens: 28000
  blocked_reason: "Depends on #873: requires novel pause/resume pattern for interactive workflow. Architecture decision needed."
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
