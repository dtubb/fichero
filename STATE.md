# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed and clean. Swift client pipeline fully working.

**Status:** All route handlers have typed Pydantic response models. OpenAPI spec generates complete named schemas for all 448 endpoints. Swift client (`fichero-api-client`) builds cleanly from the spec. 1785 passing, 5 pre-existing failures. Lint clean.

## In Progress

Nothing active.

## Test Health

**1785 passing, 0 failures, 21 skipped.** All pre-existing failures resolved.

## Next Session — Start Here

1. **Release 0.0.1** — ship 0.0.1 before merging 0.0.2 into main.
2. **Then merge 0.0.2 → main** — branch is clean, tests green, Swift client pipeline working. Ready to merge once 0.0.1 is out.
3. **Start 0.0.4 milestone** — #372 claim review queue UI, #373 contradiction triage, #374 search metrics panel, #375 interpretations workspace.

---
*Last updated: 2026-04-14* — typed response model pass + Swift client pipeline fixed (1785 passing, 5 pre-existing failures)
