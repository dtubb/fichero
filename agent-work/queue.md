# Worker Queue — 0.0.2 autonomous loop
# Generated: 2026-05-18 (Round 2 curator pass)
# Done this round: #743 #1061 #764 #1038

# ── Priority 1: Small bugs / quick wins (≤15k tokens) ────────────────────────

- issue: 1042
  status: done
  title: "Workflow editor doesn't draw the merge→catalogue edge and shows '0 connections'"
  files: [fichero/fichero/Views/WorkflowEditor/WorkflowCanvasView.swift, fichero/fichero/Views/WorkflowEditor/]
  approach: "Fix port-position lookup so merge-node output port key resolves correctly; edge should render and connection count should reflect actual edge list."
  est_tokens: 15000
  blocked_reason: null
  commit: 19246138
  completed_at: 2026-05-18T23:27:36-03:00

- issue: 1040
  status: done
  title: "Activity Progress tab shows wrong node as running — says Transcribe while Extract runs"
  files: [fichero/fichero/Views/Activity/]
  approach: "Clear a node's running indicator when its completed event arrives before marking the next node running; fix ordering in SSE event handler."
  est_tokens: 12000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 1048
  status: blocked
  title: "Activity: add a per-node timing summary so runs can be optimized"
  files: [fichero/fichero/Views/Activity/]
  approach: "Compute elapsed time per workflow node from SSE start/end events and display a timing breakdown in the simplified Activity view (#1038 is done — 4-tab layout now in place)."
  est_tokens: 14000
  blocked_reason: "Free OpenRouter worker hallucinated on this twice — cross-cutting backend timing + UI card scope exceeds single-iteration capacity. Needs splitting or Sonnet/Opus."
  commit: null
  completed_at: null

- issue: 1045
  status: blocked
  title: "Activity Overview: show the document × step grid (like workflow Output Log), not a flat file list"
  files: [fichero/fichero/Views/Activity/]
  approach: "Replace the flat file list in Activity Overview with a 2D grid where rows are documents and columns are workflow nodes. #1038 done — do now."
  est_tokens: 15000
  blocked_reason: "Free worker iter 5 implemented grid UI but stubbed workflow fetch with hardcoded extract/classify/files nodes — couldnt wire to backend WorkflowServiceGenerated. Needs Sonnet-tier or scope split (backend prerequisite first)."
  commit: null
  completed_at: null

- issue: 1024
  status: done
  title: "PDF viewer needs its own zoom toolbar mirroring the image viewer's ImageZoomToolbar"
  files: [fichero/fichero/Views/Document/]
  approach: "Add PDFZoomToolbar wired to the existing PDFZoomController bridge; expose fit-to-page / fit-to-width / zoom-in / zoom-out. Gate for #928."
  est_tokens: 14000
  blocked_reason: null
  commit: 00dde49f
  completed_at: 2026-05-19

- issue: 730
  status: done
  title: "KG claims: SVO-style claim text + structured triples in metadata"
  files: [fichero-engine/src/fichero/models/knowledge.py, fichero-engine/src/fichero/kg/_common.py, fichero-engine/src/fichero/db.py]
  approach: "Add svo_subject/svo_verb/svo_object fields to KnowledgeClaim via _ensure_table (0.0.x no-migration rule); populate from extract_all output using slug_verb from _common.py. Gate for #1036."
  est_tokens: 14000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 1036
  status: done
  title: "Make claim SVO display easier to read and click — tappable subject / verb / object chips"
  files: [fichero/fichero/Views/KG/]
  approach: "Render claim subject/verb/object as three individually-tappable chips with distinct styling; do after #730 ensures backend SVO fields exist."
  est_tokens: 13000
  blocked_reason: "workers exhausted: ['shipped']"
  commit: null
  completed_at: 2026-05-22

- issue: 958
  status: in_progress
  title: "Artifacts inspector: structured outputs (NER, classifications) shouldn't be rendered as editable RTF"
  files: [fichero/fichero/Views/Inspector/]
  approach: "Detect artifact type in the inspector; route structured JSON artifacts to a read-only formatted view instead of the RTF editor."
  est_tokens: 14000
  blocked_reason: null
  commit: null
  completed_at: null

