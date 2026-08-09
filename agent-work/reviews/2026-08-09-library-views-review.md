# Library views review — icon, list, table, columns (2026-08-09)

Read-only review for Daniel. Finder is the reference; his screenshot rulings
beat older notes in the code. Every mechanism carries `file:line`. Anything I
reasoned to rather than read is marked **INFERRED**. Paths are relative to
`fichero/fichero/`.

Scope note: `LibraryView.swift`, `LibraryView+TableView.swift` and
`LibraryView+ArrowNavigation.swift` were being edited by the code lane while I
read them, so line numbers in those three may have shifted by the time you read
this. The mechanisms will not have.

---

## The headline: the grammar is good, the plumbing around it is not

This is not a codebase that got selection wrong through carelessness. There is
one real grammar — `Models/Selection/SelectionGrammar.swift` — and it is
genuinely well thought through: the two anchor rules at
`SelectionGrammar.swift:26-34` are the difference between multi-select feeling
right and feeling nearly right, and they are correct. `LibraryKeyboardCursor`
(`Views/Library/LibraryView+ArrowNavigation.swift:8-23`) is the right idea:
cursor, then anchor, then topmost-in-visual-order, *never* `Set.first`.

The defects below are almost all one shape: **the grammar is right, and
something outside it re-answers the same question by hand.** That is worth
saying plainly because it changes what "fixing the library views" means — it is
mostly deletion and delegation, not new logic.

---

## Correctness bugs

### B1. Right-click acts on rows you did not click — CHEAP, CERTAIN

`Views/Library/LibraryView+ContextMenu.swift:394`

```swift
let targetIds = selection.isEmpty ? [document.id] : Array(selection)
```

Select A and B, then right-click C (not selected). "Exclude/Include from
Processing" applies to **A and B**. The clicked row is ignored entirely.

Finder's rule — a right-click outside the selection acts on the clicked row —
is implemented correctly *twice in the same file*: `imageStackTargets` guards
with `selection.contains(document.id) && selection.count > 1`
(`:403`), and `addToChatMenuItem` replaces the selection when the clicked row is
outside it (`:120`). `Views/Library/LibraryView+DeleteActions.swift:79-87` gets
it right a third way.

Swept: `selection.isEmpty ? [` appears nowhere else under `Views/`. One
instance — but four hand-written answers to "what did the user right-click" is
the actual finding. **Ready to fix:** one shared
`contextMenuTargets(clicked:)` that all four call, so a fifth menu item cannot
invent a fifth answer.

### B2. Two ordered-list seams where the code says there is one — LATENT

`Views/Library/LibraryView+ArrowNavigation.swift:98-119` introduces
`keyboardNavigationIds` and documents it as "ONE seam, so the grammar can never
be handed a list that does not match what is rendered (#4377)". It correctly
special-cases the Table, whose disclosed child rows are not documents at all.

`handleTap` does not use it. `Views/Library/LibraryView+Selection.swift:94`
passes the older, narrower `keyboardNavigationDocuments.map(\.id)`.

Today this is harmless: Table does not route clicks through `handleTap` (see
below), so in every mode that *does* — icon, list, columns — the two seams
return the same array. It is a live trap rather than a live bug: the seam that
exists specifically to stop a mode being handed the wrong list is bypassed by
the click path, and the next mode that needs the wider vocabulary will
reintroduce exactly the #4377 defect on the mouse side. That is the shape #4377
already was — "the keyboard path had already grown a robust fallback chain; the
mouse path never got it" (`SelectionGrammar.swift:19-21`). **Ready to fix:** one
line, `handleTap` reads `keyboardNavigationIds`.

### B3. Icon mode writes the preview twice per click — INFERRED (mechanism read, timing not observed)

`Views/Library/LibraryView+Selection.swift:104-106` sets `detailDocument = doc`
directly on tap. The same click also mutates `selection`, which is bound to
ContentView's `browserSelection`, whose `onChange` handler
(`Views/Shell/ContentView/ContentView+StateEvents.swift:134-186`) resolves and
writes `detailDocument` *again* — this time through
`BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail` (`:161`), which
the direct write bypasses.

Two writers to one piece of state per click, one of them skipping the policy
that governs it. This is the same family as the duplicate-handler bug the code
lane fixed tonight (`327046854`), and a plausible remaining contributor to the
preview double-redraw. Worth a look while #4572/#4574 are still warm.

---

## Finder-grammar departures

### G1. Table rows and every other mode draw selection differently

List and columns use the app's own Mail-style grey fill —
`LibrarySelectableRow` with `LibrarySelectionStyle.fill` =
`.unemphasizedSelectedContentBackgroundColor`
(`Views/Library/LibraryViewComponents.swift:28-34, 101-104`), with the label
tint following focus (`:43-45`).

Table applies none of it. Its cells
(`Views/Library/ViewModes/LibraryView+TableColumns.swift:203-228`) carry no
`isSelected` or tint parameter at all; selection is whatever AppKit's native
`Table`/`NSTableView` draws. The only selection-aware line is an accessibility
trait (`:227`).

So switching view mode on the same folder changes the visual language of
selection. **This is a design question for you, and it has a right answer
either way** — either Table adopts the custom style, or list/columns drop
theirs and inherit native selection everywhere. My recommendation is the
latter: native selection is what Finder actually draws, it tracks focus and
accent colour for free, and it is the direction tonight's sidebar work already
took ("the native source-list platter IS Finder's grey", `bc36d39bd`).

### G2. Table's drop target is the Name column, not the row

`Views/Library/ViewModes/LibraryView+TableColumns.swift:203-217`. The comment is
explicit that this is deliberate — "Table scopes the dropDestination (and its
highlight) to this cell" — so this is a known constraint, not an oversight.

