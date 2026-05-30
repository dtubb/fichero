# Milestone Audit: Search (2026-05-30)

**Scope:** 62 issues total — 27 open, 35 closed.
**Search milestone ID:** 17

---

## Summary Counts

| Action | Count |
|---|---|
| Wrong milestone → re-milestone (closed, clearly misplaced UI/shell bugs) | 12 |
| Wrong milestone → re-milestone (open, clearly misplaced non-search features) | 8 |
| Duplicate open issues (one is the canonical, close the shadow) | 3 pairs |
| Reopen — genuine uncaptured ideas closed too early | 4 |
| Label fixes (missing type:/priority:/surface) | 11 |
| Keep as-is | 24 |

---

## Section 1 — Wrong Milestone: Closed UI/Reading Surface Bugs → Library & Reading Surface

These were closed "as completed" but the work they track belongs firmly in Library & Reading Surface, not Search. The bulk-cleanup warning in the prompt is exactly right here.

```bash
# #355 — Bottom magnifier zoom limit: pure document-viewer bug, no search involvement
gh issue edit 355 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #354 — Right sidebar closes on click: inspector/pane bug, zero search relation
gh issue edit 354 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #593 — Preview-style swipe navigation across folders: document reading UX
gh issue edit 593 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #602 — Sidebar drag-drop reorder: library sidebar behaviour
gh issue edit 602 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #617 — Toolbar per-column NNW redesign: Mac app shell / library layout
gh issue edit 617 --repo dtubb/fichero --milestone "Mac App Shell"

# #618 — Sidebar flatten indentation: library sidebar aesthetics
gh issue edit 618 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #519 — Add Artifacts column to library table view: library view feature
gh issue edit 519 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #518 — Import progress indicator in library view: library onboarding UX
gh issue edit 518 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #356 — Sidebar Architecture review (unified vs 5 sidebars): architectural decision for Library/Shell
gh issue edit 356 --repo dtubb/fichero --milestone "Mac App Shell"

# #326 — Keyboard shortcuts — all navigation shortcuts: Library & Shell UX, not search-specific
gh issue edit 326 --repo dtubb/fichero --milestone "Mac App Shell"

# #276 — Re-enable Library List/Table/Map views after 0.0.1: library views — not search views
gh issue edit 276 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #517 — Re-enable library list, table, map display modes: same as above; pure library feature
gh issue edit 517 --repo dtubb/fichero --milestone "Library & Reading Surface"
```

---

## Section 2 — Wrong Milestone: Closed Workflow/KG Tasks → Workflows

These were completed tasks for the Workflows or KG pipeline that ended up parked in Search, presumably because they were in-flight during the same sprint.

```bash
# #726 — Generify Catalogue (composable) workflow: pure workflow editor / tool task
gh issue edit 726 --repo dtubb/fichero --milestone "Workflows"

# #727 — Catalogue tool: consume structured NER inputs: workflow pipeline wiring
gh issue edit 727 --repo dtubb/fichero --milestone "Workflows"

# #731 — Apple Intelligence Catalogue workflow: Workflows milestone
gh issue edit 731 --repo dtubb/fichero --milestone "Workflows"

# #921 — Re-enable research orchestration routers: backend routing, not search
gh issue edit 921 --repo dtubb/fichero --milestone "Workflows"

# #684 — Chained per-file steps backend support: workflow execution engine
gh issue edit 684 --repo dtubb/fichero --milestone "Workflows"

# #683 — Visual fan-out / aggregate markers in workflow editor edges: workflow editor UI
gh issue edit 683 --repo dtubb/fichero --milestone "Workflows"

# #680 — Aggregate node: collect per-file outputs: workflow node
gh issue edit 680 --repo dtubb/fichero --milestone "Workflows"
```

---

## Section 3 — Wrong Milestone: Closed Performance/Shell Bugs → Library & Reading Surface or Mac App Shell

```bash
# #619 — Backend connection on launch slow: startup performance, Mac App Shell
gh issue edit 619 --repo dtubb/fichero --milestone "Mac App Shell"

# #605 — App startup still slow: startup performance, Mac App Shell
gh issue edit 605 --repo dtubb/fichero --milestone "Mac App Shell"

# #675 — convertToSendable loses metadata value types: inspector/library bug
gh issue edit 675 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #674 — documentSignature computes full content hash on every SwiftUI diff: library perf bug
gh issue edit 674 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #673 — refreshDocumentFromBackend fires N times: workflow execution observer + library, but closer to Workflows
gh issue edit 673 --repo dtubb/fichero --milestone "Workflows"
```

---

## Section 4 — Wrong Milestone: Open Non-Search Issues → Correct Homes

These open issues landed in Search but are unrelated to search functionality:

