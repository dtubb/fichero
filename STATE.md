# STATE.md — Fichero

## Snapshot

**Branch: 0.0.2** · Latest: `61ef2f10` · Working tree clean.

Interactive testing session complete. 5 SwiftUI + CLI bugs fixed. Hybrid vector search verified end-to-end via CLI. KG quality reviewed against real ethnographic documents.

## Tooling Now Available

- **Knowledge graph at `graphify-out/`** (built 2026-05-16) — query the codebase via `/graphify query "..."`, `/graphify explain "LLMConfig"`, or `/graphify path "FicheroClient" "Database"`. ~17K nodes / 30K edges over fichero/ + fichero-engine/ (831 code files). ~50× cheaper than grepping. Run `/graphify --update` if the branch has moved substantially since.

## Next Session — Start Here

1. **Remaining open 0.0.2 issues (CLI-testable first)**:
   - **#1082** — Page 2 of 2-page test PDF has no transcription artifact — check via CLI
   - **#1099** — Workflow tool: extract direct quotes with speaker attribution (backend)
   - **#1075** — API inconsistency: bare list vs paginated envelope (breaking change risk, defer)
   - **SwiftUI**: #1049 (workflow nodes spacing), #1042 (editor missing merge→catalogue edge), #1044 (per-page progress), #1040 (activity progress wrong node), #1070 (pane widths jump), #1036 (claim SVO readability), #1035/#1034 (KG viewer cosmetics)

2. **KG quality observations from fichero-loop-test** (2 completed docs):
   - No `person` entities extracted — "Don Antonio" is in `catalogue.keywords` but missing from the KG. Person extraction is the biggest gap.
   - Event alias confusion: "Filing of Petition" incorrectly aliased to "Repairing Water Pipes" entity.
   - After #1109 fix, tautological "is a X" claims are now filtered in the inspector.

3. **Build required before PR**: three-leg check — `swiftlint` + `xcodebuild` + `RunAllTests`. Last build was not run this session; swiftlint was clean.

4. **Loop verification corpus**: `fichero-loop-test.fichero` has 2 completed docs (20 total). Run NER on remaining 18 to expand the KG for further review.

## In Progress

None.

## Blocked

None right now. Watch for:
- Anthropic monthly limit on Opus (use sonnet for subagents).
- `~/Library/Application Support/Fichero/.api-key` clobbered by pytest if `initialize_token` rotation regressed (#1110 was the fix; keep an eye if 401s reappear).

## Don't Break (load-bearing invariants)

**Engine / typed contract:**
- `Database.save()` MUST use DuckDB `ON CONFLICT (id) DO UPDATE SET … = EXCLUDED.…` — `INSERT OR REPLACE` is not reliable upsert in DuckDB and crashes uvicorn (#1120).
- `_resolve_write_target()` (catalogue.py) is the canonical helper for "where do KG / artifact writes attach when no folder container resolves" — falls back to selected doc. Don't add a 5th call site that gates on raw `_resolve_container_doc` (#1087/#1105).
- `initialize_token()` is idempotent — reuses existing `.api-key` if present; rotation only via `force_rotate=True` or env var. Don't revert to unconditional rotation (#1110).
- Every claim written by the extractor MUST have non-None `subject_canonical` + `predicate_verb` + `object_phrase`. Heuristic fallback in `_synthesize_svo_fallback()` covers cases the LLM doesn't fill; `+heuristic-svo` model suffix surfaces this honestly to users (#1113).
- Never raw SQL outside `db.py` / typed store layers. The typed audit (`agent-work/proposals/duckdb-typed-audit-2026-05-15-v2.md`) lists the 4 known offenders; new violations must not creep in.
- `client.py::_expect_list(raw, path)` is the contract — typed list methods raise on wrong-shape responses, never silently coerce.

**Architecture:**
- Backend = logic; CLI / SwiftUI / future iPad / web = display surfaces. KG/entity logic stays in the engine.
- Hermeneutics ≠ KG. Separate epistemic layers — KG asserts facts; hermeneutics interprets. Hermeneutic objects reference KG by id (`claim_ids`, `entity_ids`). Don't fold either into the other (#1126 will redo the abortive Wave 1 fold).
- `process_vision`: PDF text-layer short-circuit runs BEFORE the skip-if-artifact cache check; cache check is gated on `not pdf_layer_used` (#1064). Don't reorder.
- `document_inspector._build_knowledge_graph` *follows* `merged_into_id` to the canonical entity — does NOT skip merged entities (#1068 under-count root cause). Don't revert.
- `entity_inspector._compose_entity_summary` builds `summary` as a deterministic entity-level line — must NEVER echo a claim's text/predicate (#1050).

**Process:**
- One issue per commit, directly to `0.0.2` branch (CLAUDE.md rule 7 — no per-task branches).
- Per-commit gates: pytest + ruff via test-runner subagent; code-reviewer subagent on diff; silent-failure-hunter when touching error handling.
- Subagents on **sonnet**; orchestrator on opus (when not limit-bound).
- When orchestrator context hits 200%+ : /session-end is cheaper than continuing.
