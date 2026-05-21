# STATE.md — Fichero

## Snapshot

**Branch: 0.0.2** · Latest: `69cb6fcd` (jcodemunch migration) · Prior: `22e96e6e` (#840 shipped).

## Tooling

- **jcodemunch** — code-intelligence MCP, replaces trace-mcp (migrated 2026-05-17). Use `mcp__jcodemunch__*` tools (`search_symbols`, `get_file_outline`, `get_symbol_source`, `get_context_bundle`, `find_references`, `get_blast_radius`, `find_importers`, etc.) instead of Read/Grep/Glob for ALL code questions. Opening move per task: `mcp__jcodemunch__plan_turn { repo, query, model }`. Index at `~/.code-index/`; PostToolUse hooks auto-reindex.
- **Autonomous loop** — `~/code/autoloop/` (local-only repo). Run via `~/code/autoloop/bin/curator.sh <project>` then `~/code/autoloop/bin/worker-loop.sh <project> <N>`. Curator (Sonnet) pre-digests `raw-issues.json` → `issues-summary.md` to avoid Read-limit. Worker (Haiku) routes through jcodemunch via `minimal-mcp.json`. Latest run shipped #840.
- **.venv** — fresh Python 3.12 at `~/code/fichero-0.0.2/.venv`, `fichero-engine[dev]` editable installed. Activate with `source .venv/bin/activate`. NEVER alias to `.briefcase-venv` again — that was the symlink rot.

## Next Session — Start Here

1. **Check git state** — should be clean post-commit `69cb6fcd`. 0.0.2 is 837+ commits ahead of `origin/main`; release ceremony (#158-#165) hasn't run yet.
2. **Decide direction:**
   - **Continue autoloop** — `~/code/autoloop/bin/worker-loop.sh ~/code/fichero-0.0.2 3` on the freshly-curated `agent-work/queue.md`. Next pending is **#984 SVO promotion** (tight scope, no-migration, well-bounded).
   - **Start the release** — #158 → #164 → #165 (merge 0.0.2 → main).
   - **SwiftUI work** — #1135 KG editor, #1133 AppleScript bridge.
3. **ACTIVE THREAD — verification gate. Read `agent-work/verification-gate-handoff.md` FIRST.** Goal: ⌘U / one command runs lint+build+test across app+engine+CLI. `scripts/verify_python.sh` = single-source gate; `~/code/autoloop` `cascade_router.py` now calls it. Baseline 107→44 unit failures (2 real backend bugs already fixed: `save_claim` svo_*, CLI `workflow run --wait`). Get baseline to 0 before relying on the gate. Needs-Opus post-May-23: bucket F real 500s, `CrossLanguageGateTests.swift`, `verify_all.sh`, **verify KG works end-to-end** (reported broken).
   - Cadence loop (free): `cd ~/code/autoloop && .venv/bin/python bin/cascade_loop.py ~/code/fichero-0.0.2 --with-curator --with-reconcile --iterations 20` (use `check_level=minimal` until baseline green).
   - Vision roadmap (NOT rushing 0.0.2): GitHub #1153 — RAG agent, research agents+browser, RealityKit mind palace, KG browse, VisionPro/iPad, editing tools. Each needs its own spec before a free worker can build it.
   - Gotchas: jcodemunch + Xcode MCP can disconnect mid-session (fall back to grep/xcodebuild); SourceKit "No such module" = false positive, trust xcodebuild.

## In Progress

- **Cascade loop ready to run overnight** — verification gate complete (0 failures), free model working, vision issues created (#1156-1161, all `needs-design`).

## Blocked

- **#1054** (search relevance threshold) — pending, returns every page; needs scoring cutoff.
- **#183** Phase H end-to-end test on LFH_AHJM folder — pending.
- **Vision issues blocked** — #1156-1161 created but require specs and design before free workers can build (labeled `needs-design`).

## Don't Break (load-bearing invariants)

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
