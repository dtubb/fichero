# STATE.md — Fichero

## Snapshot

**Branch: 0.0.2** · Latest: `ff3a9cf1` · Working tree clean.

✅ **Backend Milestone FULLY COMPLETE** — All Rounds 1–3 verified complete (May 16, 8:54 PM):
  - Round 1: 4 architectural fixes (#1001, #1025, #1017, #988) ✓
  - Round 2: 6 verification sweep (all already fixed) ✓
  - Round 3: 3 post-test bugs (all closed: #1136, #1137, #1138) ✓

## Tooling Now Available

- **Knowledge graph at `graphify-out/`** (built 2026-05-16) — query the codebase via `/graphify query "..."`, `/graphify explain "LLMConfig"`, or `/graphify path "FicheroClient" "Database"`. ~17K nodes / 30K edges over fichero/ + fichero-engine/ (831 code files). ~50× cheaper than grepping.

## Next Session — Start Here

**All 0.0.2 milestones completed through CLI + backend standardization (May 17, 8:51 AM)**. 

**Completed in this session:**
- #1140: CLI typed response models (12 methods)
- #1141: CLI formatters (specialized renderers)
- #1132: Engine lifecycle commands
- #1131: Library registry persistence ← backend blocker
- #1130: Library lifecycle CLI (8 commands)
- #1075: List endpoint standardization (51+ endpoints, 33 models)

**Decision point:**
1. **Ship 0.0.2 → main** (backend milestone fully complete, CLI/backend APIs type-safe)
2. **Continue with Round 5** backend work (#1054/#1108 and other unblocked items in backlog)
3. **Begin SwiftUI milestone** (#1135 KG editor, #1133 AppleScript bridge)

## In Progress

None — all CLI tasks complete. Awaiting direction on next milestone.

## Completed (This Session & Prior)

- **#1137** — CLI entity documents formatter (FIXED: d2f4ebde, closed)
- **#1136** — CLI entity_neighborhood wrong URL path (FIXED: cebf5efd, closed)
- **#1037** — extract_all performance instrumentation (already fixed)
- **#1033** — transcribe text-layer short-circuit (already fixed in 7ef16274)
- **#1001** — permissive_guardrails for extractors (Apple Intelligence false-positives)
- **#1025** — local PYPPETEER diagram rendering (drop mermaid.ink remote API)
- **#1017** — extractor schema round-trip + invariant violation tests
- **#988 step 3** — probabilistic entity-match scoring with auto-merge thresholds

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