# ── Priority 2: Medium bugs / contained features (15–20k tokens) ─────────────

- issue: 1031
  status: done
  title: "KG viewer claim source link does nothing — page-child sourceDocumentId not resolved on navigation"
  files: [fichero/fichero/Views/KG/, fichero-engine/src/fichero/api/routes/documents.py]
  approach: "Resolve page-child sourceDocumentId to parent document ID before navigation; add /documents/{id}/parent endpoint if Swift cannot resolve alone."
  est_tokens: 18000
  blocked_reason: "verify_diff mismatch: empty response"
  commit: "b78f72d7"
  completed_at: "2026-05-19T12:28:00Z"

- issue: 1071
  status: done
  commit: dcb3a6fc
  title: "KG entities in document inspector: source-scoped aggregation + navigation + filter/search"
  files: [fichero/fichero/Views/Inspector/, fichero-engine/src/fichero/api/routes/kg.py]
  approach: "Add ?document_id filter to KG entities endpoint; wire inspector entity list to source-scoped query and navigation-to-entity tap. Companion to #1031."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-21T07:44:57.620962

- issue: 768
  status: done
  title: "Workflow editor: migrate provider picker from legacy LLMProvider to OpenAPI-typed ProviderResponse"
  files: [fichero/fichero/Views/WorkflowEditor/]
  approach: "Replace legacy LLMProvider enum binding in workflow editor provider picker with OpenAPI-typed ProviderResponse from the API client. Do before #797 and #1059."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-21

- issue: 797
  status: done
  title: "Workflow run context-menu: model picker submenu (Transcribe → Provider → Model)"
  files: [fichero/fichero/Views/WorkflowEditor/, fichero/fichero/Views/Library/]
  approach: "Add a nested submenu to the workflow context menu for per-node provider/model selection; wire to existing LLM config path. Do after #768."
  est_tokens: 15000
  blocked_reason: null
  commit: dcb3a6fc
  completed_at: 2026-05-21

- issue: 735
  status: blocked
  title: "Pre-run cost estimate on workflow execute button"
  files: [fichero/fichero/Views/WorkflowEditor/, fichero-engine/src/fichero/api/routes/workflows.py]
  approach: "Add a /workflows/{id}/estimate endpoint returning token/cost estimate from node configs; surface as an info badge on the run button."
  est_tokens: 16000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 1052
  status: blocked
  title: "Color-code KG entities vs. searchable terms in the document/library view"
  files: [fichero/fichero/Views/Document/, fichero/fichero/Views/Library/]
  approach: "Assign distinct highlight colors per entity type (person/place/concept) in the document text view; add a legend chip in the toolbar."
  est_tokens: 16000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 732
  status: blocked
  title: "Surface provider-side errors clearly in the UI (quota / 429 / model-not-found / auth)"
  files: [fichero-engine/src/fichero/api/routes/workflows.py, fichero/fichero/Views/WorkflowEditor/]
  approach: "Normalize provider error codes in API routes into structured error responses; surface as distinct labelled error messages in the workflow run UI."
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1085
  status: blocked
  title: "Maps importer: pair sidecar .iffy.json files with their image/PDF on ingest"
  files: [fichero-engine/src/fichero/ingest/]
  approach: "During ingest, detect sibling <name>.iffy.json and persist its contents as metadata on the Document; use _ensure_table pattern (0.0.x no-migration rule)."
  est_tokens: 18000
  blocked_reason: "workers exhausted: ['no_commit', 'timed_out']"
  commit: null
  completed_at: null

- issue: 1044
  status: blocked
  title: "PDF per-page progress isn't visible during a workflow run — page-child rows don't spin"
  files: [fichero/fichero/Views/Activity/, fichero-engine/src/fichero/api/routes/workflow_execution.py]
  approach: "Emit per-page SSE progress events during transcription; display them as a sub-progress indicator under the parent document in Activity."
  est_tokens: 20000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1111
  status: blocked
  title: "KG: deterministic paragraph rendering with bidirectional citation links"
  files: [fichero-engine/src/fichero/kg/, fichero-engine/src/fichero/api/routes/kg.py]
  approach: "Build a renderer composing subject + slug_verb + object into deterministic prose paragraphs with source citations; expose via /kg/render endpoint. Reuse slug_verb from kg/_common.py."
  est_tokens: 18000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