```bash
# #735 — Pre-run cost estimate on workflow execute button: Workflows milestone
# (LiteLLM cost surfacing before a run — workflow UX, not search)
gh issue edit 735 --repo dtubb/fichero --milestone "Workflows"

# #734 — Surface ModelComparisonService 'Compare models' UI: Workflows (ModelComparisonService is workflow tooling)
gh issue edit 734 --repo dtubb/fichero --milestone "Workflows"

# #712 — Remove center preview pane; folder inspector when nothing selected: Library & Reading Surface
gh issue edit 712 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #710 — Test: ArtifactPanel RTF encode/decode round-trip: Library & Reading Surface (inspector test)
gh issue edit 710 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #709 — Test: AppDatabase RLock concurrent reads: Infrastructure (backend concurrency test)
gh issue edit 709 --repo dtubb/fichero --milestone "Infrastructure"

# #707 — Test: per-page Artifact rows after vision propagation: Workflows (vision tool test)
gh issue edit 707 --repo dtubb/fichero --milestone "Workflows"

# #708 — Test: workflow stream emits cached:true: Workflows (SSE event shape test)
gh issue edit 708 --repo dtubb/fichero --milestone "Workflows"

# #706 — Inspector V2 phase 3: user-defined attribute schema: Library & Reading Surface (inspector feature)
gh issue edit 706 --repo dtubb/fichero --milestone "Library & Reading Surface"

# #664 — Achieve 100% unit test coverage: Infrastructure (cross-cutting test goal)
gh issue edit 664 --repo dtubb/fichero --milestone "Infrastructure"

# #663 — Consider updating git/GitHub identity to dtubb-ai: Developer Experience
gh issue edit 663 --repo dtubb/fichero --milestone "Developer Experience"

# #670 — files_tool silently resolves page selection to whole PDF: Workflows (files_tool bug)
# Note: label says client:swiftui but this is a backend bug in sources.py + vision_base.py
gh issue edit 670 --repo dtubb/fichero --milestone "Workflows"
```

---

## Section 5 — Duplicate Open Issues: Close Shadows

These are clear duplicates where a newer, better-written issue supersedes an older one. Close the older shallow issue:

```bash
# #285 vs #434 — Both track "Re-enable Search icon/table/map views after 0.0.2"
# #434 is closed/completed; #285 is open and is the live tracking issue. Keep #285.
# No action needed — #434 already closed.

# #287 vs #432 — Both track "Re-enable Library/Search split layouts after 0.0.2"
# #432 has backend acceptance criteria; #287 has roadmap label. These are companion issues:
# #432 = backend work, #287 = SwiftUI work. Keep both but note they're tightly coupled.
# Suggest: add cross-reference comment linking them. No close needed.

# #424 vs #374 — Both are "0.0.4: Search explanation and metrics visibility panel"
# #424 has backend acceptance criteria; #374 has roadmap + client:swiftui.
# These are companion issues (same dual-track pattern as above). Keep both.
# Suggest: #424 add label backend, #374 add label client:swiftui (already has it). Cross-link in body.
# Close #374 as duplicate of #424 since #424 is more complete:
gh issue close 374 --repo dtubb/fichero --comment "Duplicate of #424 which covers both backend and frontend scope. Closing shadow; all work tracked in #424."
```

---

## Section 6 — Reopen: Genuine Uncaptured Ideas

These were closed as "completed" but a meaningful, **unbuilt** idea was embedded in the issue body that deserves its own tracking:

### REOPEN: #593 — Preview-style swipe navigation (re-migrate too)
**Why reopen:** Daniel explicitly asked for "swipe to go next image/PDF page like macOS Preview with page-turn animation" — the verbatim request is in the body. The issue was closed as completed, but this specific gesture-driven swipe-with-animation hasn't shipped. The partial work (arrow-key navigation) was done but not the swipe gesture + page-turn animation.
```bash
gh issue reopen 593 --repo dtubb/fichero
gh issue edit 593 --repo dtubb/fichero --milestone "Library & Reading Surface" --add-label "type:feature,client:swiftui,priority:P2"
```

### REOPEN: #921 — Re-enable research orchestration routers
**Why reopen:** The issue body says "When to re-enable: when LangGraph workflows need multi-step research operations." It lists specific triggers (summarise → extract → triangulate → review queue). The routers were not deleted — just unregistered. The upstream trigger (LangGraph workflows driving multi-step research) is exactly what Workflows milestone is building. This is a real pending task, not a completed one.
```bash
gh issue reopen 921 --repo dtubb/fichero
gh issue edit 921 --repo dtubb/fichero --milestone "Workflows" --add-label "type:task,backend,priority:P3"
```

