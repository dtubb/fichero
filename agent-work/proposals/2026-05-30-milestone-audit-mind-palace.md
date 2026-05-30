# Milestone Audit — Mind Palace
**Date:** 2026-05-30
**Auditor:** claude-sonnet-4-6
**Status:** PROPOSAL ONLY — no GitHub state has been modified

---

## Summary

| Metric | Count |
|---|---|
| Total issues audited | 16 |
| Currently open | 10 |
| Currently closed | 6 |
| **Reopen candidates** | **2** |
| Re-milestone candidates | 2 |
| Label fixes needed | 7 |
| New milestone proposals | 1 |

---

## Context: What Phase 3 Actually Delivered (2026-05-30)

Phase 3 landed on `opus-realitykit-design` today:
- `LinkType` enum + `MindPalaceLink` content-level edge
- `MindPalaceTheme` cross-platform palette
- `MindPalaceLibraryProjector` (phyllotaxis layout, placeholder for backend endpoint)
- `SpatialScene3D` extended: sphere meshes for entities, cylinder edges colored by `LinkType`, `HoverEffectComponent`, follow-link camera recentre
- Pinned 'Whole Library' pseudo-room in `RoomListView`
- `MindPalaceService.loadLibraryProjection()`
- Tests: `MindPalaceLinkTypeTests.swift`
- Cross-platform: compiles unchanged on macOS 15 / iOS 18 / visionOS 2

Phase 3 is NOT fully merged yet — blocked on a pre-existing trunk regression in `ClaimSummaryCardView.swift` (KG team issue). Branch is at `opus-realitykit-design`.