# ── Priority 3: Larger features (20k+ tokens) ─────────────────────────────────

- issue: 868
  status: done
  title: "Theme A: LLMProvider abstraction layer"
  files: [fichero-engine/src/fichero/api/routes/, fichero-engine/src/fichero/workflows/]
  approach: "Refactor LLMProvider into a provider interface + registry; centralise provider resolution so all workflow nodes use a single path. Gate for #1059 and unified picker."
  est_tokens: 22000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-21

- issue: 928
  status: blocked
  title: "PDF pages: surface the same loupe / magnifier / image-preview tools we have for images"
  files: [fichero/fichero/Views/Document/]
  approach: "Extend PDFViewer to host LoupeView overlay and image-preview toolbar, mirroring ImageViewer. Do after #1024 (zoom toolbar provides the PDF infra)."
  est_tokens: 16000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1032
  status: blocked
  title: "Unify search into one always-visible top search bar with consistent scope (documents + vectors + KG)"
  files: [fichero/fichero/Views/Search/, fichero/fichero/Views/ContentView.swift]
  approach: "Add a single top-level SearchBar visible in all modes; route queries to the unified search endpoint with scope toggle chips."
  est_tokens: 20000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 874
  status: blocked
  title: "User-extensible entity types (registry + dynamic extraction + UI auto-generation)"
  files: [fichero-engine/src/fichero/models/knowledge.py, fichero-engine/src/fichero/api/routes/kg.py, fichero-engine/src/fichero/db.py]
  approach: "Add EntityTypeRegistry table via _ensure_table; CRUD endpoints; inject custom types into extraction prompt at runtime. Do before #916 and #1102."
  est_tokens: 22000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1102
  status: blocked
  title: "User-extensible epistemic statuses + claim kinds (registry, companion to #874)"
  files: [fichero-engine/src/fichero/models/knowledge.py, fichero-engine/src/fichero/api/routes/kg.py, fichero-engine/src/fichero/db.py]
  approach: "Add EpistemicStatus and ClaimKind registry tables with seed defaults; CRUD endpoints; plumb into KnowledgeClaim model. Use _ensure_table (no ALTER TABLE). Do alongside/after #874."
  est_tokens: 20000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 916
  status: done
  title: "KG: user-created entities / claims / annotations (full CRUD parity with extractor-emitted)"
  files: [fichero-engine/src/fichero/api/routes/kg.py, fichero-engine/src/fichero/models/knowledge.py, fichero/fichero/Views/KG/]
  approach: "Add POST/PATCH/DELETE endpoints for KnowledgeEntity and KnowledgeClaim alongside existing GET; plumb CRUD into the SwiftUI KG inspector panel. Do after #1102."
  est_tokens: 22000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-21

- issue: 1059
  status: blocked
  title: "Consolidate model/provider selection — ~6 separate picker UIs, inconsistent behaviour"
  files: [fichero/fichero/Views/Settings/, fichero/fichero/Views/WorkflowEditor/]
  approach: "Audit all 6 provider/model picker sites; extract a single ModelProviderPicker component reused everywhere. Do after #768, #797, and #868."
  est_tokens: 22000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 926
  status: blocked
  title: "Translation + modernization workflow nodes: archaic → modern, source → user language"
  files: [fichero-engine/src/fichero/workflows/nodes/, fichero-engine/src/fichero/workflows/tools/]
  approach: "Add translate_node and modernize_node using LLM with configurable source/target language; follow the existing node pattern (catalogue.py as template)."
  est_tokens: 22000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 1101
  status: blocked
  title: "Bibliographic metadata: add canonical BibTeX field + import-time sidecar reader (.bib / .ris / .csl.json / Zotero)"
  files: [fichero-engine/src/fichero/ingest/, fichero-engine/src/fichero/models/document.py, fichero-engine/src/fichero/db.py]
  approach: "Add bibtex_raw column to Document via _ensure_table; parse .bib/.ris/.csl.json sidecars at ingest and store normalized BibTeX string."
  est_tokens: 25000
  blocked_reason: "workers exhausted: ['no_commit']"
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