### REOPEN: #355 — Bottom magnifier zoom limit
**Why reopen:** Hardcoded 100px zoom floor in the document viewer. The issue is specific, reproducible, and the fix is mechanical (remove/lower the min constraint). Closed as "completed" but there's no evidence in the body that a fix was merged. Could easily be a false-close.
```bash
gh issue reopen 355 --repo dtubb/fichero
gh issue edit 355 --repo dtubb/fichero --milestone "Library & Reading Surface" --add-label "type:bug,client:swiftui,priority:P3"
```

### REOPEN: #354 — Right sidebar closes when clicking at the top
**Why reopen:** Specific SwiftUI hit-testing/gesture bug — right sidebar (inspector) dismisses when clicking the top area. This is a real UX regression that would irritate users constantly. Closed as "completed" with no fix commit referenced. Likely a false-close from a batch status update.
```bash
gh issue reopen 354 --repo dtubb/fichero
gh issue edit 354 --repo dtubb/fichero --milestone "Library & Reading Surface" --add-label "type:bug,client:swiftui,priority:P2"
```

---

## Section 7 — Label Fixes (no milestone change)

Issues that have the right milestone but are missing canonical labels:

```bash
# #1270 — Rich search results (closed, no labels): needs type:task, backend, client:swiftui
gh issue edit 1270 --repo dtubb/fichero --add-label "type:task,backend,client:swiftui"

# #1086 — Vector search verification (closed): missing type:task
gh issue edit 1086 --repo dtubb/fichero --add-label "type:task,backend"

# #288 — 0.0.1 Simplify Search UX (closed, no labels): type:task, client:swiftui
gh issue edit 288 --repo dtubb/fichero --add-label "type:task,client:swiftui"

# #325 — Search bar placement (closed): has type:feature but missing client:swiftui
gh issue edit 325 --repo dtubb/fichero --add-label "client:swiftui"

# #356 — Sidebar Architecture review (closed, no labels): type:task, needs-design, area:both
gh issue edit 356 --repo dtubb/fichero --add-label "type:task,needs-design"

# #670 — files_tool PDF page selection bug (open): has client:swiftui but is actually backend bug
# Remove wrong label, add correct ones:
gh issue edit 670 --repo dtubb/fichero --remove-label "client:swiftui" --add-label "type:bug,backend,priority:P1"

# #432 — Re-enable Library/Search Split Layouts: missing client:swiftui (it has backend but needs frontend label too)
gh issue edit 432 --repo dtubb/fichero --add-label "client:swiftui"

# #481 — Release Gate 0.0.3: missing roadmap label
gh issue edit 481 --repo dtubb/fichero --add-label "roadmap"

# #482 — Release Gate 0.0.4: missing roadmap label
gh issue edit 482 --repo dtubb/fichero --add-label "roadmap"

# #483 — Release Gate 0.0.5: missing roadmap label
gh issue edit 483 --repo dtubb/fichero --add-label "roadmap"

# #737 — Search v2.1 alias-aware query expansion: missing type:task
gh issue edit 737 --repo dtubb/fichero --add-label "type:task"
```

---

## Section 8 — Issues That Remain Correctly in Search

These 24 issues are correctly filed and need no milestone change:

| # | Title | Notes |
|---|---|---|
| #878 | Semantic embedding map visualisation | Core Search feature (2D doc cloud) |
| #877 | RAG Q&A workflow (Apple Intelligence + hybrid retrieval) | Core Search — local RAG |
| #876 | Int8 quantization for LanceDB at 100K+ | Core Search scaling |
| #875 | Hybrid BM25 + BGE-M3 retrieval (RRF) | Core Search retrieval |
| #741 | Search v2.5: local RAG Q&A workflow | Duplicate scope of #877; consider closing |
| #738 | Search index: int8 quantization | Duplicate scope of #876; consider closing |
| #737 | Search v2.1: alias-aware entity query expansion | Correct |
| #736 | Search v2: hybrid BM25 + BGE-M3 (RRF) | Duplicate scope of #875; consider closing |
| #483 | Release Gate 0.0.5 — Search v3 | Correct |
| #482 | Release Gate 0.0.4 — Search v2 | Correct |
| #481 | Release Gate 0.0.3 — Search v1 | Correct |
| #434 | Re-enable Search Icon/Table/Map Views (closed) | Correct |
| #432 | Re-enable Library/Search Split Layouts | Correct (backend component) |
| #424 | Search Explanation and Metrics Panel (backend) | Correct |
| #287 | Re-enable Library/Search split layouts (SwiftUI) | Correct (SwiftUI component) |
| #285 | Re-enable Search icon/table/map views | Correct |
| #281 | Re-enable icon-view zoom toolbar controls | Correct (Search scope — deferred) |
| #1270 | Rich search results + transcript snippet + KG | Correct |
| #1106 | CLI search results render as placeholders | Correct |
| #1086 | Vector search verification | Correct |
| #1054 | Search returns every page with marginal relevance | Correct (fixed) |
| #1053 | Clicking search result doesn't show preview | Correct (fixed) |
| #1046 | Search results icon view shows generic placeholder | Correct (fixed) |
| #1032 | Unify search into one always-visible search bar | Correct (fixed) |
| #325 | Search bar in search column not toolbar | Correct |
| #288 | 0.0.1 Simplify Search UX | Correct |