But it still departs: list and columns wrap the full row
(`LibraryView+ListView.swift:67-72`,
`Columns/LibraryView+ColumnsView.swift:154-157`), Finder accepts a row drop
anywhere along the row, and the sidebar was deliberately moved to a full-row
platter tonight (`be75fa424`). In Table, dragging a file over the Status or
Output column of a folder row does nothing, with no feedback explaining why.
**Design question:** accept the SwiftUI `Table` constraint, or take the drop to
a row-level overlay.

### G3. ⌘-click and ⇧-click do not exist on touch

`Views/Library/LibraryView+Selection.swift:70-80`: `currentSelectionModifiers`
reads `NSEvent.modifierFlags` on macOS and returns `[]` everywhere else. The
grammar then collapses to plain single selection on iOS/iPadOS. That is honest
rather than broken — there are no modifier keys on a touch — but it means iPad
currently has **no way to build a multi-selection in the library at all**
(no Edit-mode, no long-press-to-select found). Flagging because
multi-selection is the input to every batch workflow. **Design question**, and
probably a separate issue.

### G4. Columns mode carries two kinds of "selected"

`Columns/LibraryView+ColumnsView.swift:139-144`: a row is drawn selected when it
is genuinely selected in the active column, *or* when it is the path segment for
an inactive ancestor column — the latter tinted `.secondary` rather than
`selectionTint`. This is correct Miller-columns behaviour and matches Finder;
noting it because it is the one place where "looks selected" deliberately does
not mean "is in `selection`", and any future audit of selection appearance will
trip over it.

---

## Performance

Measured baseline for the session is 106 stalls / 32.6s / worst 1860ms
(`20b41220c`). I did not re-run the sampler — that requires a build, which is
the code lane's. These are read-from-source observations, so treat them as
candidates, not measurements.

### P1. Columns refetches every open column on any document change

`Columns/LibraryView+ColumnsView.swift:98-100` reloads all open columns'
children with `force: true` on *any* `documentStore.currentDocuments` change,
unscoped to the folder that actually changed. With several columns open and a
change stream that fires per import, this is a fan-out of GETs for data that did
not change. **INFERRED** as a hazard from the call shape; not profiled.

### P2. Table rebuilds its node tree every render and skips `.equatable()`

`Views/Library/ViewModes/LibraryView+TableView.swift:119-121` states
`outlineNodes` is rebuilt fresh each render. List and columns rows are wrapped
`.equatable()` (`LibraryView+ListView.swift:59`, `ColumnsView.swift:148`); the
Table's cells are not. `Table` virtualises, so the blast radius is bounded to
visible rows — but it is strictly more per-render work than the other modes do,
in the mode most likely to be showing a large expanded outline.

