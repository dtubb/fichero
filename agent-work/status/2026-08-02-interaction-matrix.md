# The interaction matrix (#4464)

*"Drag and drop everywhere. VoiceOver everywhere. Arrow keys everywhere. Menus. We don't have duplicate code paths."*

Read from the code — every cell is a declaration someone wrote, not a description someone believed. **Map only; nothing implemented.**

Legend: **N** native (the container provides it) · **H** hand-rolled · **—** absent · **n/a** absent and correct

---

## The matrix

| surface | container | arrows | multi-select | context menu | drag out | drop in | VoiceOver | ⌘ |
|---|---|---|---|---|---|---|---|---|
| **Sidebar** | `List(selection:)` | **N** +1 H | **N** `Set` | ✓ ×3 sites | ✓ | ✓ ×5 sites | ✓ rows | ✓ |
| **Library list** | ScrollView+VStack | **H** | **H** | ✓ | ✓ | ✓ | ✓ rows | via menus |
| **Library icons** | ScrollView+Grid | **H** *(dup)* | **H** | ✓ ×3 | ✓ | ✓ | **—** tiles | via menus |
| **Library table** | `Table(selection:)` | **N** + **H** | **N** `Set` | ✓ typed API | ✓ ×5 | ✓ | ~ partial | via menus |
| **Library columns** | ScrollView+VStack | **H** *(3rd impl)* | **H** *(raw)* | ✓ | ✓ | ✓ | ✓ rows | via menus |
| **Library canvas** | `RealityView` | **n/a** | **H** *(own model)* | **—** | n/a internal | n/a internal | **—** nodes | ⌫/⌘A only |
| **Shell / toolbar** | — | **H** window-level | n/a | **—** | n/a | ✓ ×2 APIs | ✓ | ✓ *(dup)* |
| **Inspector: Related** | `List(selection:)` | **N** | — single *(correct)* | ✓ 1 item | — | — | **—** rows | — |
| **Inspector: Entities** | `List(selection:)` | **N** | **N** `Set` | ✓ selection-aware | ✓ | ✓ | **—** rows | — |
| **Inspector: Annotations** | `List(selection:)` | **N** | — single | ✓ | ✓ | — | **—** rows | — |
| **Inspector: Artifacts** | `List(selection:)` | **N** | **N** `Set` | ✓ selection-aware | ✓ | — | **—** rows | ⌫ |
| **Inspector: Citations** | `List(selection:)` | **N** | — single | ✓ | ✓ | ✓ pane | **—** rows | — |
| *Inspector: Bibliography* | `LazyVStack` | **—** | **—** | ✓ | — | — | ✓ | — |
| **Reader** | ScrollView+NSTextView | **—** | text only | ✓ toolbar only | **—** | **—** | ✓ chrome, — content | esc only |
| **Workflow: node canvas** | `ZStack`+`.position` | **—** | **H** *(broken)* | ✓ | raw gestures | ✓ `.plainText` | **—** nodes | — |
| **Workflow: library** | `List`/`Table` | **N** ×3 | **N** `Set` | ✓ **typed API** | — | — | ✓ toolbar | — |
| **Chat: transcript** | ScrollView+VStack | **—** | **—** | **—** | **—** | ✓ | **—** messages | ⏎ |
| **Chat: side panes** | `List(selection:)` | **N** | **N** `Set` | ✓ | — | — | ✓ chrome | ⌘A *(dup)* |
| **Settings** | `List(selection:)` ×4 | **N** | — single *(correct)* | **—** all of Settings | n/a | n/a | ✓ controls | sheets |
| **Ontology: entities** | `List(selection:)` | **N** | — single | ✓ | **—** | **—** | **—** rows | ✓ *(dup)* |
| **Ontology: claims** | `List(selection:)` | **N** | **N** `Set` | ✓ ignores selection | **—** | **—** | **—** | ⌫ |
| **Ontology: graph** | `Canvas` | **—** | single | **—** | **—** | **—** | **—** nodes | — |

---

## 1. The matrix has one explanatory variable: **container choice**

Every surface built on `List`/`Table` has arrows, multi-select and selection-aware menus **for free and correct**. Every surface built on `ScrollView`+`LazyVStack`, `ZStack`, `Canvas` or `RealityView` either hand-rolls them or does without.

That is the whole answer to *"we don't have duplicate code paths."* **The duplication is not carelessness — it is the downstream cost of nine container decisions.** Nobody chose to write arrow keys three times; three surfaces chose a container that gives nothing, and then each needed arrows.

And the original container decision was deliberate and defensible. `LibraryView+ListView.swift:5` says the `ScrollView` exists *because* `List` would eat the arrow keys before `.onKeyPress` could see them. That was true. But it bought custom arrows at the price of custom selection, custom deselect, custom type-ahead and custom modifier reading — and then the same trade repeated in icons and columns.

**Good news: the mostly-filled verdict holds.** 14 of 22 surfaces are on a native container. Daniel's ask is largely a *verification* problem — except for the specific cells in §4.

## 2. Where one interaction is implemented more than once

