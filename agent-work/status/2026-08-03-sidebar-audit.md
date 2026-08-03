# Sidebar QA audit — #116

Audited against the code on `origin/integration` at `1a72c880a`. 42 files, 8,830
lines. Inventory first, before any fix, because the assumed state has been wrong
every time today — including in the brief for this task.

---

## Already fixed — verify and close, do not re-report

The brief said #4453 and #4454 were "closed today". **Both are still OPEN on
GitHub, and both are fixed in the code.** That is the verify-and-close shape.

| Issue | Code state | Evidence |
|---|---|---|
| **#4453** deleting the selected row crashes on relaunch | **FIXED** | `ContentView+Persistence.swift:162-183` carries an explicit `#4453` guard: a restored selection that matches the stale `viewMode` fallback is dropped rather than assigned. The `??` resurrection path the issue describes is gone. |
| **#4454** delete on a structural row confirms and does nothing | **FIXED** | `SidebarItemContextMenu.swift:193` — `.folder` is excluded from `canBeDeleted`, with the reasoning recorded in place. |
| #4474 / #4475 drag payload + modifier grammar | FIXED, closed | `6c1519367` |
| #4461 document surfaces reaching for globalLibrary | FIXED, closed | `d45b040e7` |

---

## The inventory

### Structure

**There are no sections.** The sidebar is one `List` of per-library
`DisclosureGroup`s over a flattened node list; section headers were retired.
Ordering inside a library is **hardcoded** in
`SidebarView+UnifiedLibrarySections.swift:166-201` — documents, schedules,
triggers, savedSearches, comparisons, workflows — each behind a `FeatureManager`
gate. Libraries render in raw `openLibraries` array order, so the Global library
is not pinned first.