- issue: 1148
  status: blocked
  title: "arch: unify Swift/CLI/engine on the OpenAPI contract (CLI bypasses it; generated Python client is dead code)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 1147
  status: blocked
  title: "test: contract test that every endpoint's response actually validates against its response_model"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 1146
  status: blocked
  title: "Embed MLX Swift for local Qwen3-VL 8B / Nanonets-OCR-s; investigate Chandra"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1145
  status: blocked
  title: "Add OCR / HTR model options: Qwen3-VL 8B, Chandra, Nanonets-OCR-s, Gemini 3, GPT-5"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1144
  status: done
  title: "type envelope ListResponses with concrete element types (followup to #1075)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-21

- issue: 1142
  status: blocked
  title: "[security] Upgrade liquidjs to >=10.25.7 — CVE-2026-41311 (circular block DoS, high severity)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 1135
  status: blocked
  title: "SwiftUI KG editor: edit, delete, merge, split entities and claims in-app"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 1133
  status: blocked
  title: "AppleScript bridge: programmatic UI control for autonomous dev/test loop"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1124
  status: done
  title: "Hermeneutics: controlled predicate vocabulary distinct from KG verbs (centers / decenters / contests_reading / etc)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 1118
  status: blocked
  title: "NER: multi-provider abstraction (LLM + spaCy + HuggingFace transformers) with per-claim provider attribution"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1115
  status: blocked
  title: "Workflow architecture: make KG-write an explicit node (transcribe → extract → catalogue → kg_writer)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1103
  status: blocked
  title: "References as first-class entities: DuckDB table + backend API + researcher-agent dispatch"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1100
  status: blocked
  title: "Citation extraction workflow: port pdf2bib end-to-end + footnote/in-page citations + inspector panel"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 1098
  status: done
  title: "Catalogue: bulk 'catalogue each selected folder' fan-out (500 folders → 500 catalogues)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 1095
  status: blocked
  title: "Bidirectional client compute: SwiftUI clients claim work from a server queue and post back results"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1094
  status: blocked
  title: "Web client calling the engine"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 1093
  status: blocked
  title: "iPad / iOS client app calling the engine"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1092
  status: blocked
  title: "Multi-user with write permissions (the engine is single-user today)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1091
  status: blocked
  title: "SwiftUI undo system that includes navigation undo (Cmd-Z restores prior view)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1090
  status: blocked
  title: "Undo / rollback for artifacts"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 1089
  status: blocked
  title: "Changelog: per-artifact + per-document audit log"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 1072
  status: done
  title: "Audit the whole SwiftUI codebase for logic that belongs in the backend — frontend should only display"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 975
  status: blocked
  title: "Structured transcript ingest: timecoded segments + speaker diarization as artifacts"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 974
  status: done
  title: "Citation graph: link in-text citation → bibliography entry → claim, surfaced per-doc AND library-wide"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 973
  status: blocked
  title: "Book-aware page numbering + chapter markers for PDFs and folders (Apple Intelligence detection)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 972
  status: blocked
  title: "Core ML on-device personalization: classifiers that learn from user curation (merge / accept / type decisions)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 970
  status: blocked
  title: "OCR bounding boxes: persist per-text-region bbox from Apple Vision + cloud OCR, tie KG claims to them"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 969
  status: blocked
  title: "Future: more robust engine auth — design for remote (Tailscale / mTLS) and harden the local token path"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 968
  status: blocked
  title: "iPad / iPhone client app talking to a remote Fichero engine (via Tailscale or similar)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 938
  status: blocked
  title: "Transcribe-as-composable-workflow: multi-model ensemble + thinking step + add $thinking default tier"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 924
  status: blocked
  title: "Citation + source-tier extraction with role-tagged entities (grammar-constrained)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 902
  status: done
  title: "KG SwiftUI-native visualisation: force-directed graph + Charts + Map place layer"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 878
  status: blocked
  title: "Semantic embedding map visualisation (2D projection of doc cloud)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 877
  status: blocked
  title: "RAG Q&A workflow (Apple Intelligence + hybrid retrieval)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 876
  status: blocked
  title: "Int8 quantization for LanceDB embeddings (100K+ doc scale)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 875
  status: blocked
  title: "Hybrid BM25 + BGE-M3 retrieval (RRF beyond cosine)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 854
  status: blocked
  title: "Apple Intelligence: proactive token budgeting (waiting on SDK 26.4)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 821
  status: blocked
  title: "Foundation toolkit: Tool protocol — let Apple Intelligence call back into the KG"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 801
  status: blocked
  title: "Chunk inputs to summarize_file / summarize_folder / summarize_collection / rewrite / analyze for on-device LLMs"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 799
  status: done
  title: "fm-bridge: GenerationSchema for guaranteed structured output (per-extractor schemas)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 760
  status: blocked
  title: "Bash-launched Fichero binary doesn't get window/scene activation on macOS 26"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 756
  status: blocked
  title: "Analysis tool: Language identification"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 755
  status: blocked
  title: "Analysis tool: Plagiarism / near-duplicate detection across library"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 754
  status: done
  title: "Analysis tool: Sentiment classifier"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 753
  status: blocked
  title: "Add 'Detect AI Text' workflow tool (desklib/ai-text-detector-v1.01)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 752
  status: blocked
  title: "Settings → Local Models tab: enable + download/manage local model weights"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 751
  status: blocked
  title: "Workflow context menu: group Run Workflow submenu by folder_path (#722 part 2)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['timed_out']"
  commit: null
  completed_at: null

