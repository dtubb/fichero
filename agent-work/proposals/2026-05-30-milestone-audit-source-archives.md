# Milestone Audit — Source Archives
**Date:** 2026-05-30
**Auditor:** claude-sonnet-4-6
**Scope:** All 7 issues in `dtubb/fichero` milestone "Source Archives" (milestone #65), plus boundary review against "Importers" (milestone #57).

---

## Summary

| Category | Count |
|---|---|
| Total issues in milestone | 7 |
| Open | 6 |
| Closed (completed, genuine) | 1 |
| **Reopen candidates** | **0** |
| Wrong-milestone (re-file) | 0 |
| Label fixes needed | 7 (all lack `priority:` and `client:`) |
| Importers milestone description conflict | 1 (description body only, no issue moves needed) |
| New milestone proposals | 0 |

**Verdict:** The Source Archives milestone is clean — every issue is correctly placed, genuinely scoped to a corpus import (not an import tool), and the one closed issue (#1231 slipbox) was truly completed with a real artifact and owner comment. No reopens warranted. The main actionable work is adding missing `priority:` and `client:` labels to all 7 issues, and correcting the Importers milestone description which still names these corpora as its own scope.

---

## Issue-by-Issue Analysis

### #1231 — Release data: import slipbox from Tinderbox and filesystem into Fichero
- **State:** CLOSED / COMPLETED
- **Genuinely done?** YES. Owner comment on 2026-05-27: "Merged to 0.0.2 — standalone 'import-slipbox' CLI (filesystem + Tinderbox .tbx → Fichero catalogue). 93 tests pass; real-sample import verified searchable." Real artifact exists.
- **Reopen?** No.
- **Labels:** `type:task`, `type:feature` — missing `priority:P2` (completed data work, retrospective) and `client:cli` (the deliver was a CLI command).
- **Milestone boundary:** Correctly in Source Archives (corpus import, not tool). Note: the closure comment calls out that #1232 (maps) was not finished at time of close — it's still open, correctly.

### #1232 — Release data: create Fichero database for Chota Valley and Colombian Pacific maps
- **State:** OPEN
- **Reopen candidate?** N/A — already open.
- **Status:** Triage comment (2026-05-28) confirms no committed artifact found; genuinely incomplete.
- **Blocker note:** The #1231 closure comment noted "Maps import (#1232) still needs the real ~/code/maps path" — path is now documented in the issue body as `/Users/danieltubb/code/maps_southern_colombia`. No blocker label currently.
- **Labels:** `type:task`, `type:feature` — missing `priority:P2`, `client:cli` or `backend`.

### #1233 — Release data: import already-catalogued GHC materials (including ACENET imports) into Fichero
- **State:** OPEN
- **Status:** Triage comment (2026-05-28) confirms no committed artifact. Genuinely incomplete.
- **Labels:** `type:task`, `type:feature` — missing `priority:P2`, `backend`.

### #1234 — Release data: import Archivo Judicial de Medellin catalogue into Fichero
- **State:** OPEN
- **Status:** Triage comment (2026-05-28) confirms no committed artifact. Genuinely incomplete.
- **Labels:** `type:task`, `type:feature` — missing `priority:P2`, `backend`.

### #1235 — Release data: import Sergio Mosquera notebooks and catalogue spreadsheet into Fichero
- **State:** OPEN
- **Status:** Triage comment (2026-05-28) confirms no committed artifact. Genuinely incomplete.
- **Dependency note:** Issue body says "may depend on spreadsheet/XLSX import support." #1237 (XLSX importer tool) is CLOSED/COMPLETED in Importers milestone as of 2026-05-26, so the dependency is resolved — no blocker needed.
- **Labels:** `type:task`, `type:feature` — missing `priority:P2`, `backend`.

### #1236 — Release data: import Newton C. Marshall diary materials into Fichero
- **State:** OPEN
- **Status:** Triage comment (2026-05-28) confirms no committed artifact. Genuinely incomplete.
- **Labels:** `type:task`, `type:feature` — missing `priority:P2`, `backend`.

### #1238 — Release data: one-time import of Istmina mineria transcript workflow outputs into Fichero
- **State:** OPEN
- **Status:** Triage comment (2026-05-28) confirms no committed artifact. Genuinely incomplete.
- **Labels:** `type:task`, `type:feature` — missing `priority:P2`, `backend`.

---

## Reopen Candidates

**None.** The one closed issue (#1231) was genuinely completed with a verified artifact. All other issues remain open.

---

## Importers Milestone Description Conflict

The "Importers" milestone (milestone #57) description currently reads:

> "Cloud-linked importers (Box, Dropbox) that link without downloading. **Release-data import flows (Black folder + Maps folder metadata fusion, Chota Valley maps, Archivo Judicial, Mosquera notebooks, Marshall diary, Istmina).** XLSX/spreadsheet import. Drag-in folder/file polish. Pre-catalogued material import (skip re-extraction)."

The corpus names (Chota Valley maps, Archivo Judicial, Mosquera notebooks, Marshall diary, Istmina) belong to **Source Archives**, not Importers. The issues themselves are correctly milestoned in Source Archives (#1232–#1238). Only the Importers **description text** is stale/misleading. The Source Archives milestone description is already correct.

---

## Executable Checklist

### A. Label Fixes (7 issues)

Add `priority:P2` to all open corpus-import issues (reasonable default for release-data work — not blocking a P0 user-facing crash, but needed for `0.0.2` demo). Add `backend` to the five that are clearly backend ingest work. Add `client:cli` to #1232 (maps has CLI delivery path per #1231 pattern).

```bash
# #1232 — Maps
gh issue edit 1232 --repo dtubb/fichero --add-label "priority:P2,backend,client:cli"

# #1233 — GHC/ACENET
gh issue edit 1233 --repo dtubb/fichero --add-label "priority:P2,backend"

# #1234 — Archivo Judicial
gh issue edit 1234 --repo dtubb/fichero --add-label "priority:P2,backend"

# #1235 — Mosquera notebooks
gh issue edit 1235 --repo dtubb/fichero --add-label "priority:P2,backend"

# #1236 — Marshall diary
gh issue edit 1236 --repo dtubb/fichero --add-label "priority:P2,backend"

# #1238 — Istmina mineria
gh issue edit 1238 --repo dtubb/fichero --add-label "priority:P2,backend"

# #1231 — Slipbox (closed; retrospective label for completeness)
gh issue edit 1231 --repo dtubb/fichero --add-label "priority:P2,client:cli"
```

### B. Importers Milestone Description Correction

Remove the corpus names from the Importers description so the boundary is unambiguous. Proposed replacement:

```bash
gh api repos/dtubb/fichero/milestones/57 \
  --method PATCH \
  --field description="Cloud-linked importers (Box, Dropbox) that link without downloading. XLSX/spreadsheet import. Drag-in folder/file polish. Pre-catalogued material import (skip re-extraction). Resumable corpus pass (#739). Tinderbox .tbx importer (#744). Note: corpus-specific import tasks (Chota Valley, Archivo Judicial, Mosquera, Marshall diary, Istmina, GHC/ACENET) live in the Source Archives milestone."
```

### C. Reopens

None proposed.

### D. Re-milestone

No issues need to move. All 7 are correctly placed in Source Archives. No issues in other milestones were found to be misplaced corpus-import work.

### E. New Milestones

None proposed. All identified corpus collections already have issues.

---

## Boundary Reference (for future filing)

| Issue type | Correct milestone |
|---|---|
| Import TOOL (loader, parser, sync engine) | Importers |
| Corpus DATA import (specific collection, one-time or scheduled ingest) | Source Archives |
| Tinderbox importer tool (#744) | Importers ✓ |
| XLSX importer tool (#1237) | Importers ✓ |
| Slipbox import (#1231) | Source Archives ✓ |
| Maps import (#1232) | Source Archives ✓ |
| Any new "import the XYZ archive" issue | Source Archives |
| Any new "build a loader for format X" issue | Importers |
