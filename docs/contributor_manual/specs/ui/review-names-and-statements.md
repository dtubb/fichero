# Reviewing names and statements — the Mac review surfaces — Design Spec (#1677, #6280)

> Milestone: kg-entities-and-statements
> Manual: TBD — a section, "Checking names and statements", showing a researcher how to go through a
> folder's people, places and institutions and its statements beside the page, accept, fix, merge or
> reject each in a press or two, work the flagged list, and see how far along the folder is.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-10-29). The UX half of
> `../kg/kg-entities-and-statements.md` (owner, 2026-10-29: how a person reviews is a first-class
> question). Iterates on what the app has: the Document Inspector's Entities tab
> (`fichero/fichero/Views/Inspector/Knowledge/Entities/`), its entity arm and statements list
> (`kg-entity-inspector.md`), the Entities and Claims panes (`kg-tables.md`), the source
> click-through (`ClaimSourceRequest`), the per-window focus (`KGFocusState`), the pair queue and
> curation routes, and the bless, reject, rename, retype, merge and delete verbs the Entities tab's
> menus already offer. Retires in its favour the unmounted review sheets of #4828.
> Tags: **[OK]** · **[PARTIAL]** · **[GAP]** · **[BROKEN]**.

## Intent (the design)

A person checks a folder the way they read it: the page on the left, what was found on it on the
right, and one gesture per decision. Selecting a folder or a page opens the **review layout**:
Source (page image with the found names and statement spans marked, dashed until confirmed), Reader
(the text with the same marks), and the **review list** in the Inspector column: this scope's names
in three groups and its statements, each row with its state, its evidence and its verbs. The
**flagged list** sits at the top of the same column: what the engine was unsure of, with evidence,
one press to decide. A progress line says how far the scope is ("43 of 77 checked") and where to go
next. Everything is a key away; nothing opens a modal to do what a row can do in place.

## Prior art

Transkribus' tag review and Recogito's entity annotation (name on the text, a side panel to
confirm or relink), the Finder's inspector grammar this app follows (selection on the left,
detail on the right, verbs on the row), mail triage (one key per decision, the next item focused),
and nodegoat's reconciliation lists (candidate pairs with evidence, accept or reject).

## The layout

```
┌ Sidebar ─┬ Source (page image) ───────┬ Reader (text) ─────┬ Inspector ───────────────┐
│ Project  │ names and spans marked:    │ the same marks;    │ Review ▸ GHC_B12 Doc06   │
│  Sources │ dashed = proposed,         │ click a mark →     │ 43 of 77 checked ▸ Next  │
│   Doc06 ◀│ solid = confirmed,         │ row selected       │ ── Flagged (4) ─────────  │
│   Doc07  │ hidden = rejected          │                    │ [merge?] A ≈ B  ✓ ⇄ ✗ ⏎  │
│          │                            │                    │ ── People (31) ──────────│
│          │                            │                    │ ● Name  3 pp  ✓ ✎ ⇄ ✗    │
│          │                            │                    │ ── Places (9) ───────────│
│          │                            │                    │ ── Institutions (6) ─────│
│          │                            │                    │ ── Statements (31) ──────│
│          │                            │                    │ ○ S — V — O  p.4  ✓ ✎ ✗  │
└──────────┴────────────────────────────┴────────────────────┴──────────────────────────┘
```

## Behaviors

### A. Where review happens

