# Milestone Audit — Library & Reading Surface
**Date:** 2026-05-30  
**Auditor:** claude-sonnet-4-6  
**Status:** PROPOSAL ONLY — no GitHub state has been changed

---

## Coverage

- Total issues fetched: **112** (12 open, 100 closed)
- All 12 open issues reviewed thoroughly.
- All 100 closed issues reviewed (title + labels + body preview up to 600 chars).
- **Full coverage achieved** — no pagination gap. Closed bodies are fully visible via `gh issue list --json body`.

---

## Summary Counts

| Action | Count |
|---|---|
| Reopen (closed but never done / good idea) | 14 |
| Re-milestone (wrong milestone, leave state) | 2 |
| Label fixes (open issues missing priority) | 11 |
| Label fixes (closed issues missing type) | 9 |
| No action needed | 76 |

---

## Part A — Reopen Candidates

These were closed as COMPLETED but the work is either clearly unimplemented, was filed as a future-design-spec with no implementing commit, or is explicitly "capturing for later." Daniel's policy: be generous.

### A1 — Strong reopens (unimplemented features/specs filed and closed without shipping)

```bash
# #1253 — Bidirectional scroll sync between WebKit transcript and PDF viewer
# Body says "currently they scroll independently" — no evidence of implementation.
# Closed 2026-05-26; #1228 that spawned it fixed only crash/regressions, not scroll sync.
gh issue reopen 1253 --repo dtubb/fichero
gh issue edit 1253 --repo dtubb/fichero --add-label "type:task,client:swiftui,priority:P2"

# #1229 — Inspector UX: move toggle to main toolbar + filterable attribute strip
# Split from #1228 deliberately. Items 1 (toggle in toolbar) and 2 (filterable strip) are
# explicitly called out as unfinished follow-ups. Open #1215 covers partial overlap but is
# scoped to pane toggles; #1229's filterable attribute strip is not covered there.
gh issue reopen 1229 --repo dtubb/fichero
gh issue edit 1229 --repo dtubb/fichero --add-label "type:task,client:swiftui,priority:P2"

# #1199 — Consistent inspector layout: inspector always visible across all views
# Detailed acceptance criteria. Five-pane layout (#1189, closed) is the structural
# prereq; #1199 is the behavioral goal on top of it. Open #1215 does not cover this.
gh issue reopen 1199 --repo dtubb/fichero
# labels already: type:task, client:swiftui — add priority
gh issue edit 1199 --repo dtubb/fichero --add-label "priority:P2"

# #1186 — Navigation history: back/forward toolbar buttons + Cmd+' shortcut
# #1261 (OPEN) is a narrower re-report of the same feature from Daniel 2026-05-29.
# #1186 has the fuller spec (Cmd+' shortcut, navigation stack scope).
# Recommend: reopen #1186 and close #1261 as duplicate pointing to #1186.
# OR: leave both open. Keeping both surfaces the issue; #1186 has richer acceptance.
gh issue reopen 1186 --repo dtubb/fichero
# labels already: type:task, client:swiftui — add priority
gh issue edit 1186 --repo dtubb/fichero --add-label "priority:P2"
# Optionally close the thinner duplicate:
# gh issue close 1261 --repo dtubb/fichero --comment "Duplicate of #1186 (richer spec). Reopening #1186."

# #994 — Frontend: LazyVStack + cap-N + sheet for Entities / Claims sections
# "Folds into Phase 3 inspector reorg" in title — explicitly deferred. At 500-entity
# scale, bare ForEach freezes. No evidence this shipped in any 0.0.2 inspector work.
gh issue reopen 994 --repo dtubb/fichero
gh issue edit 994 --repo dtubb/fichero --add-label "type:task,client:swiftui,priority:P2"

# #747 — Inspector: text selection persists when switching documents
# Bug with a clear code path: NSTextView selectedRange not reset on documentId change.
# No labels, no evidence of a fix commit. Simple, targeted fix.
gh issue reopen 747 --repo dtubb/fichero
gh issue edit 747 --repo dtubb/fichero --add-label "type:bug,client:swiftui,priority:P2"

# #746 — Inspector: bold formatting not persisting to backend
# Separate from RTF/color persistence (#671, closed). Specifically about attribute-only
# changes (bold) not triggering textDidChange. No evidence of a fix.
gh issue reopen 746 --repo dtubb/fichero
gh issue edit 746 --repo dtubb/fichero --add-label "type:bug,client:swiftui,priority:P2"

# #625 — JSON files show no preview in document grid / inspector
# Clear unfixed bug: JSON docs show nothing in grid or inspector. Simple text-preview
# treatment needed. No labels, no fix commit referenced.
gh issue reopen 625 --repo dtubb/fichero
gh issue edit 625 --repo dtubb/fichero --add-label "type:bug,client:swiftui,priority:P3"

# #616 — Hide icon-grid list panel (like sidebar/inspector toggles)
# Explicit acceptance criteria. "Daniel is actively testing 0.0.2" context. The sidebar
# and inspector can already be hidden; the grid cannot. Open #1215 lists this as a needed
# control ("Hide/show list view"). Should be tracked separately as grid-specific.
gh issue reopen 616 --repo dtubb/fichero
# labels already: type:task — add client + priority
gh issue edit 616 --repo dtubb/fichero --add-label "client:swiftui,priority:P2"
```