**Dead UI:** `Modes/SidebarModeBar.swift` and `Modes/SidebarModeIcon.swift`,
299 lines, have no production call site (only the former's own `#Preview`).

### Disclosure state — persists, and grows without bound

| State | Key | Persists | Default |
|---|---|---|---|
| library rows | `sidebar.libraries.<windowId>` | yes | expanded |
| folder/doc rows | `sidebar.expanded.<windowId>` | yes | collapsed |

`windowId` is a `@SceneStorage` UUID minted per window. So `EngineConfig.defaults`
accumulates **two keys per window-scene ever created**, and nothing purges dead
scene ids (there is a purge, but only for one retired key name). Unbounded
growth in user defaults. Low severity, definite leak.

`expandedItems` is a **single flat set across all libraries** — ids are
namespaced by kind (`doc:`, `structure:`) but not by library. Two libraries
holding the same engine id would share expansion state. Whether the engine can
produce a collision is AMBIGUOUS from the Swift side.

### Selection — and the biggest divergence found

Selection is `Set<SidebarDestination>`, native multi-select, with a two-value
model (highlight set + routed primary) and a resilience layer for tree rebuilds
(#4297). Escape collapses to the primary.

**`SelectionGrammar` (#4436) has ZERO uses in the sidebar.** The type is used by
five library surfaces and the inspector entities tab — everywhere except here.
The sidebar hand-rolls its primary derivation, its collapse, and a plain-click
path that re-reads `NSEvent.modifierFlags` itself
(`SidebarItemRow+Presentation+Body.swift:85-102`) rather than calling
`SelectionGrammar.click`. There is no anchor concept, so the two anchor rules
that the grammar exists to hold — ⌘-click moves the anchor even when it
deselects; ⇧ holds the anchor and moves only the cursor — are absent.

In practice AppKit's `List(selection: Set)` supplies ⇧-range and ⌘-toggle, so
this is not visibly broken today. It is the same shape as the inspector finding:
a tested, correct implementation that one surface does not use.

### Row types — 8 of 13 are selectable and inert

Every tree row is `.tag`-ged, so every row highlights on click. Of 13 kinds,
**eight route nowhere**: PDF structure nodes, virtual folders (search /
automation / regular), chains, schedules, triggers, batches, and library headers
land in a `log only, no-op` branch (`SidebarView+SelectionHandling.swift:200-277`).
Clicking paints a selection and the detail pane does not change.

Activity rows no longer render at all (`activityItems` is hardcoded `[]`), yet
the `.run` destination and its lookup remain live.

### Context menus — one real defect

Tree rows all get the same menu regardless of kind. Findings:

1. **Rename is offered on structural and virtual rows and silently does
   nothing.** `canBeRenamed` includes `.folder`
   (`SidebarItemContextMenu.swift:174`); committing the rename falls through to
   `default:` in `SidebarItemRow+Rename.swift:115-117`, logs "Unknown item type
   for rename", and returns. **This is the exact defect #4454 fixed for Delete,
   in the same file, left unfixed for Rename.** Fixed below.
2. **Right-clicking the Global library header opens an empty menu.** Every item
   is inside `if !isGlobal` (`SidebarView+LibraryHeaderHelpers.swift:204`).
3. **Open in New Tab / New Window on non-document rows** opens the library, not
   the item — the code says so itself (`SidebarItemRow.swift:580-596`).
4. Run Workflow appears on every row kind but resolves to a disabled "Nothing to
   run on" — honest, and correct after #4419.

### Empty states — there are none

Not one `ContentUnavailableView` or "No …" string in 42 files. An empty bucket
renders nothing, stated as intent. Filtering to zero matches gives a blank list
with no "No results". An expanded empty library shows a disclosure group with
`(0)`.

### Multiple libraries

Caches are keyed by library UUID and pruned on close. Two are not:
`libraryExpansionStates` (persists forever, by design) and
**`historicalRunsByLibrary`, which is never pruned when a library closes** — the
close handler rebuilds the other caches and leaves this one.

`cachedItemIndex` is first-in-DFS-preorder-wins, and forest ids are explicitly
not unique (a workflow mirror shares a document's id), so a duplicate resolves
to whichever library sorts first.

### Storage-filename leaks — the sidebar is the one document surface not using `DocumentTitle`

`grep DocumentTitle fichero/fichero/Views/Sidebar/` → **0 hits**, against 30 call
sites elsewhere. Seven sites compose names by hand:

| Site | Code |
|---|---|
| `Models/SidebarItem.swift:194` | `name: doc.pageThumbnailLabel ?? doc.name` — the #4416 defect verbatim |
| `SidebarItemRow+Presentation.swift:226` | `"\(doc.name) alias"` — leaks a storage name **into the database** |
| `SidebarView+SelectionHandling.swift:106,124` | raw `doc.name` in a user-facing alert |
| `SidebarItemRow+Presentation+Body.swift:107` | VoiceOver label built from the leaked `item.name` |
| `SidebarItemRow+Label.swift:37,281`, `SidebarItemRow.swift:527` | downstream of `SidebarItem.name` |

Fixing `SidebarItem.swift:194` fixes the label, the VoiceOver label and the help
text at once. The alias and alert sites are separate.

### Empty-closure class (#4505)

No instance inside a `Button` body. But
`SidebarActions.swift:143-153` — `handleOpenSelectionInNewTab` /
`handleOpenSelectionInNewWindow` — have bodies that are **entirely**
`#if os(macOS)`, and both are published as focused values. Any menu or key
binding reaching them on iOS is a live, enabled, silent no-op. One indirection
removed from the #4505 shape.

---

## Fixed in the follow-up commit

1. **`SidebarItem.swift:194` → `DocumentTitle`.** The sidebar was the last
   document surface composing names by hand, which is why #4416 kept finding new
   leaks: each sweep fixed the surfaces that used the composer and could not see
   this one.
2. **Rename disabled on virtual/structural rows**, matching what #4454 did for
   Delete in the same file.

## Needs Daniel's decision — joins the three inspector questions

**Q4. Should the sidebar adopt `SelectionGrammar`?** AppKit currently supplies
⇧-range and ⌘-toggle for free, so nothing is visibly broken. Adopting it means
deciding what ⇧ extends *along* in a tree — visual DFS order across libraries, or
within one library only? The grammar's own doc says a surface with no inherent
order must decide that first. Not guessed.

**Q5. Should eight inert row kinds be selectable at all?** Clicking a chain, a
schedule, a structure node or a library header paints a selection and changes
nothing. Two defensible answers: make them non-selectable, or give them a detail
view. Both are product decisions.

**Q6. Should the sidebar have empty states?** It has none anywhere, deliberately
("empty arrays render nothing"). That is defensible for a tree, but "no results"
after a filter is a different case — the user typed something and got silence.

---

## Not fixed, reported

- `historicalRunsByLibrary` never pruned on library close.
- Per-scene `sidebar.expanded.<uuid>` keys accumulate forever in user defaults.
- Global library header's context menu is empty.
- `Modes/SidebarModeBar.swift` + `SidebarModeIcon.swift`: 299 lines, no callers.
- `handleOpenSelectionInNewTab/Window` are empty functions on iOS but still
  published as focused values.
- Alias creation writes a raw `doc.name` into the engine.
