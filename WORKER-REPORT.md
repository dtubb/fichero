# Worker report — AI Backend Hardening batch (auto-advanced)

Worker: Claude, in worktree `~/code/fichero-worktrees/ms-docs`, branch `lane/docs`.
Reset to `origin/main` at start. Commits authored as Claude, Co-Authored-By Daniel.
Nothing pushed; the manager merges.

## Milestone selection

Docs Review (#108) is drained: all 6 issues are implemented and merged from prior
batches, just not closed. Auto-advanced past the soonest-due milestones (Test
Coverage, API Surface & Test Harness, Observable Data Layer, Remote & Self-Hosting,
Developer Experience) because their open issues are Swift-client work needing Xcode,
EPICs, or design-blocked/needs-human items that cannot be implemented AND gated from
this worktree (Swift here is swiftlint-only; no build/test). Landed on **AI Backend
Hardening**, which has backend-Python work I can fully gate with ruff + pytest.

## Issue worked

### #2507 — replace silent fallbacks with raised/logged errors (backend slice)

Daniel's principle: silent fallbacks mask bugs; raise or log loudly, never silently
substitute a different target than requested (caused #2430).

I audited the issue's named highest-risk WRITE paths:

| path | finding |
|---|---|
| `POST /api/entities` upsert (`api/routes/entities.py`) | **BUG, fixed.** A provided `request.id` that was not found silently created a NEW entity under a different auto-generated id and returned 200. Now raises 404, matching the PATCH route. Create (no id) and update (valid id) unchanged. |
| entity merge (`kg_entity_curation.py merge_entities_impl`) | Already correct: raises 404 on missing absorber/absorbed, 409 on already-merged. |
| claim write paths (`api/routes/claims.py`) | No upsert-by-id; explicit `create_claim` + `patch_claim` (patch 404s on miss). No bug. |
| artifact/page save exemplar (`workflows/tools/llm_base.py save_artifact`) | Already hardened for #2430/#2513/#2540 (page-miss never reroutes to parent; fail-loud return-None). |
| extraction writer (`workflows/tools/_entity_writer.py upsert_entity`) | Intentional name-based fuzzy find-or-create (by design, #897/#899/#1907). Not the substitution anti-pattern. |

So the genuine remaining silent-substitution bug in the named cluster was the entity
upsert route. Fixed with regression tests. The broader 128 swallowing `except`
blocks across the engine are mostly benign defaults; a blanket sweep is out of scope
for one batch (high risk of changing intended behavior), so the issue stays open for
further targeted passes.

**Tests added** (`tests/unit/test_routes_entities.py`):
- `test_upsert_with_unknown_id_returns_404_not_silent_create` — unknown id 404s and
  writes no substitute row.
- `test_upsert_unknown_id_leaves_other_entities_untouched` — a failed upsert leaves
  existing rows intact.

## Gate results

- `ruff check` on the changed source: **clean**.
- `pytest` (engine venv, `PYTHONPATH=fichero-engine/src` → this worktree's src) on
  every upsert-touching suite: **135 passed** (`test_routes_entities`,
  `test_canonical_knowledge_routes`, `test_mcp_knowledge_adapters`, `test_mcp_tools`,
  `test_routes_mcp_tools`, `test_change_stream`, `test_multilingual_api`,
  `test_manifest_import`).
- No `.swift` touched.

## Commits

- `fix(kg): entity upsert 404s on unknown id instead of silent substitute (#2507)`
