# Milestone Audit — Importers
**Date:** 2026-05-30
**Auditor:** claude-sonnet-4-6
**Scope:** All 29 issues in `dtubb/fichero` milestone "Importers" (open AND closed), plus boundary sweep for un-milestoned importer-relevant issues.

---

## Summary

| Category | Count |
|---|---|
| Total issues in milestone | 29 |
| Open | 5 |
| Closed (completed) | 23 |
| Closed (not-planned) | 1 |
| **Reopen candidates** | **2** |
| Wrong-milestone → re-file | 3 |
| Un-milestoned issues that belong here | 2 (Box + Dropbox importers) |
| Label fixes on open issues | 3 issues missing type/priority |
| Label fixes on closed issues | 19 issues missing priority (retrospective) |
| Milestone description conflict | YES — names specific corpora; those belong in Source Archives |
| New milestones needed | 0 |

---

## Milestone Description Flag

**The "Importers" milestone description currently reads:**
> "Cloud-linked importers (Box, Dropbox) that link without downloading. Release-data import flows (Black folder + Maps folder metadata fusion, Chota Valley maps, Archivo Judicial, Mosquera notebooks, Marshall diary, Istmina). XLSX/spreadsheet import. Drag-in folder/file polish. Pre-catalogued material import (skip re-extraction)."

**Problem:** The phrase "Release-data import flows (Black folder + Maps folder metadata fusion, Chota Valley maps, Archivo Judicial, Mosquera notebooks, Marshall diary, Istmina)" names specific research corpora — those belong in the **Source Archives** milestone. The Importers milestone should describe import *tools and mechanisms* only.

**Proposed corrected description:**
> "Import tools and loaders: cloud-linked importers (Box, Dropbox — link without downloading), Kreuzberg/Docling PDF and image extraction, XMP sidecar support, XLSX/spreadsheet import, drag-in folder/file polish, folder watchers, pre-catalogued material import (skip re-extraction), Tinderbox .tbx importer, resumable large-corpus ingest."

```bash
# Fix description
gh issue edit --repo dtubb/fichero --milestone-description "..." # NOTE: milestone description edits require gh api
gh api repos/dtubb/fichero/milestones/57 -X PATCH -f description="Import tools and loaders: cloud-linked importers (Box, Dropbox — link without downloading), Kreuzberg/Docling PDF and image extraction, XMP sidecar support, XLSX/spreadsheet import, drag-in folder/file polish, folder watchers, pre-catalogued material import (skip re-extraction), Tinderbox .tbx importer, resumable large-corpus ingest."
```

---

## Section 1 — Wrong-Milestone: Re-file