---

## Section 9 — Suspected Duplicates in Search (no action required, but flag)

```
#875 ≈ #736  (Hybrid BM25+BGE-M3 retrieval — #875 is a newer, cleaner restatement of #736)
#876 ≈ #738  (Int8 quantization for LanceDB — same)
#877 ≈ #741  (RAG Q&A workflow — same)
```

**Recommendation:** Once Search v2/v3 work begins, close #736, #738, #741 as "superseded by" #875, #876, #877 respectively. The newer issues have cleaner scope. Not actioning now since it's pre-work.

---

## Quick-Reference: Full Checklist

```bash
# ============================================================
# SECTION 1: Closed UI bugs → Library & Reading Surface
# ============================================================
gh issue edit 355 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 354 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 593 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 602 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 618 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 519 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 518 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 276 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 517 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 675 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 674 --repo dtubb/fichero --milestone "Library & Reading Surface"

# Closed UI bugs → Mac App Shell
gh issue edit 617 --repo dtubb/fichero --milestone "Mac App Shell"
gh issue edit 356 --repo dtubb/fichero --milestone "Mac App Shell"
gh issue edit 326 --repo dtubb/fichero --milestone "Mac App Shell"
gh issue edit 619 --repo dtubb/fichero --milestone "Mac App Shell"
gh issue edit 605 --repo dtubb/fichero --milestone "Mac App Shell"

# ============================================================
# SECTION 2+3: Closed Workflow/KG tasks → Workflows
# ============================================================
gh issue edit 726 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 727 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 731 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 684 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 683 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 680 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 673 --repo dtubb/fichero --milestone "Workflows"

# ============================================================
# SECTION 4: Open misfiles → correct milestones
# ============================================================
gh issue edit 735 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 734 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 712 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 710 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 706 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 670 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 707 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 708 --repo dtubb/fichero --milestone "Workflows"
gh issue edit 709 --repo dtubb/fichero --milestone "Infrastructure"
gh issue edit 664 --repo dtubb/fichero --milestone "Infrastructure"
gh issue edit 663 --repo dtubb/fichero --milestone "Developer Experience"

# ============================================================
# SECTION 5: Close duplicate
# ============================================================
gh issue close 374 --repo dtubb/fichero --comment "Duplicate of #424 which covers both backend and frontend scope. Closing shadow; all work tracked in #424."

# ============================================================
# SECTION 6: REOPENS (generous — real uncaptured ideas)
# ============================================================
gh issue reopen 593 --repo dtubb/fichero
gh issue edit 593 --repo dtubb/fichero --milestone "Library & Reading Surface" --add-label "type:feature,client:swiftui,priority:P2"

gh issue reopen 921 --repo dtubb/fichero
gh issue edit 921 --repo dtubb/fichero --milestone "Workflows" --add-label "type:task,backend,priority:P3"

gh issue reopen 355 --repo dtubb/fichero
gh issue edit 355 --repo dtubb/fichero --milestone "Library & Reading Surface" --add-label "type:bug,client:swiftui,priority:P3"

gh issue reopen 354 --repo dtubb/fichero
gh issue edit 354 --repo dtubb/fichero --milestone "Library & Reading Surface" --add-label "type:bug,client:swiftui,priority:P2"

# ============================================================
# SECTION 7: Label fixes (in-place)
# ============================================================
gh issue edit 1270 --repo dtubb/fichero --add-label "type:task,backend,client:swiftui"
gh issue edit 1086 --repo dtubb/fichero --add-label "type:task,backend"
gh issue edit 288 --repo dtubb/fichero --add-label "type:task,client:swiftui"
gh issue edit 325 --repo dtubb/fichero --add-label "client:swiftui"
gh issue edit 356 --repo dtubb/fichero --add-label "type:task,needs-design"
gh issue edit 670 --repo dtubb/fichero --remove-label "client:swiftui" --add-label "type:bug,backend,priority:P1"
gh issue edit 432 --repo dtubb/fichero --add-label "client:swiftui"
gh issue edit 481 --repo dtubb/fichero --add-label "roadmap"
gh issue edit 482 --repo dtubb/fichero --add-label "roadmap"
gh issue edit 483 --repo dtubb/fichero --add-label "roadmap"
gh issue edit 737 --repo dtubb/fichero --add-label "type:task"
```
