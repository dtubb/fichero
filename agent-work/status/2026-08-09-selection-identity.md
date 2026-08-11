# Selection identity — one answer to "what is selected" (task 11)

Daniel's report: "the sidebar says page 7, the toolbar says 1, the inspector
shows another page", and right-click acting on a row that is not the one under
the cursor. Three surfaces disagreeing is one defect, not three.

## Mechanism

The library pane already has a rigorous selection identity. `LibraryView` owns
an ordered list plus `selectionAnchor` / `selectionCursor`, and resolves the one
row a command acts on through `orderedPrimarySelectionId`
(`LibraryView+ArrowNavigation.swift:148`) → `LibraryKeyboardCursor.index(…)`.
`SelectionGrammar` states the rule explicitly, twice:

> Never `selection.first` — that is `Set` hash order, which would make the same
> gesture produce different ranges on different runs.

`ContentView` holds the SAME selection set (`browserSelection` is the binding
`LibraryView` writes) but **not** the cursor — that is `@State` private to
`LibraryView`. So every ContentView-side surface falls back to exactly the
construction the grammar forbids:

| site | what it decides |
|---|---|
| `ContentView+StateEvents.swift:160` | which document is promoted to `detailDocument` — the PREVIEW pane |
| `ContentView+StatePreview.swift:52` | preview restored on appear |
| `ContentView+StatePreview.swift:150` | preview repopulated when the document list reloads |
| `ContentView+StateSelection.swift:31` | `inspectorDocument` — what the INSPECTOR shows |
| `ContentView+CompactReader.swift:53` | which leaf the compact READER opens |

Five independent `browserSelection.first` calls. With one row selected they all
agree and the bug is invisible. With two or more they are five independent draws
from `Set` hash order, and `String`'s hash is seeded per process — so the answer
differs between surfaces *and* between launches. That is precisely the reported
symptom, including why it looks intermittent.

This is one class with five instances, so it gets one fix, not five patches.

## Fix

`LibraryView` stays the OWNER of the cursor: it is the surface that knows its
ordered list, and that list differs per view mode (entities vs documents,
Miller-column children, Table outline rows). Moving 25 cursor/anchor usages up
into `ContentView` would relocate the knowledge away from the thing that has it.

Instead the library PUBLISHES its resolved answer, and everyone reads that:

1. `WindowState.primarySelectionId: String?` — one per window, alongside
   `preservedDocumentSelection`, which already exists for the same reason (a
   selection fact several surfaces must agree on).
2. `LibraryView` writes `orderedPrimarySelectionId` into it on every change of
   selection / cursor / anchor.
3. `ContentView` reads through ONE accessor that prefers the published id and
   falls back — when the library pane is not mounted, e.g. a sidebar-driven
   selection — to the topmost selected row in **document order**, never
   `Set.first`. Determinism at worst, agreement at best.

## Guardrail

`SelectionGrammar`'s rule is currently a comment, and comments do not fail
builds — five violations accumulated under it. A source-pin test forbidding
`browserSelection.first` / `selection.first` outside the resolver, with a fixture
proving it fires, is the part that stops the sixth.

## The same class, third surface: right-click target resolution

Daniel also reports right-click acting on the wrong row. The sidebar is fine —
`SidebarItemContextMenu` takes `let item: SidebarItem`, so it targets the
clicked row by construction. The library grid has the defect, and it is one
line:

```swift
// LibraryView+ContextMenu.swift:394 — excludeToggleTargets(for:)
let targetIds = selection.isEmpty ? [document.id] : Array(selection)
```

When the selection is non-empty and does NOT contain the clicked row, this acts
on the selection and ignores the row the user actually right-clicked. Finder's
rule is the opposite: a right-click outside the selection acts on the clicked
row.

The correct form already exists twice in the same file — `imageStackTargets`
(:403) guards with `selection.contains(document.id) && selection.count > 1`,
and `addToChatMenuItem` (:120) replaces the selection when the clicked row is
outside it. So three menu items, three hand-written answers to "what did the
user right-click", one of them wrong.

Swept for siblings: `selection.isEmpty ? [` appears nowhere else in `Views/`.
One instance, but the class is "each menu item resolves its own targets", and
the fix is one shared `contextMenuTargets(clicked:)` the three call — so a
fourth item cannot invent a fourth answer.

## Status

Diagnosed 2026-08-09 overnight. Implementation BLOCKED, not deferred: a second
agent (`sidebar@session-37c4b9a0`) is editing this same worktree concurrently —
`LibraryView.swift` and `OntologyBrowser+Sheets.swift` modified, untracked
`SheetLibraryEnvironment.swift`, and its in-flight `LibraryView.swift` fails to
compile, so no build result here can be trusted. Escalated to the lead; holding
at read-only rather than racing it.
