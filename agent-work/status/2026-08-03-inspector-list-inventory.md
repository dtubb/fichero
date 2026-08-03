# Document inspector — List inventory

Daniel asked: *"did you properly review usage of swiftui lists in document inspector?
drag and drop. keyboard control. multiselect. ios and ipad and mac friendly."*

**The honest answer was no.** Last night covered the LIBRARY view modes and the
inspector's attribute chooser and claims *display*. Nobody had checked the inspector's
own Lists. This is that check, against the code in the worktree, before any fix.

Scope: `fichero/fichero/Views/Inspector/**` — 86 files, 84 list-like constructs, of which
**11 are real `List`s** and the rest are `ForEach` inside a stack. That distinction is the
single most load-bearing fact in this document: a `ForEach` in a `ScrollView` gets no
free keyboard navigation, no free multi-select, no swipe actions, and no selection at all.

---

## The headline

| Question | Answer |
|---|---|
| Do inspector lists use the shared drag grammar (#4474/#4475)? | **Two do. Nine do not, and two invented their own payload types.** |
| Do inspector lists use `SelectionGrammar` (#4436)? | **None do.** The one helper that calls it has **zero production callers** — only tests. |
| Multi-select? | 4 of 11 real Lists. The other 7 are single-selection or selectionless. |
| Reorder (`.onMove`)? | **None anywhere.** No inspector list is user-orderable. |
| `.swipeActions` / `EditButton` — the iOS/iPad idioms? | **Zero occurrences in the entire inspector tree.** |
| Keyboard: arrows / ⇧-arrow / ⌘A / Return / Escape? | Arrows come free from `List`. **⇧-arrow range, ⌘A, Return-to-act and Escape are implemented nowhere.** |
| iPad tab switching? | **Pointer/touch only** — `SurfaceTabBar` buttons carry no `.keyboardShortcut`. |

---

## The 11 real `List`s

| # | List | Sel | Drag | Keyboard | Multi | iPad |
|---|---|---|---|---|---|---|
| 1 | `Knowledge/Citations/CitationListView.swift:36` citations | `String?` | `.draggable(CitationDragID)` — **own payload** | none | no | contextMenu only |
| 2 | `Knowledge/Entities/DocumentInspectorEntitiesTab.swift:91` entities | `Set<String>` | `.draggable(InspectorEntityDragID)` + `.dropDestination` — **own payload** | `.onExitCommand` (rename only, macOS) | **yes** | double-click to open; contextMenu fallback |
| 3 | `…EntitiesTab+Rows.swift:102` fallback list | `Set<String>` | same | same | yes | same |
| 4 | `Knowledge/EntityDigestView.swift:91` entity index | `Set<String>` | none | `.onDeleteCommand` **macOS-only** | **yes** | **no delete affordance on iPad** |
| 5 | `Knowledge/EntityDigestView.swift:328` claims by document | `String?` | none | none | no | selection alone drives navigation |
| 6 | `Knowledge/KnowledgeGraph/…+Views.swift:82` KG claims | `Set<String>` | none | `.onKeyPress(.space)` → source peek | **yes** | double-click to open source |
| 7 | `Artifacts/ArtifactListView.swift:61` artifacts | `Set<String>` | `.draggable(LibraryItemDrag)` ✅ **shared** | `.onDeleteCommand` **macOS-only** | **yes** | **no delete affordance on iPad** |
| 8 | `Notes/Annotations/AnnotationListView.swift:50` annotations | `String?` | `.draggable(LibraryItemDrag)` ✅ **shared** | **nothing** | no | **no delete at all from the list** |
| 9 | `Source/DocumentInspectorMetadataTab.swift:10` metadata | `String?` | none | none | no | — **BROKEN, see D1** |
| 10 | `Source/SourceOutlineView.swift:141` outline tree | `String?` | none | free arrows only | no | selection fires navigation on every arrow keystroke |
| 11 | `Document/DocumentInspectorRelatedTab.swift:59` related docs | `String?` | none | free arrows only | no (deliberate, documented `:28-30`) | double-click; contextMenu fallback ✅ |

## The 19 pseudo-lists worth naming

`ForEach` in a stack — no selection, no keyboard, no drag, by construction:

- `Source/Info/…+Citations.swift:69` — **no action of any kind**
- `Source/Info/…+RelatedClaims.swift:53` — **no action**; a related claim is shown and cannot be opened
- `Source/Info/…+Bibliography.swift:146` — actions are **context-menu-only** (Edit/Resolve/Delete), undiscoverable and unreachable without right-click/long-press
- `Source/Info/…+Workflow.swift:47` — proper `Button`, disabled with a reason ✅ the best row in the inspector
- `DisplayAttributesStrip.swift:71` — inert text, no copy, no menu
- `Notes/DocumentInterpretationsSection.swift:92` — `LazyVStack`; header expand/collapse is a bare `.onTapGesture` on a non-Button
- `Notes/NoteDetailView.swift:252` — **backlinks are inert**, see D2
- `Knowledge/KGCurationHistorySection.swift:34` — per-row Undo `Button` ✅
- `Knowledge/EntityKindBlock.swift:101` — `LazyVStack`; **referenced only from previews**, no production caller

---

## Defects — clearly wrong, no design decision needed

### D1. The metadata tab is a `List` inside a `ScrollView` — the exact bug its neighbour documents

`Source/SourceSectionView.swift:49` wraps its children in a `ScrollView`. One of those
children, `DocumentInspectorMetadataTab.swift:10`, is a `List(selection:)`.

A SwiftUI `List` collapses to zero height inside a `ScrollView`. This is not a guess —
the sibling file's own doc comment says so, names it #2107, and explains that
`DocumentInspectorInfoTab` was rewritten to plain stacks *for this reason*
(`DocumentInspectorInfoTab.swift:28-35`). The metadata tab never got that treatment.

So Source → Info shows the Info block and then, most likely, nothing where the metadata
should be. **Fixed** in the follow-up commit.

### D2. A linked note is displayed and cannot be opened

`Notes/NoteDetailView.swift:252` renders backlinks and forward-links as an
`HStack { Image; Text }`. No `Button`, no `.onTapGesture`, no `.contextMenu`. The link is
visible and inert — #4421's "affordance that does nothing", in the surface Daniel uses to
follow his own cross-references. **Fixed.**

### D3. The inspector's only use of `SelectionGrammar` is dead code

`Knowledge/Entities/…+SupportTypes.swift:52-67` — `InspectorEntityBulkSelection.reduceTap`
delegates correctly to `SelectionGrammar.click`, including the two anchor rules. Its
callers are `SelectionGrammarTests.swift:371` and four in
`KnowledgeGraphInspectorSectionTests.swift`. **There are no others.**

The entities list gets its selection from the native `List(selection:)` binding, which
implements neither anchor rule. So the app has a tested, correct implementation of the
grammar wired to nothing, and a live surface that does not use it. That is the same shape
as #4415's curation guard: real code, real tests, wrong caller — and it is exactly why an
inventory comes before a fix.

**Not fixed here** — see Q1, because what ⇧-arrow should extend *along* in a
sectioned-by-kind list is a design question, not a bug.

---

## What needs Daniel's decision — three sharp questions

**Q1. Should inspector lists get the full Mac selection grammar, or is native `List` enough?**
Native `List(selection:)` gives arrows and ⇧-click. It does *not* give ⌘A, ⇧-arrow range,
or the two anchor rules that make multi-select feel right rather than nearly right. Wiring
`SelectionGrammar` in means deciding what ⇧ extends *along* in a list grouped into sections
by entity kind — across sections, or within one? The grammar's own doc says a surface with
no inherent order must decide that first. **I did not guess.**

**Q2. iPad: should inspector rows get `.swipeActions`, or stay context-menu-only?**
There is not one `.swipeActions` or `EditButton` in the whole inspector. On iPad, delete
is reachable for artifacts and entities only by long-press, and for annotations not at all.
Adding swipe actions is the native idiom — but it changes the Mac surface too unless
`#if os(iOS)`-gated, and this codebase's rule is feature-first, not OS-first. **Which way?**

**Q3. Should the inspector differ from the library on multi-select, and where?**
`DocumentInspectorRelatedTab` documents its single-selection as deliberate — *"multi-select
would be an affordance for nothing"* — and I think that is right. But annotations and
citations are single-selection with no such reasoning recorded, and a user who just learned
⌘-click in the library will try it there. **Deliberate, or drift?**

---

## Where the inspector SHOULD differ from the library

Recorded so a later uniformity sweep does not "fix" them into bugs:

- **`DocumentInspectorRelatedTab` stays single-selection.** Its rows navigate; there is no
  batch action for them to feed. Documented at `:28-30`, and correct.
- **`SourceOutlineView` selection fires navigation.** An outline exists to move the reader;
  select-equals-navigate is the point. But note it fires on *every arrow keystroke*, which
  the Related tab deliberately avoided by splitting select from open — see Q3.
- **No reorder anywhere is correct.** Every inspector list shows a *derived* order
  (newest-first, by run, by kind, sorted keys). There is no user order to persist, so
  `.onMove` would be a lie about what the list is.

---

## What remains unverifiable on iPad

Every platform claim in this document is read off the source. **None of it has been run on
iPad, and none of it can be**, because `fichero-ipad.xctestplan` names `FicheroTests`,
which does not support iPad (#4472) — both test targets are macOS-only in all 8
configurations. Specifically unverifiable until that target exists:

1. Whether `List` row heights meet the 44pt touch target on iPad.
2. Whether long-press context menus are actually reachable on every row that has one.
3. Whether the three double-click actions have any touch path at all
   (`ArtifactListView:173`, `…EntitiesTab+Rows:227`, `EntityKindRow+ClaimBlock:105`).
4. Whether the compact-width inspector presentation (`InspectorPresenter:48-70`, sheet vs
   push) actually renders the section bar and facet picker usably — `DocumentInspector`
   reads no `horizontalSizeClass`, so only the *container* adapts, not the contents.
5. Whether `.onDeleteCommand`-only delete leaves iPad users with no delete path — read of
   the source says yes, for artifacts and the entity index.

Items 3 and 5 are the ones I would bet are actually broken.