Ranked by risk, not count.

| # | interaction | implementations |
|---|---|---|
| 1 | **Arrow keys** | shared set (`LibraryView+KeyboardShortcuts.swift:85`), a **verbatim duplicate** in icon mode (`LibraryView+IconMode.swift:141`, whose own comment says *"these deliberately DUPLICATE the body-level handlers… keep the two in sync"*), a third ←/→ fork for columns (`ColumnsView.swift:229`), **plus** the native `Table` — which has the hand-rolled set layered on top of it anyway |
| 2 | **Selection model** | four: sidebar native `Set<SidebarDestination>`; library `Set<String>` via `SelectionGrammar`; `Table` writing that same set natively and back-filling cursor/anchor in `.onChange`; canvas `CanvasInteractionController` with its **own anchor** |
| 3 | **Modifier-flag reading** | three `NSEvent.modifierFlags` translators — `LibraryView+Selection.swift:70`, `ArrowNavigation.swift:182`, `CanvasInteractionController.swift:188` (whose comment admits it mirrors the first) |
| 4 | **Click-empty-space-to-deselect** | three: `SelectionGrammar.clear()` in list and icons; **raw triple-assignment** in columns (`ColumnsView.swift:163`); a controller dispatch in canvas |
| 5 | **"Menu acts on the selection"** | re-derived by hand in four inspector lists, versus the one place using the native `contextMenu(forSelectionType:)` — `WorkflowChainListViewParts/ChainListContent.swift:51` |
| 6 | **Double-click to open** | four spellings across inspector lists: `.onTapGesture(count: 2)`, `.simultaneousGesture(TapGesture(count: 2))`, single-tap open, and native `primaryAction:` |
| 7 | **Marquee** | two independent implementations (current canvas + legacy `SpatialView`) |
| 8 | **⌘ chords declared twice** | ⌘' / ⌘⇧' in both the toolbar and the menu bar; ⌥⌘F likewise; ⌘A in `ChatInspector+Header.swift:19` alongside the app-level select-all |

**Dead second implementation:** `InspectorEntityBulkSelection.reduceTap` (`DocumentInspectorEntitiesTab+SupportTypes.swift:57`) is a complete hand-rolled shift/⌘ grammar **with no production caller** — kept alive only by tests. A tested, maintained, unreachable copy of `SelectionGrammar`.

## 3. Absences that are CORRECT — do not "fix" these

- **Related tab, Annotations, Citations: single selection.** No operation there takes multiple items. Multi-select would be an affordance for nothing. (`Citations` binds `$focused.id` because it drives a *detached window* — that is a detail driver, not a selection model.)
- **Settings: no multi-select, no context menus, no drag.** You configure one thing at a time. Zero `.contextMenu` in all of `Views/Settings/` is a coherent decision, not an oversight.
- **Canvas: no arrow keys.** Explicitly excluded at `LibraryView+KeyboardShortcuts.swift:30` — "up" has no meaning on a free 2D layout.
- **Reader: no multi-select, no drag.** It is a reading surface; text selection is the selection.
- **Chat transcript: no drag out.** Messages are not objects you file.

## 4. The cells whose absence he would feel — recommended

**① VoiceOver on library icon tiles and canvas nodes — the only true zeroes.**
Every other library mode labels its rows. Icon mode labels **nothing** on the tile; canvas labels **nothing** on the node. Icon mode is plausibly the default browsing view, so this is the app's most-used surface being silent. The app-wide scanner reports zero violations because it only checks *icon-only Buttons* — tiles are not buttons, so this gap is **invisible to the guardrail that was supposed to find it**. That is worth knowing on its own.
→ *Recommend: label icon tiles. Canvas nodes are RealityView entities and are a genuinely harder problem — file separately, do not bundle.*

**② The workflow node canvas's multi-select is broken, not missing.**
`selectedNodeIds` is a `Set`, and every tap **replaces** it (`+NodesLayer.swift:63`). No modifier is ever read. So the set can only ever hold one item from user gesture — while `.onDeleteCommand` deletes "the selection", and the type promises more. A user who shift-clicks three nodes and presses ⌫ loses one.
→ *Recommend: this is the highest-value single fix in the matrix. It is a bug wearing a feature's clothes.*

**③ Reader has no context menu on page content.**
The only menu is on the toolbar strip. Right-clicking a passage — the single most natural gesture in a document reader — does nothing.
→ *Recommend: worth one issue; it is the largest "nothing happens" in a primary surface.*

## 5. What this says about the ask

The matrix is **mostly filled**, so #4464 is primarily a verification programme — the click-list covers most of it. But three things are worth doing as work rather than checking:

1. the two VoiceOver zeroes (icon tiles, canvas nodes),
2. the workflow canvas's broken multi-select,
3. the arrow-key triplication — which is the only duplication that has *already* required a comment begging future editors to keep two copies in sync. That comment is the failure mode arriving in advance.

Everything else in §2 is real duplication but currently benign: the copies agree today. They are worth recording — this document — rather than sweeping, because each one is downstream of a container decision that would have to be revisited to remove it.