Phase 2 remaining items NOT done (per Daniel's 2026-05-27 comment):
- 3D tap-to-select (`InputTargetComponent`/`CollisionComponent`)
- Camera-orbit + viewport persistence
- Drag documents/collections from Library grid onto canvas
- Collection/smart-group expansion in Add picker
- Live AI-rail streaming (depends on #1269 MCP)

---

## SECTION A — Reopen Candidates

### REOPEN #1297 — Mind Palace Phase 2 — editing (drag-to-move, viewport persistence) + 3D view
**Current state:** CLOSED / COMPLETED
**Why reopen:** Closed today with "Merged" but Phase 2 checklist items are explicitly NOT done per Daniel's own 2026-05-27 comment:
- 3D tap-to-select not implemented
- Camera-orbit + viewport persistence not wired
- Library grid drag-onto-canvas not done
- Smart-group expansion in Add picker not done
- Live AI-rail streaming not done (depends on #1269)

This was bulk-closed as part of Phase 3 merge but it is clearly partial. These are substantive interaction capabilities core to Mind Palace's value proposition. Reopen and track remaining items explicitly.

```
gh issue reopen 1297 --repo dtubb/fichero
gh issue comment 1297 --repo dtubb/fichero --body "Reopening: Phase 2 was closed at Phase 3 merge but the following checklist items from Daniel's 2026-05-27 comment remain undone: 3D tap-to-select, camera-orbit + viewport persistence, Library-grid drag-to-canvas, collection expansion in Add picker, live AI-rail streaming (#1269). Tracking these explicitly."
```

**Labels to add:**
```
gh issue edit 1297 --repo dtubb/fichero --add-label "type:feature,client:swiftui,priority:P1"
```

---

### REOPEN #920 — Re-enable mind-palace (spatial Notes layer) when RealityKit work resumes
**Current state:** CLOSED / COMPLETED
**Why reopen:** Closed as "completed" but the reconciliation task it describes — reconciling the mind-palace Note spatial fields (room_id, position, viewport) with the newer `/api/notes` shape — has not been done. The open issues #267, #268, #269 on REST APIs and Note model are still open, which means this reconciliation work still exists. The issue is not about "re-enabling" anymore (the router is presumably re-enabled) but the Note model reconciliation described in the body is untracked. Reopen and retitle or add a comment narrowing to the Note-shape reconciliation.

```
gh issue reopen 920 --repo dtubb/fichero
gh issue comment 920 --repo dtubb/fichero --body "Reopening: the router re-enablement may be done but the Note-model reconciliation described in step 2 (reconcile spatial Note fields room_id/position/viewport with the /api/notes shape from #917) is still open and untracked. #267 and #268 are still open. This issue should track the reconciliation gap, not just the router toggle."
```

**Labels to add:**
```
gh issue edit 920 --repo dtubb/fichero --add-label "backend,priority:P2"
```

---

## SECTION B — Re-milestone Candidates

### RE-MILESTONE #1078 — Apple Vision provider/model strings inconsistent
**Current state:** CLOSED / COMPLETED, in Mind Palace milestone
**Why:** This is a provider/model normalization bug. It has nothing to do with the spatial knowledge layer, RealityKit, notes, drag/connect, or viewport persistence. It was likely swept into this milestone by accident.
**Proposed milestone:** "Settings & Providers" (milestone #20)

```
gh issue edit 1078 --repo dtubb/fichero --milestone "Settings & Providers"
```

---

### RE-MILESTONE #937 — Two Apple Vision providers listed — consolidate or label, prevent duplicate-add
**Current state:** CLOSED / COMPLETED, in Mind Palace milestone
**Why:** Same problem as #1078 — this is a providers/settings UI bug about Apple Vision model deduplication. Zero spatial/RealityKit/note content. Likely swept in alongside #1078.
**Proposed milestone:** "Settings & Providers" (milestone #20)

```
gh issue edit 937 --repo dtubb/fichero --milestone "Settings & Providers"
```

---

## SECTION C — Label Corrections

### #1297 — Mind Palace Phase 2
**Missing labels:** `type:feature`, `client:swiftui`, `priority:P1`
**Current:** no labels at all
**Fix:**
```
gh issue edit 1297 --repo dtubb/fichero --add-label "type:feature,client:swiftui,priority:P1"
```

### #265 — Epic: Spatial knowledge layer architecture and roadmap
**Current labels:** `documentation`, `type:feature`
**Missing:** `area:both`, `priority:P1` (this is the epic driving all spatial work)
**Note:** `documentation` is not wrong (it's a plan doc) but `type:feature` is the more important signal. Also missing `area:both` since it covers frontend + backend.
**Fix:**
```
gh issue edit 265 --repo dtubb/fichero --add-label "area:both,priority:P1"
```

### #274 — Build direct-manipulation RealityKit spatial workspace foundation
**Current labels:** `type:task`, `type:feature`, `client:swiftui`
**Missing:** `priority:P1` (this is a core Phase 1 deliverable for the milestone), `area:both`
**Fix:**
```
gh issue edit 274 --repo dtubb/fichero --add-label "priority:P1,area:both"
```

### #270 — Extend Fichero MCP server with semantic note, workspace, and spatial tools
**Current labels:** `type:task`, `backend`, `type:feature`
**Missing:** `mcp` label, `priority:P2`
**Fix:**
```
gh issue edit 270 --repo dtubb/fichero --add-label "mcp,priority:P2"
```

### #266 — Add durable note links and provenance records
**Current labels:** `type:task`, `backend`, `type:feature`
**Missing:** `priority:P2`
**Fix:**
```
gh issue edit 266 --repo dtubb/fichero --add-label "priority:P2"
```

### #268 — Introduce native Note model with user/AI taxonomy and lifecycle
**Current labels:** `type:task`, `backend`, `type:feature`
**Missing:** `priority:P1` — this is foundational to everything else in the milestone (268 blocks 267, 266, 273, 270)
**Fix:**
```
gh issue edit 268 --repo dtubb/fichero --add-label "priority:P1"
```

### #512 — [Release Gate] 0.6.1 - Wire: Spatial Library
**Current labels:** `status:ready-for-test`, `roadmap`
**Missing:** `type:task`, `client:swiftui`
**Note:** `status:ready-for-test` is inconsistent — this is a 0.6.x milestone gate for far-future work; it shouldn't be "ready for test" now. Should be `roadmap` only with proper type label.
**Fix:**
```
gh issue edit 512 --repo dtubb/fichero --add-label "type:task,client:swiftui" --remove-label "status:ready-for-test"
```

### #511 — [Release Gate] 0.6.0 - Wire: Spatial Knowledge Layer
**Same problem as #512.**
**Fix:**
```
gh issue edit 511 --repo dtubb/fichero --add-label "type:task,client:swiftui" --remove-label "status:ready-for-test"
```

---

## SECTION D — New Milestone Proposal

### Proposed new milestone: "Spatial Library" (or "Library Spatial View")

**Rationale:** Phase 3 introduced a design document and initial implementation for a whole-library spatial view (`MindPalaceLibraryProjector`, `linkType` taxonomy, sphere/cylinder RealityKit primitives). This is architecturally distinct from the core Mind Palace "notes + connections + drag" work:

- Mind Palace = per-room knowledge-graph canvas (notes, drag/connect, AI workspace)
- Spatial Library = whole-library phyllotaxis/3D spatial view of documents/entities as first-class spatial browsing mode

Issues #511 and #512 (0.6.0 and 0.6.1 release gates) are tracking this Spatial Library concept. They currently sit in Mind Palace milestone but describe a distinct 0.6.x feature track.

**Proposed milestone:** Create "Spatial Library" and move #511, #512 there. Also move the backend endpoint stub referenced in `MindPalaceLibraryProjector` (`/api/mind-palace/library/scene`) into a new issue under this milestone when created.

```
# Cannot create milestone via gh issue, but the gh api endpoint is:
gh api repos/dtubb/fichero/milestones --method POST \
  --field title="Spatial Library" \
  --field description="Whole-library 3D/spatial browsing mode via RealityKit. Documents and entities as spatial objects. One scene graph: Mac -> iPhone AR -> Vision Pro. Phase 1-5 per 2026-05-30-mindpalace-spatial-library.md design doc." \
  --field state="open"

# Then move issues:
gh issue edit 511 --repo dtubb/fichero --milestone "Spatial Library"
gh issue edit 512 --repo dtubb/fichero --milestone "Spatial Library"
```

---

## SECTION E — Issues That Are Correctly Filed (no action needed)

| # | Title | Assessment |
|---|---|---|
| #265 | Epic: Spatial knowledge layer architecture + roadmap | Correct milestone. CLOSED/COMPLETED is correct — it's a plan doc, plans can be closed. Label fix proposed in Section C. |
| #266 | Add durable note links and provenance records | Correct milestone. Open. Label fix in Section C. |
| #267 | Expose native notes and spatial workspace REST APIs | Correct milestone. Open. No label issues beyond P-label missing (acceptable). |
| #268 | Introduce native Note model with user/AI taxonomy | Correct milestone. Open. Priority label fix in Section C. |
| #269 | Persist spatial graph primitives | Correct milestone. Open. Labels acceptable. |
| #271 | Add shared spatial workspace mode to Library views | Correct milestone. Open. Labels acceptable. |
| #273 | Let workflows and agent teams write durable results into AI workspace | Correct milestone. Open. Labels acceptable. |
| #274 | Build direct-manipulation RealityKit spatial workspace foundation | Correct milestone. Open. Label fix in Section C. |
| #389 | 0.0.2 Phase 3: Mind Palace + RealityKit (Layer 6) | Correct milestone. CLOSED/COMPLETED appropriate — it was a sprint tracking issue, not a feature spec. |

---

## Consolidated Checklist

```bash
# SECTION A — Reopen

gh issue reopen 1297 --repo dtubb/fichero
gh issue comment 1297 --repo dtubb/fichero --body "Reopening: Phase 2 closed at Phase 3 merge but 5 checklist items remain per Daniel's 2026-05-27 comment: 3D tap-to-select, camera-orbit + viewport persistence, Library-grid drag-to-canvas, collection expansion in Add picker, live AI-rail streaming (#1269)."
gh issue edit 1297 --repo dtubb/fichero --add-label "type:feature,client:swiftui,priority:P1"

gh issue reopen 920 --repo dtubb/fichero
gh issue comment 920 --repo dtubb/fichero --body "Reopening: router re-enablement may be done but Note-model reconciliation (step 2: reconcile spatial Note fields with /api/notes shape from #917) is untracked. #267 and #268 are still open. Track the reconciliation gap here."
gh issue edit 920 --repo dtubb/fichero --add-label "backend,priority:P2"

# SECTION B — Re-milestone

gh issue edit 1078 --repo dtubb/fichero --milestone "Settings & Providers"
gh issue edit 937 --repo dtubb/fichero --milestone "Settings & Providers"

# SECTION C — Label corrections

gh issue edit 265 --repo dtubb/fichero --add-label "area:both,priority:P1"
gh issue edit 266 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 268 --repo dtubb/fichero --add-label "priority:P1"
gh issue edit 270 --repo dtubb/fichero --add-label "mcp,priority:P2"
gh issue edit 274 --repo dtubb/fichero --add-label "priority:P1,area:both"
gh issue edit 511 --repo dtubb/fichero --add-label "type:task,client:swiftui" --remove-label "status:ready-for-test"
gh issue edit 512 --repo dtubb/fichero --add-label "type:task,client:swiftui" --remove-label "status:ready-for-test"

# SECTION D — New milestone + move (do milestone create first, then edit issues)

gh api repos/dtubb/fichero/milestones --method POST \
  --field title="Spatial Library" \
  --field description="Whole-library 3D/spatial browsing mode via RealityKit. Documents and entities as spatial objects. One scene graph: Mac -> iPhone AR -> Vision Pro. Phase 1-5 per 2026-05-30-mindpalace-spatial-library.md design doc." \
  --field state="open"

# After creating, get the new milestone number and use it:
gh issue edit 511 --repo dtubb/fichero --milestone "Spatial Library"
gh issue edit 512 --repo dtubb/fichero --milestone "Spatial Library"
```

---

## Rationale Notes

**Why reopen #1297 and not just create new issues?** The Phase 2 issue body was never completed — all five remaining checklist items are explicitly documented in Daniel's own comment. Reopening preserves the thread context, the original scope description, and the Phase 1 baseline description. Creating new issues would fragment the history.

**Why reopen #920 and not just create a new issue?** The Note-model reconciliation gap (#920 step 2) is a direct prerequisite to #267/#268 being buildable against a consistent API. The issue body already describes the exact work needed. Reopening keeps the cross-reference intact.

**Why move #1078/#937 out of Mind Palace?** Both issues are about the Apple Vision provider/model list in Settings — they predate Mind Palace work, deal with provider registry deduplication, and have zero spatial/RealityKit content. They were almost certainly swept into this milestone by a bulk triage pass rather than intentional assignment.

**Why flag #511/#512 `status:ready-for-test` as wrong?** These are roadmap-future 0.6.x release gates. The `status:ready-for-test` label means "merged, awaiting human QA" — but 0.6.x hasn't shipped or been built. The label appears to have been applied during a bulk triage pass rather than reflecting actual merge state.
