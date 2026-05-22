# STATE.md — Fichero

## Snapshot

**Branch: 0.0.2** · Clean working tree, all verification-gate fixes committed.

## Next Session — Start Here

1. **Run `/session-start` script** to load context files (SOUL.md → MEMORY.md → STATE.md).
2. **Decide direction:**
   - **Continue autoloop** — `~/code/autoloop/bin/worker-loop.sh ~/code/fichero-0.0.2 3` on fresh `agent-work/queue.md`.
   - **Fix autoloop timeout** — workers timeout before commits (60s default). Consider `cascade_loop.py --timeout 7200`.
   - **Vision roadmap** — Issues #1156-1161 created but blocked with `needs-design` label.
3. **ACTIVE THREAD — verification gate complete.** `scripts/verify_python.sh` returns ALL PASS. Swift build + 245 tests pass.
4. **Gotchas:** SwiftLint config updated for current project paths; workers execute tools but need more time per issue.

**Engine / typed contract:**
- `Database.save()` MUST use DuckDB `ON CONFLICT (id) DO UPDATE SET … = EXCLUDED.…` — `INSERT OR REPLACE` crashes uvicorn (#1120).
- `_resolve_write_target()` (catalogue.py) is the canonical "where do KG/artifact writes attach" helper — falls back to selected doc (#1087/#1105).
- `initialize_token()` is idempotent — reuses existing `.api-key` if present (#1110).
- Every extractor-emitted claim has non-None `subject_canonical` + `predicate_verb` + `object_phrase`. `+heuristic-svo` model suffix when heuristic ran (#1113).
- `_generate_resumen()` returns `tuple[str, list[str]]` from BOTH single-shot AND map-reduce paths. Caller must unpack (#840 fix landed 2026-05-17).
- `client.py::_expect_list(raw, path)` is the contract — typed list methods raise on wrong-shape responses.
- Never raw SQL outside `db.py` / typed store layers.

**Architecture:**
- Backend = logic; CLI / SwiftUI / iPad / web = display surfaces. KG/entity logic stays in engine.
- Hermeneutics ≠ KG (separate epistemic layers). Hermeneutic objects reference KG by id; don't fold either into the other (#1126).
- `process_vision`: PDF text-layer short-circuit BEFORE skip-if-artifact cache check (#1064).
- `document_inspector._build_knowledge_graph` follows `merged_into_id` (#1068).
- `entity_inspector._compose_entity_summary` builds entity-level summary — never echo a claim's text/predicate (#1050).

**Process:**
- One issue per commit, directly to `0.0.2`; no per-task branches (CLAUDE.md rule 7).
- Per-commit gates: pytest + ruff via test-runner subagent; code-reviewer on diff; silent-failure-hunter on error-handling changes.
- jcodemunch first for code-exploration — never Read/Grep/Glob on `.py`/`.swift`/`.ts` source.
- Subagents on Sonnet; orchestrator on Opus.
