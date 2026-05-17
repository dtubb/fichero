# Worker Queue — 0.0.2 backend autonomous loop
# Generated: 2026-05-17

- issue: 1117
  status: done
  title: "Cleanup: 3 minor write-path bypasses from the DuckDB audit"
  files: [fichero-engine/src/fichero/api/main.py, fichero-engine/src/fichero/db.py]
  approach: "Replace raw SQL INSERTs with Pydantic model writes for the 3 sites called out in the audit; add regression test."
  est_tokens: 30000
  blocked_reason: null
  commit: 33f0cc64
  completed_at: 2026-05-17T11:54:00Z

- issue: 1112
  status: done
  title: "Audit: Pydantic-only DuckDB writes (find raw-SQL bypasses)"
  files: [fichero-engine/src/fichero/db.py, fichero-engine/src/fichero/api/, fichero-engine/src/fichero/]
  approach: "Grep-audit raw INSERT/UPDATE/UPSERT outside db.py; emit report markdown listing bypasses; companion to #1117."
  est_tokens: 25000
  blocked_reason: null
  commit: 49678b18
  completed_at: 2026-05-17T11:52:00Z

- issue: 984
  status: done
  title: "Promote subject/verb/object from KnowledgeClaim.metadata to top-level fields"
  files: [fichero-engine/src/fichero/models/knowledge_claim.py, fichero-engine/src/fichero/db.py, fichero-engine/src/fichero/kg/]
  approach: "Add subject/verb/object Pydantic fields on KnowledgeClaim; backfill via _ensure_table (0.0.x no-migration rule); update _entity_writer + queries."
  est_tokens: 45000
  blocked_reason: null
  commit: 798bb940
  completed_at: 2026-05-17T11:55:00Z

- issue: 1102
  status: blocked
  title: "User-extensible epistemic statuses + claim kinds (registry)"
  files: [fichero-engine/src/fichero/models/, fichero-engine/src/fichero/api/main.py, fichero-engine/src/fichero/db.py]
  approach: "Create epistemic_status + claim_kind registry tables (mirror known_libraries pattern); REST endpoints; default-seed values."
  est_tokens: 50000
  blocked_reason: "trace-mcp server stack overflow on all queries; cannot understand code structure"
  commit: null
  completed_at: null

- issue: 1101
  status: blocked
  title: "Bibliographic metadata: canonical BibTeX field + import-time sidecar reader"
  files: [fichero-engine/src/fichero/models/document.py, fichero-engine/src/fichero/ingest/, fichero-engine/src/fichero/db.py]
  approach: "Add bibtex field on Document; sidecar .bib reader on ingest; persist via _ensure_table."
  est_tokens: 40000
  blocked_reason: "trace-mcp server stack overflow on all queries; cannot understand code structure"
  commit: null
  completed_at: null