- issue: 744
  status: blocked
  title: "Tinderbox importer: link a .tbx file → ingest notes into vector DB + KG"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 741
  status: blocked
  title: "Search v2.5: local RAG Q&A workflow (Apple Intelligence + hybrid retrieval)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 740
  status: blocked
  title: "GraphRAG (parked): evaluate nano-graphrag with Apple Intelligence at corpus scale"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: []"
  commit: null
  completed_at: null

- issue: 739
  status: blocked
  title: "Ingest: resumable corpus pass with content-hash skip (100K-scale)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 738
  status: blocked
  title: "Search index: int8 quantization for LanceDB at 100K-doc scale"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 737
  status: blocked
  title: "Search v2.1: alias-aware entity query expansion"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 736
  status: blocked
  title: "Search v2: hybrid BM25 + BGE-M3 retrieval (reciprocal rank fusion)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 734
  status: blocked
  title: "Surface ModelComparisonService — 'Compare models' workflow run UI"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit']"
  commit: null
  completed_at: null

- issue: 733
  status: blocked
  title: "First-run wizard: 'Use the cheapest model that works' framing"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: "workers exhausted: ['no_commit', 'no_commit']"
  commit: null
  completed_at: null

- issue: 721
  status: done
  title: "Inspector shows parent folder's container artifacts (Dates/Events/Keywords/etc.) on selected child page"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 720
  status: done
  title: "Catalogue (composable) workflow finishes without a combined catalogue artifact — only emits per-entity outputs"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 719
  status: pending
  title: "Eager-prefetch thumbnails for the *currently selected folder* only (not whole library)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 718
  status: pending
  title: "Icon list thumbnails snap to square aspect when only one row visible (should preserve image aspect ratio)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 717
  status: pending
  title: "Grid icon click: preview updates but selected-icon highlight doesn't move to clicked item"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 716
  status: pending
  title: "Add 'Paleography Transcribe' workflow: multi-step reasoning transcription for old Spanish documents"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 715
  status: pending
  title: "Inspector RTF text editor: standard macOS text-editing shortcuts (option-left/right, etc.) don't work"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 714
  status: pending
  title: "Workflow Templates 'Install Defaults' undercounts: alert says '2 installed' when 5 templates are present"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 713
  status: done
  title: "Sidebar drag asymmetry: icon/name vs row-body produce different drag sessions inside DisclosureGroup"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: 2026-05-22

- issue: 712
  status: pending
  title: "Remove center preview pane; folder inspector when nothing selected"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 711
  status: pending
  title: "Sidebar drag: unify icon/text + row-body drag paths via .draggable Transferable (#598 follow-up)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 710
  status: pending
  title: "Test: ArtifactPanel RTF encode/decode round-trip (#688 follow-up)"
  files: []
  approach: ""
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null
