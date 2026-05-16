# STATE.md — Fichero

## Snapshot

**Branch: 0.0.2** · Latest: `7b352c02` · Working tree clean.

CLI test loop operational end-to-end. SVO + provider/model attribution per claim verified live on Apple Intelligence (14/14). Wave 1 module consolidation shipped (-5,378 LOC). CLI Wave 2 CRUD complete (40 typed methods).

## Tooling Now Available

- **Knowledge graph at `graphify-out/`** (built 2026-05-16) — query the codebase via `/graphify query "..."`, `/graphify explain "LLMConfig"`, or `/graphify path "FicheroClient" "Database"`. ~17K nodes / 30K edges over fichero/ + fichero-engine/ (831 code files). ~50× cheaper than grepping. Run `/graphify --update` if the branch has moved substantially since.

## Next Session — Start Here

1. **Tonight's autonomous-loop command** (sonnet — Opus monthly limit hit):
   ```
   sleep 3.5h && caffeinate -dimsu python3 /Users/danieltubb/code/fichero-skills/agent-autonomous-loop.py \
   /Users/danieltubb/code/fichero-0.0.2 \
   --agent claude --model claude-sonnet-4-6 --effort auto \
   --iterations 25 --sleep 999 --max-tasks 2 \
   --claude-show-thinking \
   --start-extra "Wave 2 of 0.0.2 KG completeness — see STATE.md Wave 2 backlog."
   ```

2. **Wave 2 priority order**:
   - **#1123** attribution taxonomy (12 claim fields + KnowledgeClaimLink wiring + canonical KG verbs in `kg/_common.py::CANONICAL_VERBS`)
   - **#1114** entity quality (dedup / grounding / hallucinated events)
   - **#1119** claim.entity_ids[] covers every mentioned entity, not just subject
   - **#1121** _entity_writer Stage 1↔4 race (transaction or unique constraint)
   - **#1125** scoped KG exploration CLI (page / doc / folder / library navigation + embedding integration)
   - **#1126** hermeneutics fold redo (preserve existing test contract)
   - **#1124** hermeneutic predicates (separate from KG verbs)
   - **#1128** schema-fold + no-migration project rule docs
   - **#1127** workflow cancel endpoint

3. **Skip** #1054 + #1057 (need product decisions).

4. **No-migration window**: schema changes go in `db.py` CREATE TABLE directly; nuke + recreate `~/Documents/fichero-loop-test.fichero` to pick up. (Documented in MEMORY.md 2026-05-16.)

5. **Loop verification corpus**: `/tmp/fichero-loop-corpus/` has 20 staged md files (~9.4k words) from `~/code/slipbox/coded`. After each Wave 2 commit that touches the extractor or KG schema, re-import + run NER and confirm SVO still 14/14 (or higher with the new fields populated).

## In Progress

None — Wave 2 hasn't started; tonight's autonomous loop will pick up.

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
