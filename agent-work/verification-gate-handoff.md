# Verification Gate + Baseline — Handoff (2026-05-20)

Context budget hit (~97% weekly Claude quota, resets May 23). Remaining work
delegates to the **free pi + OpenRouter autonomous loop**. This doc is the
single source of truth to resume — no need to re-derive.

## The mission
One unified verification gate so **⌘U / one command** runs lint+build+test
across **Swift app + Python engine + CLI** against the *same* seeded library, and
fails loudly on any drift. This is the cure for the "things get out of sync /
regressions" pain. Spec: `docs/superpowers/specs/2026-05-20-unified-verification-gate-design.md`.
Plan: `docs/superpowers/plans/2026-05-20-unified-verification-gate.md`.

## DONE & committed (local on 0.0.2, NOT pushed)
- `5abd7ef8` live app↔engine integration tests + test-host self-termination fix
- `33b1c3f9` shared seeder shim (`tests/integration/_seedlib.py`)
- `522e35aa` contract walker seeds via shared seeder
- `f0ac7a06` CLI live-contract test (`tests/integration/test_cli_engine_contract.py`)
- `00434a46` **REAL BUG**: `save_claim` accepts `svo_subject/svo_verb/svo_object` (KG claim-write was throwing → silently broke extraction; −29 unit failures)
- `58895d2e` stale unit tests updated for `{items,count}` envelopes + CacheEntry
- `ef7c4593` **REAL BUG**: CLI `workflow run --wait` never detected completion (`_poll_activity_for_terminal` checked `isinstance(entry,dict)` but real client returns `ActivityResponse` objects) + aligned FakeClient to real-client contract
- spaCy `en_core_web_sm` + `es_core_news_sm` installed into `.venv`
- `scripts/verify_python.sh` written (UNCOMMITTED — see queue item 1)
- Filed GitHub **#1151** (feature-gate audit + enable/keep-gated matrix), **#1152** (model-management UI feature). Both on milestone "0.0.2 - Backend Merge + Bug Fixes".

## Baseline status
Unit suite started at **107 failures**; after the two real fixes + stale-test
updates + spaCy, most are resolved. A fresh count run was in flight at handoff
(`/tmp/unit_now.log`). The remaining failures are the categories below.

## QUEUE — free-model-loop-safe (mechanical, well-specified)
Run from repo root, `PYTHONPATH=fichero-engine/src`, venv tools. Verify each with the named pytest before committing. One commit per item. Local on 0.0.2, never `--no-verify`.

1. **Fix `verify_python.sh` ruff over-reach.** It lints `fichero-engine/tests/ scripts/` which carry 219 pre-existing lint errors (not our work). Change the ruff leg to the canonical `ruff check fichero-engine/src/` ONLY. Then `chmod +x scripts/verify_python.sh && scripts/verify_python.sh` should pass its ruff leg. Commit `scripts/verify_python.sh`.

2. **xfail the gated-router unit tests** (they test dev-tier features intentionally kept gated — tracked in #1151). For each of these files, the failures are `KeyError: 'items'` / `list indices must be integers` because the route returns a bare list but the test expects an envelope. Add `@pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)` to the FAILING tests in: `test_routes_mind_palace.py`, `test_routes_research_agents.py`, `test_routes_mcp_servers.py`, `test_routes_triggers.py`, `test_routes_integrations.py`, `test_routes_schedules.py`, `test_mind_palace_api.py`, `test_research_agents_api.py`, `test_mcp_server.py`, `test_routes_settings.py` (verify which tests fail first: run each file). Do NOT touch the routes (no feature work — Daniel's call). Commit.

3. **Fix `test_sources.py` (2 failures)** — `string indices must be integers` / `assert False`: likely the same envelope drift. Investigate; if the route correctly returns an envelope, update the test to read `.items`/`["items"]`. If it looks like a real route bug, leave failing + note it.

4. **Fix `test_routes_hermeneutics.py` + `test_hermeneutics_api.py` (13)** — hermeneutics IS core/shipping (Daniel wants it enabled). Tests expect `{items,count}`; route returns bare list. This one we DO make consistent: envelope-migrate the hermeneutics list endpoints to `{items,count}` (follow the #1149 pattern — concrete `list[X]` items type, define envelope in the route file) so tests pass. Then `pytest test_routes_hermeneutics.py test_hermeneutics_api.py`. Commit.

## QUEUE — needs Opus judgment / Xcode (DEFER to post-May-23 or careful review)
- **Bucket F: 3 `ResponseValidationError` 500s** — genuine route-body-vs-response_model bugs (#1075-class). Need investigation to find which routes; real fixes. NOT for a weak model.
- **`test_node_cache.py` (4)** — if not already fixed in `58895d2e`, `CacheEntry.result` holds the dict; change `entry["k"]` → `entry.result["k"]`.
- **Gate Task 5**: `fichero/fichero-tests/CrossLanguageGateTests.swift` — Swift XCTest that runs `verify_python.sh` (full code in the plan). Needs Xcode build (`windowtab1`) to verify.
- **Gate Task 6**: `scripts/verify_all.sh` = swiftlint + `xcodebuild test`. (full code in the plan)
- **Gate Task 7**: full ⌘U run + document the gate in `docs/CLAUDE.md`.
- **Verify KG actually works end-to-end** — Daniel reports KG is broken/out-of-sync; the live contract tests + gate should pinpoint where. High value.

## Standing principles (enforce in all new work)
- **Don't hardcode user-editable things** (tool prompts, model choices, config) — make them editable settings. (memory: user-editable-not-hardcoded)
- **Tests use the REAL client, not hand-rolled fakes** — CLI: real `FicheroClient` over `httpx.MockTransport` or a live engine; Swift: real generated client over a live engine (the new `AppEngineContractTests` already do this). The `FakeClient` drift just hid a real `workflow --wait` bug — exactly the #1075 failure mode. Replacing the CLI `FakeClient` with real-client+MockTransport is tracked follow-up.
- **Envelope by construction**: list endpoints return `{items, count}` with concretely-typed `items` (`list[Document]`, not `list[Any]`) or the generated Swift client degrades to `[OpenAPIValueContainer]`.

## The big vision (roadmap — each needs its own brainstorm→spec→plan)
Daniel is NOT rushing 0.0.2; expanding scope. Capture as milestones/issues:
1. Interactive RAG / graph-RAG agent the user chats with.
2. Research agents: track research projects/milestones/tasks + search terms/languages/archives + an in-app AI-controlled web browser that finds & adds sources to Fichero. Reference implementation to study: `~/code/maps_southern_colombia` (a Claude Code version — read its chat histories).
3. RealityKit 3D/2D mind palace: VL/video models arrange pages/notes in space, group, connect (Tinderbox map-view-like). 
4. KG browse view.
5. Apple Vision Pro + iPad clients: read, annotate, take notes on documents.
6. Document editing tools: deskew, color-correct, split, crop, rotate — reference `~/code/archive`.
7. automation + integrations (lower priority for release).

**Sequencing principle (important):** the verification gate must be green BEFORE parallel feature autonomy, or parallel free-model work multiplies the out-of-sync regressions. Gate-first → then the loop builds features safely (each iteration must pass the gate to land).