### P3. Per-row `.contextMenu` closures in list, columns and icon

`LibraryView+ListView.swift:80-82`, `ColumnsView.swift:160`,
`LibraryView+IconMode.swift:107-109`. Table uses the single container-level
`.contextMenu(forSelectionType:)` (`TableView.swift:26-35`), which is the
cheaper shape. The sidebar hit exactly this and fixed it with
`SidebarDeferredMenuContent` (`c3aef4501`, 506 Time-Profiler samples attributed
to context-menu construction). The same remedy is available here and the same
measurement already justifies it. **Ready to fix**, with the sidebar's pin test
as the model.

---

## What each mode does with a multi-selection

| | icon | list | table | columns |
|---|---|---|---|---|
| ⌘/⇧ build a set (macOS) | yes | yes | yes (native `NSTableView`) | yes |
| click routing | `handleTap` → `SelectionGrammar.click` | same | native `Table(selection:)` → `SelectionGrammar.reconcile` (`TableView.swift:221-254`) | `handleColumnTap` → `handleTap` (`ColumnsView.swift:260-273`) |
| preview with 2+ selected | first-resolved doc | same | `primaryNodeId` — deterministic (`TableView.swift:89-99`) | suppressed by design (`ColumnsView.swift:49-55`) |
| header sort | — | — | yes, shared state (`TableView.swift:360-376`) | — |
| column reorder/resize | — | — | yes (`TableColumns.swift:63-198`) | — |

Two things stand out. **Table is the only mode with header sorting**, though
sort *state* is shared — so the same folder is sortable by clicking in one mode
and only via the toolbar menu in the other three. Whether that is fine (it is
what Finder does) or a gap is your call. And **columns deliberately refuses to
preview a multi-selection** (`ColumnsView.swift:49-55`), which is correct Finder
parity and is the only mode that makes an explicit decision about it — the other
three fall through to "whichever document resolved first", which is the subject
of the companion review.

---

## The pattern worth naming: rules that cannot fire

Four separate times today the codebase was found to contain a rule that was
structurally incapable of failing. This is the most useful thing in either
review, because it is a habit rather than four accidents:

1. **`SelectionGrammar` forbids `Set.first` — in a comment.**
   `SelectionGrammar.swift:93-94` says "Never `selection.first` — that is `Set`
   hash order". Comments do not fail builds. Six violations accumulated
   underneath it (enumerated in the companion review).
2. **`check_environment_forwarding.py` printed "no new gaps" through three
   crashes** it existed to prevent, because its host list held one entry and
   none of the three failures were in it. Fixed tonight in `f9512ec80`; the
   fix's self-test now proves the check *fires*.
3. **A preflight check that always failed** and a **bookmark mint that could
   never throw** — the two the code lane hit earlier today.

The common form: the rule is written where it cannot be enforced (a comment, a
list that is never extended, a branch that is never reached). The remedy that
worked tonight is the one to generalise — **every guardrail ships with a
fixture that proves it fires on a real regression**, not merely that it passes
today. `check_environment_forwarding.py --self-test` is the working model.

For B1 specifically, that means: the fix is not only the shared
`contextMenuTargets(clicked:)`, it is a source-pin test that fails if a menu
item resolves its own targets again.

---

## Summary for triage

**Cheap and certain — hand to the code lane:**
- B1 right-click acts on unclicked rows (`LibraryView+ContextMenu.swift:394`) — plus the shared resolver and a pin test
- B2 `handleTap` reads `keyboardNavigationIds` (`LibraryView+Selection.swift:94`) — one line
- P3 deferred context-menu content in icon/list/columns — the sidebar's `SidebarDeferredMenuContent` is the template
- The stale icon-tile comment: your Finder screenshot ruling supersedes the older #4160 note; the comment needs updating to match what shipped

**Worth investigating next:**
- B3 double write to `detailDocument` per icon-mode click
- P1 columns' unscoped force-refetch
- P2 Table's per-render node rebuild

**Design questions only you can settle:**
- G1 one selection appearance across all four modes — native, or the custom grey? (I recommend native)
- G2 Table drop: accept the Name-column constraint, or overlay the row?
- G3 multi-selection on iPad — currently impossible; batch workflows depend on it