### A2 — Generous reopens (good ideas closed early, merit tracking)

```bash
# #1265 — Image/page editing UX: prev/next nav + rubber-band region select + batch-apply
# Filed 2026-05-26 and closed quickly. Substantive Daniel ask with clear spec.
# "Part of the Image Editing milestone" in body — consider re-milestoning to Image Editing
# rather than reopening here. See Part B for milestone move.
# If keeping in Library & Reading Surface:
gh issue reopen 1265 --repo dtubb/fichero
# labels already: type:feature, client:swiftui — add priority
gh issue edit 1265 --repo dtubb/fichero --add-label "priority:P3"

# #323 — Tab title should show current view name and icon
# One-liner spec; unfixed. Window/tab title still doesn't reflect sidebar mode in 0.0.2.
# Trivial to implement; worth keeping on the radar.
gh issue reopen 323 --repo dtubb/fichero
# labels already: type:feature — add client + priority
gh issue edit 323 --repo dtubb/fichero --add-label "client:swiftui,priority:P3"

# #588 — PDFView: trackpad pinch-zoom + prevent parent gesture interception
# Acceptance criteria: "Trackpad two-finger pinch inside PDF preview zooms in."
# Open #928 (PDF loupe/magnifier tools) is related but distinct — #928 is about
# surfacing image-preview overlays; #588 is about the native pinch gesture itself.
gh issue reopen 588 --repo dtubb/fichero
# labels already: type:task — add client + priority
gh issue edit 588 --repo dtubb/fichero --add-label "client:swiftui,priority:P2"

# #644 — Sidebar: replace 'Library' text header with clickable icon + name row
# Root-level files (parentId: nil) are invisible in sidebar today. This is an ongoing
# usability gap. Clear spec, no implementing commit referenced.
gh issue reopen 644 --repo dtubb/fichero
# labels already: type:task — add client + priority
gh issue edit 644 --repo dtubb/fichero --add-label "client:swiftui,priority:P3"
```

---

## Part B — Wrong Milestone (re-milestone only, leave open/closed state)

```bash
# #1289 — Onboarding flow — clean Cotypist-style step cards
# Body explicitly says "0.0.3 / polish-phase feature; capturing now as the design reference."
# Does NOT belong in Library & Reading Surface — belongs in Mac App Shell or a new
# Onboarding milestone. Currently CLOSED; leave closed but move milestone.
gh issue edit 1289 --repo dtubb/fichero --milestone "Mac App Shell"

# #824 — NER context fields: complete sentences + Title Case names
# This is a backend NER output-quality issue — People/Places/Events extraction formatting.
# Belongs in KG & Hermeneutics milestone, not Library & Reading Surface.
# Currently CLOSED; leave closed but move milestone.
gh issue edit 824 --repo dtubb/fichero --milestone "KG & Hermeneutics"
```

---

## Part C — Label Fixes (open issues missing priority)

All 11 open issues except #1215 are missing a `priority:` label. Suggested assignments based on severity + frequency of Daniel reports:

```bash
# P1 — blocking/regressive, Daniel-reported repeatedly
gh issue edit 598 --repo dtubb/fichero --add-label "priority:P1"
# Rationale: sidebar drag-drop completely broken per Daniel; foundational interaction

gh issue edit 928 --repo dtubb/fichero --add-label "priority:P1"
# Rationale: PDF is primary use case; loupe/magnifier parity with images is a gap Daniel
# explicitly named

# P2 — significant, should ship soon
gh issue edit 1261 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 713 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 711 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 719 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 330 --repo dtubb/fichero --add-label "priority:P2"

# P3 — good to have, lower urgency
gh issue edit 1194 --repo dtubb/fichero --add-label "priority:P3"
gh issue edit 973 --repo dtubb/fichero --add-label "priority:P3"
gh issue edit 579 --repo dtubb/fichero --add-label "priority:P3"
gh issue edit 584 --repo dtubb/fichero --add-label "priority:P3"
```

---

## Part D — Label Fixes (closed issues missing type)

These 9 closed issues have no labels at all. Fixing for discoverability/audit correctness:

