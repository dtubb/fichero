# Worker Queue — 0.0.2 backend autonomous loop
# Generated: 2026-05-17

- issue: 840
  status: in_progress
  title: "Save per-chunk catalogue summaries as catalogue.chunk.N artifacts (transparency)"
  files: [fichero-engine/src/fichero/workflows/nodes/catalogue.py, fichero-engine/src/fichero/models/artifact.py]
  approach: "Emit one Artifact per chunk with type catalogue.chunk.N before final catalogue artifact; keep final artifact unchanged."
  est_tokens: 25000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 984
  status: pending
  title: "Backend: promote subject/verb/object from KnowledgeClaim.metadata to top-level DB columns"
  files: [fichero-engine/src/fichero/workflows/tools/extractors.py, fichero-engine/src/fichero/db.py, fichero-engine/src/fichero/models/]
  approach: "Add subject/verb/object columns to KnowledgeClaim table in db.py _ensure_table + Pydantic model, then update the extractors.py write path to use top-level fields; no ALTER TABLE needed."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 801
  status: pending
  title: "Chunk inputs to summarize_file / summarize_folder / summarize_collection / rewrite / analyze"
  files: [fichero-engine/src/fichero/workflows/tools/summarize.py, fichero-engine/src/fichero/workflows/tools/rewrite.py, fichero-engine/src/fichero/workflows/tools/analyze.py, fichero-engine/src/fichero/workflows/tools/classify_text.py]
  approach: "Apply the chunked map-reduce pattern already shipping in catalogue (#ea2c59e0) to summarize/rewrite/analyze/classify tools that currently send unbounded merged text to the LLM."
  est_tokens: 30000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 873
  status: pending
  title: "pytest integration test: workflow-execution end-to-end"
  files: [fichero-engine/tests/integration/, fichero-engine/tests/fixtures/]
  approach: "Write a pytest test that boots a fixture-managed backend, posts Catalogue workflow against a small fixture PDF, polls thread status to terminal, and asserts status/completed_nodes/artifacts."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 925
  status: pending
  title: "OCR cleanup workflow step: dehyphenate + rejoin columns + strip library stamps"
  files: [fichero-engine/src/fichero/workflows/nodes/, fichero-engine/src/fichero/workflows/tools/]
  approach: "Add an OCR-cleanup node that runs post-Vision text through dehyphenation, column-rejoin, and stamp-stripping before passing to downstream extraction nodes."
  est_tokens: 22000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1096
  status: pending
  title: "Catalogue: case grouping (sub-group docs into cases inside a folder)"
  files: [fichero-engine/src/fichero/workflows/nodes/catalogue.py, fichero-engine/src/fichero/api/]
  approach: "Add optional case_id metadata field to Document; extend catalogue resolver to group by case_id and emit one catalogue artifact per case rather than per folder."
  est_tokens: 25000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1097
  status: pending
  title: "Catalogue: human-in-the-loop confirmation for ambiguous groupings"
  files: [fichero-engine/src/fichero/workflows/nodes/catalogue.py, fichero-engine/src/fichero/api/]
  approach: "Add a HITL interrupt after the grouping-proposal step that surfaces candidate groupings via SSE for user confirmation before committing catalogue artifacts."
  est_tokens: 28000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1098
  status: pending
  title: "Catalogue: bulk 'catalogue each selected folder' fan-out (500 folders)"
  files: [fichero-engine/src/fichero/workflows/nodes/catalogue.py, fichero-engine/src/fichero/api/workflows.py]
  approach: "Add selection-aware fan-out mode using LangGraph Send API to dispatch one catalogue sub-run per folder from a single workflow invocation."
  est_tokens: 35000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 971
  status: pending
  title: "Cross-page paragraphs / quotes: NER loses context when text spans a page boundary"
  files: [fichero-engine/src/fichero/workflows/tools/extract_all.py, fichero-engine/src/fichero/ocr/]
  approach: "Overlap adjacent page text windows by a configurable token margin before feeding to extract_all so spans crossing page boundaries appear in at least one extraction window."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1115
  status: pending
  title: "Workflow architecture: make KG-write an explicit node (transcribe → extract → KG)"
  files: [fichero-engine/src/fichero/workflows/nodes/, fichero-engine/src/fichero/workflows/tools/extract_all.py, fichero-engine/src/fichero/kg/]
  approach: "Refactor extract_all to return entities/claims without writing to DB, then add a discrete kg_write node downstream that owns all KnowledgeEntity/KnowledgeClaim DB writes."
  est_tokens: 30000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1124
  status: pending
  title: "Hermeneutics: controlled predicate vocabulary distinct from KG verbs"
  files: [fichero-engine/src/fichero/kg/hermeneutics.py, fichero-engine/src/fichero/kg/_common.py]
  approach: "Define a HermeneuticPredicate enum in hermeneutics.py for interpretive-move verbs (argues, challenges, extends…) separate from slug_verb KG predicates; update extractors to use it."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 924
  status: pending
  title: "Citation + source-tier extraction with role-tagged entities (grammar-constrained)"
  files: [fichero-engine/src/fichero/workflows/tools/, fichero-engine/src/fichero/workflows/nodes/]
  approach: "Add a citation-extraction tool that role-tags author/title/publisher/date via grammar-constrained LLM output and persists structured citation records as Artifacts."
  est_tokens: 35000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 974
  status: pending
  title: "Citation graph: link in-text citation → bibliography entry → claim"
  files: [fichero-engine/src/fichero/workflows/tools/, fichero-engine/src/fichero/kg/, fichero-engine/src/fichero/db.py]
  approach: "Build citation-graph edges in DuckDB linking in-text citation spans to bibliography KnowledgeClaims; expose via /kg/citations endpoint."
  est_tokens: 40000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1118
  status: pending
  title: "NER: multi-provider abstraction (LLM + spaCy + HuggingFace transformers)"
  files: [fichero-engine/src/fichero/workflows/tools/extract_all.py, fichero-engine/src/fichero/workflows/tools/]
  approach: "Define a NERBackend protocol with LLM/spaCy/HuggingFace implementations; route per-document to cheapest capable backend and merge results before KG write."
  est_tokens: 40000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 868
  status: pending
  title: "LLMProvider abstraction layer (consolidate chat/chat_structured/chat_with_tools)"
  files: [fichero-engine/src/fichero/workflows/tools/, fichero-engine/src/fichero/llm/]
  approach: "Create a unified LLMProvider class with shared timeout/error handling that wraps all five chat variants; migrate call sites to it incrementally."
  est_tokens: 50000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 874
  status: pending
  title: "User-extensible entity types (registry + dynamic extraction)"
  files: [fichero-engine/src/fichero/workflows/tools/extract_all.py, fichero-engine/src/fichero/kg/, fichero-engine/src/fichero/api/]
  approach: "Replace hardcoded entity-type Pydantic schemas in extract_all with a runtime registry that builds grammar/prompts dynamically from user-defined EntityType DB records."
  est_tokens: 45000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1108
  status: pending
  title: "MCP server: expose the engine to MCP-aware agents"
  files: [fichero-engine/src/fichero/api/, fichero-engine/src/fichero/]
  approach: "Add an MCP transport layer (stdio or SSE) re-exporting existing engine endpoints as MCP tools, reusing the same client.py auth path."
  est_tokens: 35000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 975
  status: pending
  title: "Structured transcript ingest: timecoded segments + speaker diarization"
  files: [fichero-engine/src/fichero/ingest/, fichero-engine/src/fichero/models/]
  approach: "Parse .srt/.vtt/.sbv as timecoded segment arrays; persist speaker+timestamp metadata per segment; surface jump-to-position anchors in transcript Artifacts."
  est_tokens: 25000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 926
  status: pending
  title: "Translation + modernization workflow nodes"
  files: [fichero-engine/src/fichero/workflows/nodes/, fichero-engine/src/fichero/workflows/tools/]
  approach: "Add translate_node and modernize_node workflow nodes using LLM with configurable source/target language and archaic-to-modern system instructions."
  est_tokens: 22000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 970
  status: pending
  title: "OCR bounding boxes: persist per-text-region bbox from Apple Vision"
  files: [fichero-engine/src/fichero/ocr/, fichero-engine/src/fichero/models/]
  approach: "Capture VNRecognizedTextObservation bounding boxes from the Vision OCR path and persist as metadata on page Document records for click-to-region navigation."
  est_tokens: 25000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1049
  status: pending
  title: "Workflow editor: nodes are spaced too far apart on the canvas"
  files: [fichero/fichero/Views/]
  approach: "Reduce the horizontal spacing constant in the workflow canvas layout algorithm so nodes fit without panning."
  est_tokens: 12000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1042
  status: pending
  title: "Workflow editor doesn't draw the merge→catalogue edge and shows '0 connections'"
  files: [fichero/fichero/Views/]
  approach: "Fix edge-source lookup to correctly resolve the merge node output port so the catalogue connection renders and connection count is reported correctly."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1040
  status: pending
  title: "Activity Progress tab shows wrong node as running — says Transcribe while Extract runs"
  files: [fichero/fichero/Views/]
  approach: "Fix node-state update to clear a node's running indicator when its completed event arrives, before marking the next node as running."
  est_tokens: 15000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1044
  status: pending
  title: "PDF per-page progress isn't visible during a workflow run — page-child docs not surfaced"
  files: [fichero/fichero/Views/, fichero-engine/src/fichero/api/]
  approach: "Emit per-page SSE progress events during transcription and display them as a sub-progress bar under the parent document in the Activity view."
  est_tokens: 20000
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

