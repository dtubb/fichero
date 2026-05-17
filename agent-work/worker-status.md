# Backend Worker Status

## Queue (Rounds 1-3 — ALL COMPLETE ✓)
- [x] #1001 — permissive_guardrails for extractors
- [x] #1025 — drop mermaid.ink remote dependency
- [x] #1017 — extractor schema round-trip tests
- [x] #988  — entity resolution probabilistic scoring
- [x] #1037 — extract_all timing (already fixed)
- [x] #1033 — transcribe text layer short-circuit (already fixed)
- [x] #1030 — KG raw repr sanitizer (already fixed)
- [x] #1029 — quality gate (already fixed)
- [x] #1027 — StructuredDecodeError retry (already fixed)
- [x] #1020 — collapse catalogue workflows (already fixed)
- [x] #1136 — CLI neighborhood wrong URL path
- [x] #1137 — CLI entity documents renders '(item)'
- [x] #1138 — fastembed pooling (already fixed)

## Queue (Round 4 — CLI typed client + output)
- [x] #1139 — Generate typed Python client from openapi.json (drop hand-written URLs)
- [ ] #1140 — Audit + fix response model coverage (typed models end-to-end)
- [ ] #1141 — Improve CLI output formatting (entity/claim/doc renderers)

## Queue (Round 5 — overnight, after #1140/#1141 complete)
- [ ] #1054 — search relevance threshold (backend)
- [ ] #1108 — MCP server expose engine to agents
- [ ] #1075 — list endpoint envelope standardization (backend)
- [ ] #1071 — entity inspector source-scoped aggregation (SwiftUI — skip, flag for Daniel)
- [ ] #1070 — pane width jumping (SwiftUI — skip, flag for Daniel)
- [ ] #1049 — workflow editor node spacing (SwiftUI — skip, flag for Daniel)
- [ ] #1042 — missing merge→catalogue edge (SwiftUI — skip, flag for Daniel)
- [ ] #1040 — activity progress wrong node (SwiftUI — skip, flag for Daniel)
- [ ] #1036 — SVO readability (SwiftUI — skip, flag for Daniel)
- [ ] #1034 — KG list pane width (SwiftUI — skip, flag for Daniel)
- [ ] #1031 — claim source link (SwiftUI — skip, flag for Daniel)

## Current
next: #1140

## Attempts
{}

## Last Completed
#1139

## IMPORTANT
- Work through ONE issue per session
- Check if already fixed before implementing (grep first)
- #1139 must come before #1140 and #1141 — they depend on the generated client
- #1139: install openapi-python-client, generate from fichero-engine/tests/contracts/openapi.json, wire into cli/client.py, add to sync_openapi_schema.sh
- Tests: PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived -q
- Lint: ruff check fichero-engine/src/
- Pre-existing failure to ignore: test_routes_settings.py::TestResetAIDefaults
