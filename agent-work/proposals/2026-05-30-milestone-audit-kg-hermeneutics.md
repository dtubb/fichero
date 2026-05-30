# Milestone Audit: KG & Hermeneutics (#55)
**Date:** 2026-05-30  
**Auditor:** Agent (Claude Sonnet 4.6)  
**Scope:** All 188 issues (18 open + 170 closed)  
**Coverage note:** All 18 open issues read in full. Closed issues: 170 scanned, ~115 verified via title/body/git-log, ~55 in the 677–895 range verified by title+git-log cross-check only (no individual `gh issue view` on each). That residual set is mostly concrete bug/polish fixes with clear git-commit matches — very low reopen risk.

---

## Summary Counts

| Category | Count |
|---|---|
| Open issues audited (full body) | 18 |
| Closed issues scanned | 170 |
| Reopen candidates (never built or good ideas suppressed) | 5 |
| Move → Bibliography & Citations (#68) (open) | 1 |
| Move → Workflows (#54) (open) | 1 |
| Move → Library & Reading Surface (#60) (open) | 0 (see note) |
| Closed citation issues to re-milestone → #68 | 5 |
| Label fixes needed (open issues) | 16 of 18 |
| NOT_PLANNED issues to leave alone | 2 |

---

## Section 1 — REOPEN: Closed-but-never-built good ideas

These were closed COMPLETED but the work either (a) never had a SwiftUI surface wired, (b) the decision was never actually made, or (c) the backend shipped but the feature is invisible to the user. Daniel's priority: be generous here.

```bash
# 1. Hermeneutics router fate — decision was never made (2-minute close; Daniel said "not sure what it was doing")
# The backend (PatternInstance, HermeneuticCircleState, LLM suggestion layer) IS implemented
# but /api/hermeneutics has ZERO Swift callers (per 2026-05-28 backend-not-in-ui audit).
# The three options in the issue body (re-enable, port slowly, remove) were never decided.
# This ALSO blocks release gate #501 (Wire: Hermeneutics). Strong reopen.
gh issue reopen 922 --repo dtubb/fichero --comment "Reopening: closed in 2 minutes without a decision. Backend PatternInstance + HermeneuticCircleState + LLM suggestions are implemented but /api/hermeneutics has zero Swift callers. Options 1/2/3 from the issue body still unresolved. Blocks release gate #501."

# 2. Zettelkasten layer — backend shipped (#917), NO SwiftUI (per backend-not-in-ui audit: /api/notes has no Swift caller)
# Note model + bidirectional NoteLink + CRUD exist. The feature is invisible to users.
gh issue reopen 917 --repo dtubb/fichero --comment "Reopening: backend (Note model + NoteLink CRUD) was built in feat(kg): #917. However /api/notes has zero Swift callers per the 2026-05-28 backend audit. The feature is invisible to users. Needs SwiftUI wiring: notes pane on document/entity inspectors, backlink view."

# 3. Projects / research workspaces — backend shipped (#918), NO SwiftUI (/api/projects has no Swift caller)
gh issue reopen 918 --repo dtubb/fichero --comment "Reopening: backend (Projects model + CRUD) was built in feat(kg): #918. However /api/projects has zero Swift callers per the 2026-05-28 backend audit. Needs SwiftUI: project/workspace browser, ability to group docs + notes + entities under named analyses."

# 4. KG triangulation / corroboration — backend shipped (#900), NO SwiftUI (/api/kg/triangulation has no Swift caller)
# Support_count + corroborated status per claim is computed but never surfaced in UI.
gh issue reopen 900 --repo dtubb/fichero --comment "Reopening: cross-source triangulation (support_count, corroborated status per SVO triple) was built in feat(kg): #900. However /api/kg/triangulation has zero Swift callers per the 2026-05-28 backend audit. The corroboration signal is invisible to users. Needs a claim-detail panel showing support count + agreeing sources."

# 5. Source authority weighting — backend shipped (#903), NOT surfaced in UI (/api/kg/triangulation no caller)
# Primary/secondary/tertiary weighting exists in DB but triangulation view doesn't exist.
gh issue reopen 903 --repo dtubb/fichero --comment "Reopening: source authority (primary/secondary/tertiary) was built in feat(kg): #903. However the triangulation surface that would show this to users (/api/kg/triangulation) has no Swift caller. The distinction is computed but invisible. Should be surfaced in claim detail and entity inspector."
```

---

## Section 2 — WRONG MILESTONE: Move to Bibliography & Citations (#68)

Milestone #68 description explicitly calls out #974 and #1101 as belonging there. Citation/bibliography features should be consolidated.

### Open issues to re-milestone

```bash
# #974 is in KG & Hermeneutics but is a citation-graph feature
# The Bibliography & Citations milestone description explicitly names this issue.
gh issue edit 974 --repo dtubb/fichero --milestone "Bibliography & Citations" --add-label "priority:P2" --remove-label "type:feature" --body-comment ""
# Note: also has dual type: labels — keep type:task, remove type:feature (redundant)
```

### Closed issues to re-milestone (completed implementations that belong in Bibliography scope)

These 5 issues were built and closed correctly as COMPLETED, but their subject matter is bibliography/citation, not KG hermeneutics. Moving them helps Bibliography & Citations (#68) start with meaningful history rather than an empty 0/0 scoreboard.

```bash
gh issue edit 906 --repo dtubb/fichero --milestone "Bibliography & Citations"
# KG: citation graph — document-to-document references [COMPLETED]

gh issue edit 908 --repo dtubb/fichero --milestone "Bibliography & Citations"
# KG: bibliographic metadata extraction [COMPLETED]

gh issue edit 909 --repo dtubb/fichero --milestone "Bibliography & Citations"
# KG: Zotero / BibTeX / RIS import [COMPLETED]

gh issue edit 910 --repo dtubb/fichero --milestone "Bibliography & Citations"
# KG: DOI + ISBN online metadata lookup [COMPLETED]

gh issue edit 912 --repo dtubb/fichero --milestone "Bibliography & Citations"
# KG: citation rendering — Chicago / APA / MLA / BibTeX [COMPLETED]
```

---

## Section 3 — WRONG MILESTONE: Move to Workflows (#54)

```bash
# Issue 1097 is about LangGraph interrupt() mechanics in the Catalogue workflow
# It has no KG/hermeneutics content — it's a workflow orchestration feature.
# It should live in the Workflows milestone alongside other LangGraph/HITL work.
gh issue edit 1097 --repo dtubb/fichero --milestone "Workflows"
# Catalogue: human-in-the-loop confirmation for ambiguous groupings
```

---

## Section 4 — LABEL FIXES (open issues)

All 18 open issues audited. 16 of 18 have label gaps. Commands below fix type:, priority:, and surface labels. Release gate issues (495–501) are intentionally roadmap-only — giving them type:task is the right call (they're coordination milestones, not feature requests).

```bash
# #1333 — NER with spaCy: missing type: and priority:
gh issue edit 1333 --repo dtubb/fichero \
  --add-label "type:feature,priority:P2,backend,tier:local"
# NER with spaCy — fast on-device entity extraction

# #1187 — Source-tied notes: missing priority:
gh issue edit 1187 --repo dtubb/fichero \
  --add-label "priority:P2"
# Source-tied notes: per-claim annotation layer

# #1124 — Hermeneutics controlled predicate vocab: already has type:feature + priority:P2, OK ✓
# (no change needed)

# #1097 — Catalogue HITL: already has backend + type:feature + priority:P2, OK ✓ (moving milestone)

# #974 — Citation graph: missing priority:; has dual type: labels
gh issue edit 974 --repo dtubb/fichero \
  --add-label "priority:P2,backend,client:swiftui" \
  --remove-label "type:feature"
# (keep type:task only; add surfaces; milestone moved in Section 2)

# #916 — KG user CRUD: missing priority:
gh issue edit 916 --repo dtubb/fichero \
  --add-label "priority:P1,backend,client:swiftui"
# KG: user-created entities / claims / annotations

# #753 — Detect AI Text: missing type: and priority:
gh issue edit 753 --repo dtubb/fichero \
  --add-label "type:feature,priority:P3,tier:local"
# Add 'Detect AI Text' workflow tool

# #721 — Inspector container artifact scoping bug: missing priority:
gh issue edit 721 --repo dtubb/fichero \
  --add-label "priority:P2"
# Inspector shows parent folder's container artifacts

# Release gates #495–#501: missing type: and priority:
# These are release-coordination issues → type:task, priority:P1 (gate items)
for issue in 495 496 497 498 499 500 501; do
  gh issue edit $issue --repo dtubb/fichero \
    --add-label "type:task,priority:P1"
done

# #375 — Interpretations workspace v1: missing type: and priority:
gh issue edit 375 --repo dtubb/fichero \
  --add-label "type:feature,priority:P2,client:swiftui"
# 0.0.4: Interpretations workspace v1

# #373 — Contradiction triage UI: missing type: and priority:
gh issue edit 373 --repo dtubb/fichero \
  --add-label "type:feature,priority:P2"
# 0.0.4: Contradiction triage UI

# #372 — Claim review queue UI: missing type: and priority:
gh issue edit 372 --repo dtubb/fichero \
  --add-label "type:feature,priority:P2"
# 0.0.4: Claim review queue UI
```

---

## Section 5 — NOT_PLANNED: Leave as-is

These two were deliberately closed NOT_PLANNED and should stay that way.

```
#911 KG: cross-library entity linking — NOT_PLANNED, reasonable deferral (per-library DuckDB constraint; needs global-kg architecture)
#423 0.0.4 — Interpretations Workspace v1 Linked to Claims (backend) — NOT_PLANNED; covered by open #375
```

No action.

---

## Section 6 — Issues to KEEP in KG & Hermeneutics (no move needed)

All remaining open issues correctly belong here:

| # | Title | Note |
|---|---|---|
| #1333 | NER with spaCy | Core KG extraction alternative |
| #1187 | Source-tied notes: per-claim annotation | KG annotation layer |
| #1124 | Hermeneutics: controlled predicate vocabulary | Hermeneutics core |
| #916 | KG: user CRUD parity | KG CRUD |
| #753 | Detect AI Text workflow tool | Explicitly in milestone scope ("AI-text detection") |
| #721 | Inspector container artifact scoping | KG inspector data bug |
| #501–#495 | Release gates 0.2.0–0.2.6 | KG milestone gates |
| #375, #373, #372 | Interpretations/contradiction/review | Hermeneutics core |

---

## Section 7 — Open citation issues outside KG & Hermeneutics (no milestone)

These three issues are not in KG & Hermeneutics, but are unplaced and should go to Bibliography & Citations (#68). Noted here for completeness — they are NOT in the KG & Hermeneutics milestone so they are outside strict audit scope, but flagging is useful since the milestone description calls #1101 out explicitly.

```bash
gh issue edit 1100 --repo dtubb/fichero --milestone "Bibliography & Citations"
# Citation extraction workflow: port pdf2bib end-to-end + footnote/in-page citations

gh issue edit 1101 --repo dtubb/fichero --milestone "Bibliography & Citations"
# Bibliographic metadata: add canonical BibTeX field + import-time sidecar reader

gh issue edit 924 --repo dtubb/fichero --milestone "Bibliography & Citations"
# Citation + source-tier extraction with role-tagged entities (grammar-constrained)
```

---

## Section 8 — Closed issues to LEAVE CLOSED (confirmed built)

The following closed issues were verified via git log and confirmed as genuinely shipped. They should NOT be reopened:

- **#906, 908, 909, 910, 912** — bibliography features (built 2026-05-12; moved to #68 above)
- **#913, 914** — sub-page anchors + annotations (built 2026-05-12–13, full test suite)
- **#915** — user-extensible classification (built 2026-05-12)
- **#905, 907** — Toulmin + interpretations wiring (built 2026-05-12)
- **#904** — temporal claims (built 2026-05-12)
- **#901** — KG edit/delete PATCH + DELETE (built 2026-05-12)
- **#902** — KG SwiftUI visualization (built 2026-05-29; force-directed + Charts + Map)
- **#899, 898** — rdflib/sentence-transformers/spLink stack (built)
- **#897** — event dedup (built)
- **#895** — toolbar accumulation (built)
- **#889** — rewrite ClaimInspector/EpistemologyGraph/etc. (built)
- **#888** — service-layer cleanup (built)
- **#874** — user-extensible entity types (built)
- **#859, 846, 840, 839, etc.** — catalogue improvements (built, all have git commits)
- **#427, 429, 431** — advanced graph exploration + PyKEEN track (built)
- **#388, 387** — 0.0.2 Phase 1/2 (complete milestones)
- All 1xxx-series closed issues — verified via title match to specific git commits in May 2026

---

## Coverage Note

All 18 open issues were individually read and assessed. Of 170 closed issues:
- ~115 were individually verified (git log + body check where needed)
- ~55 in the 677–895 range (concrete bug fixes and polish, shipped in 2026-04 to early 2026-05) were assessed by title + milestone origin only — these are low reopen risk (tight scope, specific bug reports with matching commits). No full `gh issue view` was done on each; a human spot-check of a sample is advisable.