- issue: 1034
  status: pending
  title: "KG entities list pane is too wide and resize isn't persisted"
  files: [fichero/fichero/Views/]
  approach: "Store entity-pane width in AppStorage with a narrower default; replace any .inspector() usage with the ResizableDivider + HStack pattern."
  est_tokens: 12000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1070
  status: pending
  title: "Pane widths (list view, inspector) jump around between views — width state not persisted"
  files: [fichero/fichero/Views/]
  approach: "Move pane-width @State to shared AppStorage keys so widths survive navigation transitions and app restarts."
  est_tokens: 12000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 961
  status: pending
  title: "Console hygiene: CoreGraphics NaN errors + FocusedValue multi-update warnings"
  files: [fichero/fichero/Views/]
  approach: "Guard geometry values before CoreGraphics calls to prevent NaN; wrap FocusedValue updates in DispatchQueue.main.async to silence multi-update warnings."
  est_tokens: 10000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1031
  status: pending
  title: "KG viewer claim source link does nothing — page-child sourceDocumentId needs parent lookup"
  files: [fichero/fichero/Views/, fichero-engine/src/fichero/api/]
  approach: "Resolve page-child sourceDocumentId to its parent document ID before navigation; add /documents/{id}/parent endpoint if the Swift layer cannot resolve it alone."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 834
  status: done
  title: "Apple Vision OCR returns empty silently on hard pages — log + retry-with-fast-level"
  files: [fichero-engine/src/fichero/ocr/, fichero-engine/src/fichero/transcribe/]
  approach: "On empty Vision result, log warning + retry at .fast recognition level; surface error if still empty after retry."
  est_tokens: 18000
  blocked_reason: null
  commit: e89d8725
  completed_at: 2026-05-17T14:18:00Z

- issue: 1085
  status: blocked
  title: "Maps importer: pair sidecar .iffy.json files with their image/PDF on ingest"
  files: [fichero-engine/src/fichero/ingest/]
  approach: "During ingest, detect sibling <name>.iffy.json and persist its contents as metadata on the Document; no schema migration needed."
  est_tokens: 20000
  blocked_reason: "trace-mcp Python index returning zero search results — cannot locate ingest module symbols for safe implementation"
  commit: null
  completed_at: null
