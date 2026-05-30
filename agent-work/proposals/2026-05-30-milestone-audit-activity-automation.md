# Milestone Audit: Activity & Automation
**Date:** 2026-05-30  
**Auditor:** Claude Sonnet 4.6  
**Scope:** All issues (open + closed) in milestone "Activity & Automation" (milestone #56), dtubb/fichero

---

## Summary

| Category | Count |
|---|---|
| Total issues in milestone | 25 |
| Open | 7 |
| Closed (all COMPLETED) | 18 |
| **Re-milestone (wrong milestone)** | **2** |
| **Reopen (closed but not done / partial)** | **0** |
| **Add to this milestone (no/wrong milestone)** | **3** |
| **Label fixes needed (open issues only)** | **5** |
| **New milestone proposals** | **0** |

**Reopen verdict:** All 18 closed issues have verifiable git commits or explicit dtubb close comments confirming completion. No bulk sweeps detected. Zero reopens recommended.

---

## Action 1 — RE-MILESTONE (wrong milestone, move elsewhere)

### #565 → Library & Reading Surface
```
gh issue edit 565 --repo dtubb/fichero --milestone "Library & Reading Surface"
```
**Rationale:** "Space key toggles preview — should trigger Quick Look instead." This is a Library browsing / keyboard UX issue, not related to workflow execution, live logs, or event-driven triggers. Area in body says `LibraryView+KeyboardShortcuts`. Closed-COMPLETED so move is housekeeping only.

### #1117 → Developer Experience
```
gh issue edit 1117 --repo dtubb/fichero --milestone "Developer Experience"
```
**Rationale:** "3 minor write-path bypasses from the DuckDB audit." Item 1 (`api/main.py` provider UPDATE) and Item 3 (`cache.py` untyped API) are pure backend code-quality fixes with no Activity surface. Only Item 2 (`activity_store.py` read asymmetry) touches the Activity layer — but the issue title/intent is a backend typed-contract cleanup, not an Activity & Automation runtime feature. Closed-COMPLETED; move is housekeeping. Better home: Developer Experience.

---

## Action 2 — ADD TO THIS MILESTONE (no milestone or wrong milestone)

### #1226 → Activity & Automation (currently: NO MILESTONE, OPEN)
```
gh issue edit 1226 --repo dtubb/fichero --milestone "Activity & Automation"
```
**Rationale:** "Add stop, pause, and delete controls for active workflow runs in Activity." This is exactly the runtime execution surface — live run management controls. OPEN, P1, backend+swiftui. Squarely belongs here.

### #1222 → Activity & Automation (currently: NO MILESTONE, CLOSED-COMPLETED)
```
gh issue edit 1222 --repo dtubb/fichero --milestone "Activity & Automation"
```
**Rationale:** "Backend: pause workflow processing on provider quota exhaustion and stop crashing activity saves." Directly about the workflow execution runtime and activity persistence on quota failure. Closed-COMPLETED; milestone assignment is housekeeping for traceability.

### #1221 → Activity & Automation (currently: NO MILESTONE, CLOSED-COMPLETED)
```
gh issue edit 1221 --repo dtubb/fichero --milestone "Activity & Automation"
```
**Rationale:** "Frontend: workflow node output log should also appear in Activity Monitor." Log stream surfacing in the Activity monitor is a core Activity milestone concern. Closed-COMPLETED; milestone assignment is housekeeping.

---

## Action 3 — LABEL FIXES (open issues only)

### Remove spurious `status:ready-for-test` from Release Gate issues

Both #493 and #494 are Release Gate placeholder issues whose checklist items are **all unchecked** (no items marked `[x]`). The `status:ready-for-test` label is incorrect — it signals "merged, awaiting human QA" but neither milestone deliverable has shipped.

```
gh issue edit 493 --repo dtubb/fichero --remove-label "status:ready-for-test"
gh issue edit 494 --repo dtubb/fichero --remove-label "status:ready-for-test"
```

### Add `priority:P2` to #1264
```
gh issue edit 1264 --repo dtubb/fichero --add-label "priority:P2"
```
**Rationale:** "Standalone live Activity window (Apple Mail Connection-Doctor style)." New feature, builds on existing SSE infrastructure. Useful but not blocking — P2 is appropriate. Currently missing any priority label.

### Add `priority:P2` to #255 and `type:task` to clarify
```
gh issue edit 255 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 253 --repo dtubb/fichero --add-label "priority:P2"
```
**Rationale:** "Promote minimal Automation slice from off to beta" (#255) and "Promote Activity from off to beta" (#253) are feature-flag promotion tasks. Missing priority; P2 is appropriate as both depend on other open work (#494, #493) completing first.

---

## Action 4 — NO-OP / CONFIRMED CORRECT

The following are confirmed in the right milestone with correct state. No action needed:

| # | Title | Verdict |
|---|---|---|
| #1264 | Standalone live Activity window | Correct milestone; label fix in Action 3 |
| #1225 | Consolidate Activity Viewer tabs | Correct. P1 open; follows on #1038 (4-tab reduction → 1-tab target) |
| #1224 | Activity viewer use user-facing names | Correct. P1 open |
| #493 | [Release Gate] 0.1.5 — Activity Monitor | Correct milestone; label fix in Action 3 |
| #494 | [Release Gate] 0.1.6 — Automation | Correct milestone; label fix in Action 3 |
| #253 | Promote Activity from off to beta | Correct; label fix in Action 3 |
| #255 | Promote Automation from off to beta | Correct; label fix in Action 3 |
| #1117 | DuckDB write-path cleanups | Re-milestone in Action 1 |
| #1048 | Per-node timing summary | Correctly closed; verified fix in ActivityOverviewView+Cards.swift |
| #1040 | Wrong node showing as running | Correctly closed; verified fix commit 56b4e5c9 |
| #1038 | Activity view 8 tabs → 4 tabs | Correctly closed; commit 9fb36969 |
| #1000 | Backend stops responding during run | Correctly closed; fix was complete per final comment (async isolation was a misdiagnosis — confirmed workflow runner was already off the main loop) |
| #700 | Cache vs fresh not shown in Progress | Correctly closed; confirmed by dtubb comment |
| #698 | File path + opaque ID as run title | Correctly closed; confirmed by dtubb |
| #655 | Activity sidebar bold/no-icon | Correctly closed |
| #654 | Internal node names + UUID in Progress | Correctly closed; activityHumanNodeName() fix |
| #649 | Elapsed time missing "ago" | Correctly closed |
| #648 | Activity view state not persisted | Correctly closed |
| #647 | Activity sidebar click not navigating | Correctly closed |
| #637 | Run data cleared on completion | Correctly closed; PR #638 |
| #633 | Green checkmarks / no artifacts | Correctly closed; artifacts endpoint fix |
| #630 | Console tab empty | Correctly closed; PR #638 |
| #629 | Progress tab "not available" | Correctly closed; PR #638 |
| #627 | Live Log "Waiting for output" | Correctly closed; PR #638 |
| #565 | Space key Quick Look | Correctly closed; re-milestone in Action 1 |

---

## New Milestone Proposals

None. All issues fit existing milestones. No new milestone warranted.

---

## Notes on Boundary: Activity & Automation vs Workflows

The boundary is:
- **This milestone:** runtime execution view (live logs, progress, node state, timing), Activity Monitor surface, triggers, schedules, run management (stop/pause).
- **Workflows milestone:** canvas editor, node configuration, workflow templates, batch input configuration, provider/model pickers on nodes.

Issues that overlap (e.g. output log surfacing in Activity) belong here when the primary user-facing surface is the Activity Monitor. Issues where the primary concern is the workflow definition or canvas stay in Workflows.

Issue #1045 ("Activity Overview: show document × step grid") was filed in Workflows milestone but is about the Activity Monitor view — however it is already CLOSED-COMPLETED so the re-milestone is optional housekeeping only and has been omitted from Action 1 to keep the list lean.

---

## Executable Checklist (copy-paste ready)

```bash
# === ACTION 1: RE-MILESTONE ===
gh issue edit 565 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 1117 --repo dtubb/fichero --milestone "Developer Experience"

# === ACTION 2: ADD TO THIS MILESTONE ===
gh issue edit 1226 --repo dtubb/fichero --milestone "Activity & Automation"
gh issue edit 1222 --repo dtubb/fichero --milestone "Activity & Automation"
gh issue edit 1221 --repo dtubb/fichero --milestone "Activity & Automation"

# === ACTION 3: LABEL FIXES ===
gh issue edit 493 --repo dtubb/fichero --remove-label "status:ready-for-test"
gh issue edit 494 --repo dtubb/fichero --remove-label "status:ready-for-test"
gh issue edit 1264 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 255 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 253 --repo dtubb/fichero --add-label "priority:P2"
```
