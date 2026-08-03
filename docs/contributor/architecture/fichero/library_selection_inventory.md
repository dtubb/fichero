# Selection across the library view modes — inventory (#4436)

An inventory of how every library view mode implements selection, taken BEFORE
any unification, so the fix that follows is reviewable against something rather
than against a claim.

The rulebook is `Models/Selection/SelectionGrammar.swift`. Its header states the
two rules that a second implementation never arrives at by accident:

1. **⌘-click moves the anchor even when the click DESELECTED the row** — Finder
   extends from where you last *acted*.
2. **⇧ holds the anchor still and moves only the cursor** — which is what lets
   ⇧↓ ⇧↓ ⇧↑ *shrink* a selection.

That doc is correct and is not restated here. What follows is the per-surface
audit of who obeys it.

## The surfaces

There are **six** surfaces that write selection, not four. Two of them are the
flag-off fallback renderers, which still ship and are still reachable.

| # | Mode | Entry point | File |
|---|------|-------------|------|
| 1 | List | `handleTap` | `ViewModes/LibraryView+ListView.swift` |
| 2 | Icon | `handleTap` / `handleEntityTap` | `ViewModes/LibraryView+IconMode.swift` |
| 3 | Table | native `Table(selection:)` | `ViewModes/LibraryView+TableView.swift` |
| 4 | Columns | `handleColumnTap` → `handleTap` | `ViewModes/Columns/LibraryView+ColumnsView.swift` |
| 5 | Canvas 2D / Space 3D (RealityKit) | `CanvasInteractionController` | `ViewModes/Canvas/Engine/CanvasInteractionController.swift` |
| 6 | Canvas 2D / Space 3D (legacy, flag-off) | raw binding writes | `ViewModes/Canvas/2D/Legacy/SpatialView.swift`, `ViewModes/Canvas/3D/SpaceSceneView.swift` |

## The table

`✅` = routed through `SelectionGrammar`. `⚠️` = implemented, but by hand.
`❌` = absent.