### #743 — Engine: lazy-import heavy ML modules to drop cold-start from 25s to ~3s
- **State:** CLOSED / COMPLETED
- **Current milestone:** Importers
- **Problem:** This is an engine cold-start performance issue — lazy-importing ML modules at process startup. Has nothing to do with import *tools* (drag-drop, loaders, file importers). The issue body explicitly says "fits [best] in 0.0.3 KG Navigation + Polish" as a polish item. Belongs in **Infrastructure** or **Developer Experience**.
- **Action:** Re-milestone to Infrastructure (already has related startup issues there, e.g. #1341, #957).

```bash
gh issue edit 743 --repo dtubb/fichero --milestone "Infrastructure"
# Rationale: engine cold-start is a performance/infrastructure concern, not an import tool
```

### #996 — OpenAPI regen drops optional fields from schemas
- **State:** CLOSED / COMPLETED
- **Current milestone:** Importers
- **Problem:** This is about the OpenAPI schema regen dropping typed fields from the Swift client (`KnowledgeEntity`, `Document`, etc.). It affects the developer/build workflow, not any import mechanism. Belongs in **Developer Experience**.
- **Action:** Re-milestone to Developer Experience.

```bash
gh issue edit 996 --repo dtubb/fichero --milestone "Developer Experience"
# Rationale: OpenAPI schema drift is a DX/API contract issue, not an import tool
```

### #643 — SwiftLint cleanup: line-length, file-length, function-body, cyclomatic-complexity
- **State:** CLOSED / COMPLETED
- **Current milestone:** Importers
- **Problem:** SwiftLint violations cleanup across 10 Swift files. This is code quality / DX work, not specific to import tools. The affected files (`ActivityOverviewView`, `ContentView+Actions`, `SidebarItemRow`, etc.) are generic app files. Belongs in **Developer Experience**.
- **Action:** Re-milestone to Developer Experience.

```bash
gh issue edit 643 --repo dtubb/fichero --milestone "Developer Experience"
# Rationale: SwiftLint cleanup is DX/code-quality, not import tooling
```

---

## Section 2 — Un-milestoned Issues That Belong Here

### #1329 — Box importer (link, not download)
- **State:** OPEN
- **Current milestone:** NONE
- **Problem:** Box importer (link without downloading, OAuth, Box preview/streaming API) is explicitly named in the Importers milestone description. Has no labels. Belongs squarely in Importers.

```bash
gh issue edit 1329 --repo dtubb/fichero --milestone "Importers" --add-label "type:feature" --add-label "backend" --add-label "priority:P2"
# Rationale: core cloud importer, named in milestone description, currently orphaned
```

### #1330 — Dropbox importer (link, not download)
- **State:** OPEN
- **Current milestone:** NONE
- **Problem:** Same pattern as #1329 — Dropbox link-not-download importer. Explicitly in the milestone description. No labels. Belongs in Importers.

```bash
gh issue edit 1330 --repo dtubb/fichero --milestone "Importers" --add-label "type:feature" --add-label "backend" --add-label "priority:P2"
# Rationale: core cloud importer, named in milestone description, currently orphaned
```

---

## Section 3 — Reopen Candidates

### #597 — Library/sidebar: missing corner badge for link vs copy ingest mode (and future sync)
- **State:** CLOSED / NOT_PLANNED
- **Why reopen?** This was superseded by #603 and closed NOT_PLANNED. However #603 covered the *delete-confirmation copy* and *ingest mode badge* for link/copy/move — but the issue body here specifically mentions the **SYNC mode badge** as a future placeholder. The milestone description explicitly calls out "cloud-linked importers (Box, Dropbox)" landing in this milestone. When Box/Dropbox importers land, users will need to distinguish cloud-linked documents visually. The "sync" corner badge concept from #597 is directly needed. The NOT_PLANNED close was reasonable for 0.0.2 but with Box/Dropbox importers now in-scope, this has uncaptured value.
- **Reopen scope:** Narrow to the SYNC/cloud-link badge only (delete copy and link/copy/move badges are done in #603). Suggest retitling.

```bash
gh issue reopen 597 --repo dtubb/fichero
gh issue edit 597 --repo dtubb/fichero \
  --title "Library/sidebar: cloud-link badge for Box/Dropbox-imported items (sync mode visual indicator)" \
  --add-label "type:feature" \
  --add-label "client:swiftui" \
  --add-label "priority:P3"
# Rationale: Box/Dropbox importers (#1329, #1330) in-scope for this milestone; visual distinction for cloud-linked docs is necessary UX; NOT_PLANNED was pre-cloud-importer context
```

### #881 — Markdown / text-file ingest: no page_content, not searchable
- **State:** CLOSED / COMPLETED
- **Why reopen?** The issue was closed as completed, but the current git status shows `fichero/fichero/Views/Library/DocumentKGSurface.swift` is modified (appears in git status as modified at session start). More importantly, the issue describes a systematic problem with `.md`/`.txt` text extraction that manifests as silent failures leaving `page_content = None`. The body identifies a specific catch-at-WARNING-level pattern in `ingest.py` that silently swallows loader exceptions. Issue #1216 (P1 open) — "large folder ingest returns 200s but data is missing after relaunch" — is almost certainly the same root: the silent-failure pattern at the WARNING level. If #881 was "fixed" but #1216 re-exhibits the same silent-success/no-data pattern for folders, the fix was incomplete. Lean toward reopening to track the remaining silent-failure surface.

```bash
gh issue reopen 881 --repo dtubb/fichero
gh issue edit 881 --repo dtubb/fichero \
  --title "Ingest: silent WARNING-level failures leave page_content=None — text files and large folders not persisted" \
  --add-label "type:bug" \
  --add-label "backend" \
  --add-label "priority:P1"
# Rationale: #1216 (P1, open, large folder 200s but no data) shares the same silent-failure root cause documented here; the fix was incomplete; generous reopen to track the pattern rather than let it hide behind a new issue number
```

---

## Section 4 — Open Issues: Label Fixes

### #744 — Tinderbox importer: link a .tbx file → ingest notes into vector DB + KG
- **Current labels:** `backend`
- **Missing:** `type:feature`, `priority:P3`
- **Note:** Large, well-specified feature. P3 because it's future-milestone work (body says "Why 0.0.4") but in the Importers milestone.

```bash
gh issue edit 744 --repo dtubb/fichero --add-label "type:feature" --add-label "priority:P3"
```

### #739 — Ingest: resumable corpus pass with content-hash skip (100K-scale)
- **Current labels:** `backend`
- **Missing:** `type:feature`, `priority:P2`
- **Note:** Infrastructure-flavored but correctly in Importers (it's about the import pipeline resilience for large corpora). P2 because 100K-scale ingest is a named goal.

```bash
gh issue edit 739 --repo dtubb/fichero --add-label "type:feature" --add-label "priority:P2"
```

### #702 — Drag-drop: folder can be dropped onto a PDF row; no drop-line indicator when dragging a folder
- **Current labels:** `type:bug`, `client:swiftui`
- **Missing:** `priority:P2`
- **Note:** Active UX regression in the primary drag-drop import path.

```bash
gh issue edit 702 --repo dtubb/fichero --add-label "priority:P2"
```

### #1216 — backend: large folder ingest returns 200s but data is missing after relaunch
- **Labels:** `type:bug`, `backend`, `priority:P1` — CORRECT. No changes needed.

### #1340 — Kreuzberg loader writes cache to repo root
- **Labels:** `type:bug`, `backend`, `priority:P2` — CORRECT. No changes needed.

---

## Section 5 — Closed Issues: Retrospective Label Fixes

Priority labels are missing on 19 closed issues. These are retrospective — adding priority helps future trend analysis. Only listing issues worth the edit cost (skip very old 0.0.1 gate issues #383, #384 — too historical).

```bash
# Active-era issues missing priority labels (0.0.2 era and newer)
gh issue edit 1237 --repo dtubb/fichero --remove-label "type:task" --add-label "priority:P2"
# #1237: XLSX import — has both type:task AND type:feature (redundant type:task); P2 for medium-complexity feature

gh issue edit 1104 --repo dtubb/fichero --add-label "priority:P1" --add-label "backend"
# #1104: Filename loss on import — was a P1 regression; also missing backend label

gh issue edit 1085 --repo dtubb/fichero --add-label "client:swiftui"
# #1085: Maps .iffy.json sidecar pairing — has backend but also has CLI/SwiftUI import surface; add client:swiftui

gh issue edit 881 --repo dtubb/fichero --add-label "type:bug" --add-label "backend" --add-label "priority:P1"
# #881: (also a reopen candidate above — labels applied with reopen)

gh issue edit 610 --repo dtubb/fichero --add-label "priority:P2" --add-label "backend" --add-label "client:swiftui"
# #610: Folder drop flattening — P2, both backend and SwiftUI

gh issue edit 603 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
# #603: Ingest mode badges + delete copy — P2 polish

gh issue edit 587 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui" --add-label "backend"
# #587: Folder drop Transferable unwrap — P2

gh issue edit 582 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
# #582: Folder import not visible — P2

gh issue edit 571 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
# #571: Sidebar drag-drop broken — P2 (was a release blocker at the time)

gh issue edit 570 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
# #570: Drag-drop PDF nothing appears — P2

gh issue edit 561 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
# #561: Can't drag-drop folder — P2

gh issue edit 547 --repo dtubb/fichero --add-label "priority:P3" --add-label "client:swiftui"
# #547: JPG uppercase extension drop — P3 (edge case)

gh issue edit 542 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
# #542: Default import mode setting — P2

gh issue edit 540 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
# #540: Drop highlights entire window, PNG rejected — P2

# Very old issues (0.0.1 era) — skip retrospective label work on #353, #357, #358, #361, #383, #384, #597
# They are historically completed and the effort doesn't add value.
```

---

## Section 6 — Issues That Are Correctly Filed (No Action)

The following are correctly in the Importers milestone, correctly closed, and correctly scoped:

| # | Title | Notes |
|---|---|---|
| #1104 | Import endpoint loses filename | Correctly completed; filename now preserved |
| #1085 | Maps .iffy.json sidecar pairing | Correctly completed |
| #881 | Markdown text-file ingest | See reopen candidate above |
| #610 | Finder folder drop flattens children | Correctly completed |
| #603 | Ingest mode badges + delete confirmation | Correctly completed; superseded #597 |
| #587 | Folder drop Transferable unwrap | Correctly completed |
| #582 | Folder import not visible | Correctly completed |
| #571 | Sidebar drag-drop broken | Correctly completed |
| #570 | Drag-drop PDF nothing appears | Correctly completed |
| #561 | Can't drag-drop folder | Correctly completed |
| #547 | JPG uppercase extension | Correctly completed |
| #542 | Default import mode setting | Correctly completed |
| #540 | Drop highlights window, PNG rejected | Correctly completed |
| #361 | XMP sidecar support for images | Correctly completed |
| #358 | Image Sidecars: standardize XMP | Correctly completed (superseded by #361) |
| #357 | Folder Watchers (0.0.1 slice) | Correctly completed (full watcher lives in Infrastructure #359) |
| #353 | PDF Import | Correctly completed (foundational) |
| #384 | 0.0.1 image import reliability | Correctly completed (release gate) |
| #383 | 0.0.1 drag/drop reliability | Correctly completed (release gate) |

---

## Section 7 — Docling Issues (Not in Milestone)

Issues #56 and #61 (Docling investigation + PDF extraction via Docling) are closed NOT_PLANNED and have no milestone. These are correctly closed — Kreuzberg was adopted as the extraction engine, superseding the Docling investigation. No action needed. Do not reopen.

---

## Full Checklist (Execution Order)

### Step 1: Milestone description fix
```bash
gh api repos/dtubb/fichero/milestones/57 -X PATCH \
  -f description="Import tools and loaders: cloud-linked importers (Box, Dropbox — link without downloading), Kreuzberg PDF/image extraction, XMP sidecar support, XLSX/spreadsheet import, drag-in folder/file polish, folder watchers, pre-catalogued material import (skip re-extraction), Tinderbox .tbx importer, resumable large-corpus ingest."
```

### Step 2: Add un-milestoned issues
```bash
gh issue edit 1329 --repo dtubb/fichero --milestone "Importers" --add-label "type:feature" --add-label "backend" --add-label "priority:P2"
gh issue edit 1330 --repo dtubb/fichero --milestone "Importers" --add-label "type:feature" --add-label "backend" --add-label "priority:P2"
```

### Step 3: Re-milestone wrong-milestone issues
```bash
gh issue edit 743 --repo dtubb/fichero --milestone "Infrastructure"
gh issue edit 996 --repo dtubb/fichero --milestone "Developer Experience"
gh issue edit 643 --repo dtubb/fichero --milestone "Developer Experience"
```

### Step 4: Reopen candidates
```bash
gh issue reopen 597 --repo dtubb/fichero
gh issue edit 597 --repo dtubb/fichero \
  --title "Library/sidebar: cloud-link badge for Box/Dropbox-imported items (sync mode visual indicator)" \
  --add-label "type:feature" --add-label "client:swiftui" --add-label "priority:P3"

gh issue reopen 881 --repo dtubb/fichero
gh issue edit 881 --repo dtubb/fichero \
  --title "Ingest: silent WARNING-level failures leave page_content=None — text files and large folders not persisted" \
  --add-label "type:bug" --add-label "backend" --add-label "priority:P1"
```

### Step 5: Label fixes on open issues
```bash
gh issue edit 744 --repo dtubb/fichero --add-label "type:feature" --add-label "priority:P3"
gh issue edit 739 --repo dtubb/fichero --add-label "type:feature" --add-label "priority:P2"
gh issue edit 702 --repo dtubb/fichero --add-label "priority:P2"
```

### Step 6: Retrospective label fixes on closed issues (0.0.2-era)
```bash
gh issue edit 1237 --repo dtubb/fichero --remove-label "type:task" --add-label "priority:P2"
gh issue edit 1104 --repo dtubb/fichero --add-label "priority:P1" --add-label "backend"
gh issue edit 1085 --repo dtubb/fichero --add-label "client:swiftui"
gh issue edit 610 --repo dtubb/fichero --add-label "priority:P2" --add-label "backend" --add-label "client:swiftui"
gh issue edit 603 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
gh issue edit 587 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui" --add-label "backend"
gh issue edit 582 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
gh issue edit 571 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
gh issue edit 570 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
gh issue edit 561 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
gh issue edit 547 --repo dtubb/fichero --add-label "priority:P3" --add-label "client:swiftui"
gh issue edit 542 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
gh issue edit 540 --repo dtubb/fichero --add-label "priority:P2" --add-label "client:swiftui"
```