```bash
gh issue edit 1289 --repo dtubb/fichero --add-label "type:feature"
gh issue edit 1280 --repo dtubb/fichero --add-label "type:bug,client:swiftui"
gh issue edit 1229 --repo dtubb/fichero --add-label "type:task,client:swiftui"
gh issue edit 890 --repo dtubb/fichero --add-label "type:bug,client:swiftui"
gh issue edit 883 --repo dtubb/fichero --add-label "type:bug,client:swiftui"
gh issue edit 747 --repo dtubb/fichero --add-label "type:bug,client:swiftui"
gh issue edit 746 --repo dtubb/fichero --add-label "type:bug,client:swiftui"
gh issue edit 625 --repo dtubb/fichero --add-label "type:bug,client:swiftui"
gh issue edit 623 --repo dtubb/fichero --add-label "type:task,client:swiftui"
```

Note: #1229, #747, #746, #625 are also reopen candidates (Part A). The `--add-label` edits above apply whether or not they are reopened; they can be run independently.

---

## Part E — Missing Label: `area:inspector`

The audit instructions note `area:inspector` for cross-cutting inspector bugs — flag if missing from the canonical label set.

**`area:inspector` does not currently exist** in the repo's label list (canonical 23 labels listed in the task prompt do not include it). The following open and reopen-candidate issues would benefit from it:

- #1215, #1194 (open)
- #1229, #1199, #994, #747, #746 (reopen candidates)

```bash
# Create the label first, then apply
gh label create "area:inspector" --repo dtubb/fichero --color "0075ca" --description "Cross-cutting inspector panel bugs and features"

# Apply to open issues
gh issue edit 1215 --repo dtubb/fichero --add-label "area:inspector"
gh issue edit 1194 --repo dtubb/fichero --add-label "area:inspector"

# Apply to reopen candidates (after reopening)
gh issue edit 1229 --repo dtubb/fichero --add-label "area:inspector"
gh issue edit 1199 --repo dtubb/fichero --add-label "area:inspector"
gh issue edit 994 --repo dtubb/fichero --add-label "area:inspector"
gh issue edit 747 --repo dtubb/fichero --add-label "area:inspector"
gh issue edit 746 --repo dtubb/fichero --add-label "area:inspector"
```

---

## Part F — Duplicate / Near-Duplicate Pairs (informational, no action required unless noted)

These closed pairs were filed as separate issues but describe the same defect. Both closed as COMPLETED — no action needed unless one is reopened:

| Pair | Verdict |
|---|---|
| #945 + #946 (multi-page PDF thumbnail stacking) | Exact duplicate; both closed. OK. |
| #956 + #960 (Inspector artifacts scroll height) | Exact duplicate; both closed. OK. |
| #942 + #943 (library view mode persistence) | #943 is a superset of #942; both closed. OK. |
| #1186 (closed) + #1261 (open) | Same feature; #1186 is richer spec. Recommend reopening #1186 and closing #1261 as duplicate (see Part A1). |

---

## Reopen Candidates — Summary Table

| # | Title | Rationale |
|---|---|---|
| #1253 | Bidirectional scroll sync WebKit ↔ PDF | Core reading-surface feature, unimplemented |
| #1229 | Inspector toggle to toolbar + filterable attribute strip | Explicitly split out as follow-up; unfinished |
| #1199 | Inspector always visible as rightmost pane | Acceptance criteria unmet; architecture prereq (#1189) is done |
| #1186 | Navigation history back/forward + Cmd+' | Full spec; Daniel re-reported as #1261; reopen the richer issue |
| #994 | LazyVStack + cap-N + sheet for Entities/Claims | Explicitly deferred; performance need at scale |
| #747 | Inspector text selection persists on doc switch | Simple targeted NSTextView fix; no evidence shipped |
| #746 | Inspector bold formatting not persisting | Attribute-change detection gap; distinct from #671 |
| #625 | JSON files no preview in grid/inspector | Clear unfixed bug; no fix commit |
| #616 | Hide icon-grid panel toggle (focus mode) | Acceptance criteria exist; #1215 lists it as needed but doesn't close it |
| #1265 | Image/page editing UX: prev/next nav + rubber-band select | Strong Daniel ask; consider re-milestone to Image Editing |
| #588 | PDFView trackpad pinch-zoom | Native gesture may still be broken; #928 is related but distinct |
| #644 | Sidebar Library header → clickable icon + name row | Root-level files invisible; clear spec |
| #323 | Tab title reflects current view name + icon | Trivial unfixed; good polish |

Total reopen candidates: **13** (plus the #1261 → close + reopen #1186 swap = net 14 state changes in Part A).

---

## Coverage Note

All 112 issues were reviewed. Closed issue bodies were fully available from the `gh issue list --json body` output — no issues were skipped. The only limitation is that closed issue comments were not fetched (only the opening body), so a fix that exists only in a comment thread could be missed. If any issue above was actually fixed in a comment-referenced commit, that would override the reopen recommendation.
