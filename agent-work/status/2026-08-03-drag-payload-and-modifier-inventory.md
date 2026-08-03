# Library-item drags: every source, every target, every modifier

**Lane:** lane-crash2 · **Date:** 2026-08-03 · **Issues:** #4474, #4475
**Predecessor:** `2026-08-02-drop-path-table.md` (gaps A, B, C are this work)

The inventory came first, before any fix, because the fix is only correct if it
covers all of it. The previous review's table was right about what it listed and
**incomplete about how many sites vend `LibraryItemDrag`** — it named the four
library view modes; there are eight `.draggable` sites in total.

---

## 1. Drag SOURCES for a library item

| # | Site | Payload | First string rep (what an in-process reader gets) |
|---|---|---|---|
| S1 | `SidebarItemRow+Drop.swift:125` (nested child rows) | `SidebarDragID(item:)` | `doc:<uuid>` — `.ownProcess`, first since #4401 |
| S2 | `SidebarView+UnifiedRows.swift:204` (top-level rows) | `SidebarDragID(item:)` | `doc:<uuid>` |
| S3 | `LibraryView+ListView.swift:62` | `libraryItemDrag(for: doc)` | JSON |
| S4 | `LibraryView+IconMode.swift:88` | `libraryItemDrag(for: doc)` | JSON |
| S5 | `LibraryView+ColumnsView.swift:151` | `libraryItemDrag(for: doc)` | JSON |
| S6 | `LibraryView+TableColumns.swift:211,254` (document + page rows) | `libraryItemDrag(for:)` | JSON |
| S7 | `LibraryView+TableColumns.swift:241,262` (artifact/note rows) | `LibraryItemDrag(kind: .artifact/.note)` | JSON |
| S8 | `ArtifactListView.swift:164`, `AnnotationListView.swift:87`, `NoteListView.swift:111` | `LibraryItemDrag(kind:)` | JSON |

`SidebarDragID(document:libraryId:)` also exists and sets `id = "doc:\(id)"` —
used for grid Export…, not for a `.draggable`.

**Not this defect class** (different concepts, correctly different types):
`CitationDragID`, `InspectorEntityDragID`, `ActionDragData`, workflow-node JSON.

## 2. Drop TARGETS

| # | Site | API | Reads | Sidebar row (S1/S2) | Library item (S3–S6) | Modifiers |
|---|---|---|---|---|---|---|
| T1 | Sidebar row → folder (`handleRowDrop`) | untyped `.onDrop(dropTypes)` | shared classifier | **move** | **move** (fixed #4473 lane) | ⌥ copy, ⌘⌥ alias |
| T2 | Sidebar nested insertion line | typed `SidebarDragID` | typed | **move** | **no match** | ⌥ copy, ⌘⌥ alias |
| T3 | Sidebar root insertion line | typed `SidebarDragID` | typed | **move** | **no match** | ⌥ copy, ⌘⌥ alias |
| T4 | Library section header ("to root") | untyped | shared classifier | **move** | **move** | none — always moves |
| T5 | **Library folder cell** (list/icon/columns/table — all four via `LibraryFolderCellDrop`) | typed `LibraryItemDrag` | typed | **NOTHING** ← #4474 | move | **none** ← #4475 B |
| T6 | Content pane | `.onDrop([.item])` | external only | n/a | n/a | n/a |
| T7 | Chat / Chat inspector | `.onDrop([.text,.plainText])` | first string | attaches | attaches | n/a |

**The four bad pairings**, all of them at T5, and all of them one line of code
(`LibraryFolderCellDrop` is shared by every library view mode — so list, icons,
columns and table are four symptoms of one site, not four sites):

1. sidebar row → library folder cell = silently nothing (#4474)
2. ⌥ + library item → library folder cell = plain move, no copy (#4475 B)
3. ⌘⌥ + library item → library folder cell = plain move, no alias (#4475 B)
4. any failure at T5 = logged only, never surfaced to the user

## 3. Where modifier state is read (#4475 C)

| Site | When sampled |
|---|---|
| `handleDropIntoFolder` | once at drop entry, passed down as `SidebarDropModifiers` |
| `handleNonMoveInsertion` (nested line) | `.current()` inline, below the entry point |
| `handleExternalInsertionDrop` (root line) | `.current()` inline, below the entry point |
| `targetedDropOperation` (hover highlight) | `.current()` during hover — correct, this one *must* re-read |

Both drop paths agree today. Two places that happen to agree is the shape that
produced this family, so the rule is made explicit rather than left to luck.

---

## Decisions

**ONE payload concept.** Not one struct — one *resolved answer*. Both surfaces
ask the same function "what internal document ids does this drop carry?" and get
back `doc:`-prefixed ids, whichever pane vended the drag.

The sources are deliberately **not** changed. `LibraryItemDrag` keeps JSON first
and `SidebarDragID` keeps `doc:` first, because changing a drag source to satisfy
one destination is exactly how #4123 caused #4401 and how #4401's fix nearly
broke chat (T7 reads the first string). The unification is on the reading side,
where it is safe.

**ONE modifier grammar**, `sidebarDropOperation`, now also behind T5.

**Deliberately left different:**

- **T4 (library header) always moves.** "Move to root" is a single-target
  gesture with no insertion offset and no meaningful duplicate-to-root distinct
  from the ⌥ already available at T3's root insertion line. Left alone.
- **T2/T3 stay typed on `SidebarDragID`.** These are *insertion lines* — they
  need the offset that `.dropDestination(for:)` gives and `.onDrop` does not.
  A library item cannot be dropped at a sidebar insertion offset today, and
  widening them means losing the offset. Recorded as a real gap, not fixed here.
- **The move EXECUTOR stays split.** T1 routes moves by folder kind (document,
  search, workflow, chat folders each have their own contract); T5 only ever has
  document folders. The *grammar* is shared; the kind-routing is not, because
  the library pane has no cross-section drops to route.
- **T5 still refuses external files.** Converting it to the untyped API makes
  Finder drags reachable there for the first time. Importing into the hovered
  folder is plausible but is a new feature, not this defect; T5 returns false so
  the drop falls through to the content pane, which already imports. Behaviour
  is unchanged from today, now by decision instead of by type accident.