- `review.layout-opens-from-a-folder-or-page` — **[GAP]** (#4978, #4886) selecting a folder or a
  page and choosing Review (sidebar row verb, the Knowledge menu, or ⌘⇧R) arranges Source, Reader
  and Inspector as above for that scope; the Inspector's review list is the folder lens of
  `kg.lens.folder-names` and `kg.lens.statements-of-a-scope`, one list, grouped: Flagged, People,
  Places, Institutions, Statements. Built: the Entities tab for one document, the panes; not
  built: the arrangement, the scope grouping, the flagged group.
- `review.marks-on-the-page` — **[PARTIAL]** (#5417, #2105) every name and statement in the list
  is marked on the page image and in the text at its span: dashed while proposed, solid once
  confirmed, hidden once rejected (`layers-on-the-source.md`); selecting a row lights its mark and
  scrolls both to it; clicking a mark selects its row. Built: the claim span click-through
  (`ClaimSourceRequest`, span > region > page); not built: marks for every row, the state styles,
  mark → row.
- `review.row-shows-its-evidence` — **[GAP]** (#2020, #4802) a name's row shows its canonical
  form, its forms as written, the pages in this scope that name it, its state, who made it, and a
  flag mark; a statement's row shows subject, verb and object as read, its date and place values,
  its page and line, and its state; hovering or pressing space shows the excerpt and the cropped
  line image (`SourceSnippet`, re-mounted).

### B. One press per decision

- `review.verbs-in-place` — **[PARTIAL]** (#1888, #4691) the verbs are on the row and in the
  menu: for a name, confirm (✓), edit (✎: canonical form, type, given names, surnames, role note,
  place type, parent place), merge into… (⇄, a picker of same-type names in scope with the
  unmistakable candidates first), reject (✗), skip; for a statement, confirm, edit (subject from
  the scope's names, verb, object, date, place), reject, skip. Edit is inline in the row, never a
  sheet; a destructive verb on many rows confirms once. Built: bless, reject, rename, retype,
  merge and delete on the Entities tab's menu; edit claim via a sheet; not built: inline edit,
  statement confirm from the row, the field set.
- `review.keyboard-flow` — **[GAP]** (#4794) with the list focused: ↑↓ move, ⏎ or Y confirm, N
  reject, M merge into…, E edit (⎋ cancels, ⏎ saves), S skip, ⌘Z undo the last decision, ⌘⌫
  delete, ⌘A select all shown, space shows the evidence, ⌥⏎ opens the source page; a decision
  moves focus to the next unchecked row in the same group; the same keys work in the Flagged
  group.
- `review.decision-is-one-audited-action` — **[PARTIAL]** (#5129, #4864) each verb is one engine
  action (the existing entity curation batch, `claim.transition`, `review.accept`,
  `review.reject`, `entity.merge`, `entity.update`), audited with the real actor, undone by ⌘Z
  from the same list; the row updates in place and the mark on the page follows; the engine's
  undo is built, the menu's is not (#5129).

### C. The flagged list

- `review.flagged-at-the-top` — **[GAP]** (#1677, #6280) the Flagged group lists this scope's
  items from `kg.lens.to-review`: a merge proposal (two names side by side: forms, pages,
  excerpts; ✓ merges into the first, ⇄ swaps which survives, ✗ rejects, S skips), a merge made by
  rule (undo), a type in doubt, a name the extractor was unsure of, a date disagreement, an
  untyped access point; each with its evidence and the same keys; an item leaves on a decision;
  an empty group says so. Replaces the unmounted `ClaimReviewQueueSheet`,
  `ContradictionTriageSheet`, `EntityReconciliationSheet` and `HeuristicReviewSheet` doors.
- `review.flag-count-in-the-sidebar` — **[GAP]** (#5413, #5508) a folder's row in the sidebar
  shows its flagged count; the project's row the total; an empty knowledge row offers the names
  step.

### D. Progress

- `review.progress-line` — **[GAP]** (#6283) the Inspector header reads "N of M checked" for the
  scope (checked = confirmed, rejected or merged, by a person), per group on hover ("People 20 of
  31"), with Next jumping to the first unchecked row; the folder's row in the Entities pane and
  the catalogue's folder table show the same fraction; a scope fully checked says so and offers
  the next folder.
- `review.proposed-is-visible-everywhere` — **[GAP]** (#4636, #5417) a proposed (unchecked) name
  or statement is drawn as proposed wherever it appears: dashed mark, a hollow state dot in the
  list, "proposed" in the catalogue entry and in any export that includes it.

### E. Statements beside their line

- `review.statement-opens-its-line` — **[PARTIAL]** (#4834, #4932) a statement's row is a door
  to its line: ⌥⏎ or a click on the page mark opens Source and Reader at the line with the span
  lit, at the precision recorded (span, region or page only, never approximated); a statement
  with no line says so and offers "tie to line" (pick the line in the Reader). Built: the
  precision-aware request from every surface; not built: the tie verb.
- `review.edit-subject-from-the-scope` — **[GAP]** (#4833) editing a statement's subject offers
  the scope's names (and "new name…"), writes `subject_entity_id`, and a date or place edit
  writes the value fields, never the subject slot.

## Build order

### Stage 6 — The review surfaces (after `../kg/kg-entities-and-statements.md` stages 1 and 2)

#### Step 6.1 — The review layout and the list with its evidence (#4978, #2020)
- Behaviours: `review.layout-opens-from-a-folder-or-page`, `review.row-shows-its-evidence`, `review.progress-line`
- Tests: fichero/Tests/Unit/general/Views/Library/ReviewLayoutArrangementTests.swift, fichero/Tests/Unit/general/Views/Inspector/ReviewListRowsTests.swift, fichero/Tests/Unit/general/Views/Inspector/ReviewProgressLineTests.swift
- Size: M

#### Step 6.2 — Verbs in place and the keyboard flow (#1888, #4794, #5129)
- Behaviours: `review.verbs-in-place`, `review.keyboard-flow`, `review.decision-is-one-audited-action`
- Tests: fichero/Tests/Unit/general/Views/Inspector/ReviewVerbsInPlaceTests.swift, fichero/Tests/Unit/general/Views/Inspector/ReviewKeyboardFlowTests.swift, fichero-server/tests/unit/api/test_review_decisions_audited_and_undoable.py
- Depends on: 6.1
- Size: M

#### Step 6.3 — The flagged group and the sidebar count (#1677, #6280, #5413)
- Behaviours: `review.flagged-at-the-top`, `review.flag-count-in-the-sidebar`
- Tests: fichero/Tests/Unit/general/Views/Inspector/FlaggedGroupTests.swift, fichero/Tests/Unit/general/Views/Sidebar/FlagCountRowTests.swift
- Depends on: 6.2
- Size: M

#### Step 6.4 — Marks on the page and statements beside their line (#5417, #4834, #4833)
- Behaviours: `review.marks-on-the-page`, `review.statement-opens-its-line`, `review.edit-subject-from-the-scope`, `review.proposed-is-visible-everywhere`
- Tests: fichero/Tests/Unit/general/Views/Preview/ReviewMarksStateStyleTests.swift, fichero/Tests/Unit/general/Models/ClaimSourceRequestTests.swift, fichero/Tests/Unit/general/Views/Inspector/StatementSubjectEditorTests.swift
- Depends on: 6.1
- Size: M

## Test matrix (legs this surface touches)

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | yes | grouping and order of the list; progress fraction; key → verb map; mark style by state | `fichero/Tests/Unit/general/Views/Inspector/` |
| Availability (Swift) | yes | every verb reachable from the row, the menu and the keyboard; the review layout from the sidebar and the menu | same |
| Visual / A11y | yes | `performAccessibilityAudit()` on the review list and flagged group; a screenshot of the layout | `fichero/Tests/UI/` |
| Backend (pytest) | yes | the scope route, the decisions, undo, the progress counts | `fichero-server/tests/unit/api/` |
| MCP / CLI | yes | the same decisions scriptable (an agent proposing, a person deciding) | `fichero-mcp/tests/test_mcp_generated.py`, `fichero-cli/tests/` |
| Click-around (Mac) | yes | select a folder → review layout → confirm a name with ⏎ → the mark turns solid and the count moves (navigation and rendering; verbs pinned at the action layer, per `../kg/kg-interactions.md`) | `fichero/Tests/UI/` |
| iPad | later | read-only review list | — |
| Load | yes | a folder of 200 pages and 3,000 rows: the list pages, keys stay instant (#5254) | `fichero-server/tests/perf/` |

## Open questions for the owner

1. **Review layout as its own saved workspace, or an arrangement of the current one?**
   Recommendation: a named arrangement (Review) the person can return to, per `panes-workspaces.md`.
2. **Confirm by default on ⏎, or require an explicit key?** Recommendation: ⏎ confirms; it is the
   common case, and ⌘Z is one key away.
