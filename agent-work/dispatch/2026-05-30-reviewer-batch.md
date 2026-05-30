# Reviewer dispatch — 2026-05-30

**You are the reviewer.** Read-only. No code edits. Worktree: `~/code/fichero-0.0.2`. Use jcodemunch-mcp for code navigation ([[reference_jcodemunch_mcp_single_source]]).

## Standby until integrator surfaces

The integrator is on Phase 0: fix trunk-red, then merge `origin/opus-realitykit-design` with 8 cascading-error fix-up. When `agent-work/dispatch/2026-05-30-integrator-DONE.md` appears, that's your signal.

## Activation pickup (when DONE file appears)

1. **Re-read** `agent-work/proposals/2026-05-30-post-collapse-review.md` (your own prior output) — your 5 MAJOR fixes were:
   - F1: route `KGMapView`/`KGTimelineView`/`EntityDigestView`/`DocumentInspectorInfoTab` through `entityService.documentKnowledgeGraph(...)`.
   - F2: share one descendant-walk helper between `folders.py` and `claims.py`.
   - F3: promote `DocumentKGSurface` `@State` → `@SceneStorage` (delete shadowed param).
   - F4: `KGFocusState` guard idempotency unit tests.
   - F5: `#if os(macOS)` color shim in `SpatialScene3D` / `RoomListView`.

2. **Read the integrator's merge SHA + diff.** Verify which of F1–F5 the merge satisfies (likely F3 and F5 if integrator did Phase 0 well).

3. **Re-review** the integrated diff specifically for:
   - Silent failures around the new RealityKit async texture loading (anything swallowing errors?).
   - The exhaustive-switch fixes — did integrator add real cases or escape with `default:`? If `default:`, flag as MINOR for follow-up.
   - The `@MainActor` annotation — did integrator put it on the property (best) or wrap the call site (acceptable)? Document.
   - Any new public API regressions surfacing through OpenAPI (Opus added `library_snapshot`-adjacent helpers but no new endpoint — confirm).

4. **Output:** `agent-work/proposals/2026-05-30-post-collapse-review-v2.md` with verdict (`MERGEABLE-AS-IS` / `MERGEABLE-WITH-FOLLOWUPS` / `NEEDS-REWORK`). List remaining F1/F2/F4 work as a follow-up scope for the next worker dispatch.

5. **Notify:** `agent-work/dispatch/2026-05-30-reviewer-DONE.md` with the verdict line. Manager picks up.

## Hard rules

- No code edits. Read-only.
- Never recommend running full pytest ([[feedback_no_full_pytest_on_daniels_machine]]).
- See [[feedback_recurring_bug_patterns]] for the three patterns to check in any review.