| Gesture | 1 List | 2 Icon | 3 Table | 4 Columns | 5 Canvas (RK) | 6 Canvas (legacy) |
|---|---|---|---|---|---|---|
| plain click | ✅ | ✅ | ⚠️ AppKit | ✅ | ✅ | ❌ raw `= [id]` |
| ⇧-click range | ✅ | ✅ | ⚠️ AppKit | ✅ | ❌ falls through to replace (#4460) | ❌ |
| ⌘-click toggle | ✅ | ✅ | ⚠️ AppKit | ✅ | ✅ | ❌ |
| marquee | n/a | n/a | n/a | n/a | ⚠️ wholesale replace | ⚠️ separate `@State` |
| ⌘A | ✅ shared `selectAll()` | ✅ | ✅ (outline ids) | ✅ | ❌ not wired | ❌ |
| click empty space | ✅ `apply(clear())` | ✅ `apply(clear())` | n/a | ⚠️ 3 hand assignments | ✅ `.tap(id: nil)` | ❌ |
| arrow / ⇧-arrow | ✅ shared | ✅ shared | ✅ shared | ⚠️ ←/→ hand-rolled | ❌ | ❌ |
| anchor | shared `selectionAnchor` | shared | **patched after the fact** | shared, but bypassed on ←/→ | **its own second anchor** | none |

**The table above is the BEFORE state and is kept as written.** Defects C and D
were fixed by #4436; what that fix did not reach is recorded in "What #4436 did
not reach" below.

## The specific defects the table encodes

**A. The canvas controller keeps a SECOND selection set and a SECOND anchor, and
never reads either back.**
`CanvasInteractionController.selectionSet` and `.selectionAnchor` are private
state. The controller writes `selection.wrappedValue` on every gesture but never
reads it. `LibraryView.canvasSelectedNodeIds` is a real two-way `Binding`, so the
read direction exists and is simply unused. Consequence: select three rows in
List, switch to Canvas, ⌘-click a fourth card — the controller starts from its
own stale `selectionSet` (often empty) and the three go away. Same for the
anchor: the library's `selectionAnchor` and the controller's are two variables
naming one concept.

**B. Marquee replaces wholesale and ignores modifiers.**
`selectMany(_:)` assigns `ids` and touches neither the anchor nor the existing
selection. In Finder a ⇧- or ⌘-marquee ADDS to the selection; here it discards
it. This is the remaining half of #4409 — the "publishes one of five" half was
already fixed, the "throws away what you had" half was not.

**C. The Table's anchor patch cannot express rule 1.**
`onChange(of: selection)` recomputes `primaryNodeId(in: newSelection)`, which
prefers the *existing* cursor when it is still selected. So a ⌘-click that
DESELECTS a row leaves the anchor where it was instead of moving it to the row
just acted on — rule 1, violated. Worse, the handler is `guard let … else {
return }`: when the selection becomes EMPTY it returns early, leaving
`selectionCursor` and `selectionAnchor` pointing at rows that are no longer
selected. The information needed to do this correctly is present and unused —
`onChange` receives the OLD selection, and the symmetric difference of old and
new is exactly the row the user acted on.

**D. Columns bypasses `apply()` in four places.**
Empty-space click writes `selection` / `selectionAnchor` / `selectionCursor` as
three separate statements. `handleColumnsArrowKey` writes all three again for →
and ←. And one branch — → into a folder whose children have not been fetched yet
— writes `selection = [doc.id]` and **leaves the anchor and cursor stale**. That
is precisely the drift the grammar exists to prevent, in the mode the issue names
as "missing modifiers".

**E. The legacy canvases have no selection grammar at all.**
`Spatial2DCanvas` (the flag-off 2D renderer) and `SpaceSceneView` (the flag-off
3D one) do `selectedNodeIds = [node.id]` at four call sites. No modifiers, no
anchor, no toggle. `Spatial2DCanvas` also keeps a `marqueeSelection` `@State`
that is OR-ed into the drawn `isSelected` — a seventh place that decides what
"selected" looks like.

## What is deliberately NOT uniform

- **Table delegates click / ⇧-click / ⌘-click to AppKit.** `NSTableView` already
  implements the same Finder rules, and replacing a native `Table(selection:)`
  with hand-rolled gestures would lose column drag-reorder, native
  keyboard-loop behaviour and accessibility. What the Table does NOT own is our
  `selectionAnchor` / `selectionCursor`, which the *shared arrow-key* path reads
  — so the fix is to make the patch obey rule 1, not to take the clicks back.
- **⇧ on a spatial canvas stays unrouted.** A canvas has no inherent order to
  extend along; picking one is a product decision, open as #4460. Documented at
  the call site already.
- **Columns' ← / → are genuinely column-scoped**, not row-scoped: they change
  which column is active, which changes the ordered list itself. They must still
  go through `apply()`, but they cannot go through `SelectionGrammar.click`.

## What #4436 did not reach (#4377)

#4436 unified which grammar CALL each surface makes. Both remaining defects were
one level down: the call was right and the **arguments** were wrong. That is why
they survived a fix explicitly about unifying selection, and why
`check_selection_grammar.py` was green the whole time — see "the guardrail's
bound" below.

**F. The Table handed the grammar a list of documents while rendering an
outline.**
`reconcile(…, in:)` and the shared arrow path both passed
`filteredDocuments.map(\.id)`. The Table is an OUTLINE: disclosed child rows
carry `"<doc>:artifact:<id>"` ids that are in no document list, and with the
No-date section showing, rows render dated-then-undated, which is not
`filteredDocuments` order either. Collapsed, the two lists coincide — which is
exactly why this looked correct. Expanded, selecting a child row and pressing ↓
resolved to no index at all, hit the "nothing is selected yet" branch, and threw
the user to the FIRST row of the library.

The sharp part: the correct list already existed.
`LibraryOutlineNode.visibleIds(of:expanded:)` was written for ⌘A in #4198, and
⌘A was the only selection path calling it. Three paths in one mode, one right
and two wrong. The inventory scored ⌘A "✅ (outline ids)" and arrows "✅ shared"
and called both correct, because it asked whether a path was SHARED and not
which LIST it shared. All three now go through `visibleOutlineRowIds`.

**G. Miller-columns changed the ordered list, then navigated, then delegated.**
`handleColumnTap` wrote `columnsPath` — descending into a folder or truncating
deeper columns — *unconditionally, one call before* `handleTap`'s guard that
refuses to drill in while ⇧ or ⌘ is held. So ⌘-clicking a folder to add it to a
selection also opened it, and ⇧-clicking a document closed every deeper column.
The guard was real; this path went around it. Opening and closing now happen
only on a plain click (`columnTapOpensOrClosesColumns`). Which column is ACTIVE
still follows a modified click, deliberately: a row renders its selection only
while its column is active, so freezing that would make ⌘-click look like a
no-op.

## The guardrail's bound

`check_selection_grammar.py` is a **delegation** check: it asks whether a
selection write is accompanied by the grammar's name. It cannot read arguments,
so it was green throughout F and G — both of which live in code it scores as
perfect. This is a real limit, not a regex bug, and the division of labour is
now explicit: the script stops a NEW mode from skipping the grammar;
`SelectionSurfaceParityTests` drives each surface through its real entry point
and is where "the grammar was handed the wrong list" gets caught.

One thing it CAN see was added: hand-constructing `SelectionGrammar.Result(…)`.
That shape names the grammar — so the delegation window scored it as compliant
— while being a private copy of whichever rule it spells out. Three call sites
used it to say "select exactly this one row"; `SelectionGrammar.select(_:)` says
it now, and the construction is forbidden with a fixture proving it fires.

## The fix this inventory justifies

One grammar, referenced from one place, plus a guardrail that a *fifth* mode
cannot skip: any file under `Views/Library/ViewModes/` that writes a selection
must do it through `SelectionGrammar` / `apply(…)`, and the check must have a
population floor so it cannot pass by matching nothing.