- issue: 841
  status: in_progress
  title: "744 unit tests fail with 'Reject non-loopback request from testclient'"
  files: [fichero-engine/src/fichero/api/main.py, fichero-engine/tests/conftest.py]
  approach: "Adjust loopback middleware to accept TestClient's 'testserver' Host header or whitelist in test config."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 840
  status: in_progress
  title: "Save per-chunk catalogue summaries as catalogue.chunk.N artifacts"
  files: [fichero-engine/src/fichero/workflows/nodes/catalogue.py, fichero-engine/src/fichero/models/artifact.py]
  approach: "Emit one Artifact per chunk with type catalogue.chunk.N before final catalogue artifact; keep final artifact unchanged."
  est_tokens: 25000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 801
  status: in_progress
  title: "Chunk inputs to summarize_file / summarize_folder / summarize_collection / rewrite"
  files: [fichero-engine/src/fichero/workflows/nodes/, fichero-engine/src/fichero/tools/]
  approach: "Wrap LLM-input assembly in a chunk-and-merge helper; reuse catalogue's chunker; preserve order."
  est_tokens: 30000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 834
  status: in_progress
  title: "Apple Vision OCR returns empty silently — log + retry-with-fast-level"
  files: [fichero-engine/src/fichero/ocr/, fichero-engine/src/fichero/transcribe/]
  approach: "On empty Vision result, log warning + retry at .fast recognition level; surface error if still empty."
  est_tokens: 18000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1085
  status: in_progress
  title: "Maps importer: pair sidecar .iffy.json files with image/PDF on ingest"
  files: [fichero-engine/src/fichero/ingest/]
  approach: "During ingest, detect sibling <name>.iffy.json and persist as metadata on the Document."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1124
  status: in_progress
  title: "Hermeneutics: controlled predicate vocabulary distinct from KG verbs"
  files: [fichero-engine/src/fichero/kg/, fichero-engine/src/fichero/models/]
  approach: "Introduce HermeneuticPredicate registry; keep slug_verb path untouched; expose via API."
  est_tokens: 45000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1096
  status: in_progress
  title: "Catalogue: case grouping (sub-group docs into cases inside a folder)"
  files: [fichero-engine/src/fichero/workflows/nodes/catalogue.py]
  approach: "Add a case-grouping pass in the catalogue node; emit sub-group artifacts."
  est_tokens: 35000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 925
  status: in_progress
  title: "OCR cleanup workflow step: dehyphenate + rejoin columns + strip library footers"
  files: [fichero-engine/src/fichero/workflows/nodes/, fichero-engine/src/fichero/tools/]
  approach: "Add new workflow node post-transcribe that runs deterministic text cleanup; emit cleanup.text artifact."
  est_tokens: 35000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 971
  status: in_progress
  title: "Cross-page paragraphs / quotes: NER loses context when text spans a page break"
  files: [fichero-engine/src/fichero/kg/, fichero-engine/src/fichero/workflows/nodes/]
  approach: "Buffer last paragraph across page boundary in extract; emit unified spans tagged with originating pages."
  est_tokens: 40000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 975
  status: in_progress
  title: "Structured transcript ingest: timecoded segments + speaker diarization as artifacts"
  files: [fichero-engine/src/fichero/ingest/, fichero-engine/src/fichero/models/artifact.py]
  approach: "Detect transcript JSON/VTT; persist segments as transcript.segments artifact with start/end/speaker."
  est_tokens: 35000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1043
  status: in_progress
  title: "Dependency audit + update sweep (langchain/langgraph etc.)"
  files: [fichero-engine/pyproject.toml]
  approach: "pip-tools / uv pip compile to surface outdated; bump non-breaking; run full unit test suite."
  est_tokens: 30000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1115
  status: in_progress
  title: "Workflow architecture: make KG-write an explicit node"
  files: [fichero-engine/src/fichero/workflows/, fichero-engine/src/fichero/workflows/nodes/]
  approach: "Split extract_all so KG write is a separate kg_write node; keep extract pure; rewire graph edges."
  est_tokens: 55000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1108
  status: in_progress
  title: "MCP server: expose the engine to MCP-aware agents"
  files: [fichero-engine/src/fichero/, fichero-engine/pyproject.toml]
  approach: "Add fichero-mcp entry point wrapping client.py; tool schemas reuse Pydantic models."
  est_tokens: 55000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 1111
  status: in_progress
  title: "KG: deterministic paragraph rendering with bidirectional citation links"
  files: [fichero-engine/src/fichero/kg/]
  approach: "Render claims as paragraphs with stable ordering; emit subject-↔-claim anchors."
  est_tokens: 35000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 873
  status: in_progress
  title: "pytest integration test: workflow-execution end-to-end"
  files: [fichero-engine/tests/integration/]
  approach: "Add e2e test that posts a workflow, polls status, asserts artifacts + KG rows present."
  est_tokens: 25000
  blocked_reason: null
  commit: null
  completed_at: null
