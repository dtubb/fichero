(AI generated. Not reviewed.)

# AppKit Interop — "Mac-assed" Behavioral Fidelity

**Status:** Adopted 2026-06-08 (Daniel directive)
**Extends:** `swiftui-principles.md` §8 ("Avoid AppKit Unless Absolutely Necessary")
**Goal of record:** Fichero should be a *Mac-assed app* — native controls, system conventions,
keyboard-first, impeccable OS integration — while staying SwiftUI-first.

---

## The decision

We keep **SwiftUI-first**. We are now widening the *sanctioned reasons* to drop to AppKit from
one to **two**:

1. **Capability gap** (existing) — SwiftUI literally cannot do the thing. PDFKit, image
   magnifier / scroll-wheel zoom, Quick Look, rich/plain-text editing, trackpad swipe. ~8 bridges.
2. **Behavioral-fidelity gap** (NEW) — SwiftUI *can* render it, but cannot match a decades-old
   Mac interaction that a power user *feels* the absence of. These are the cases Pfandrade
   documents ([mac-assed-swiftui-app](https://pfandrade.me/blog/mac-assed-swiftui-app/)).

Both reasons carry the **same containment discipline**: isolate behind an
`NSViewRepresentable` / `NSViewControllerRepresentable` bridge, documented here, never AppKit
sprinkled through view code. A bridge is a deliberate, tested seam — not a vibe.

**Iterate, never replace.** A fidelity bridge *folds into* the existing list/inspector/reading
stack. We do not stand up a parallel AppKit inspector beside the SwiftUI one. If `List` already
gives the behavior, use `List`; only bridge the specific control that `List` can't express.

## The fidelity gaps we care about (priority order)

| Gap | Why it matters on Mac | SwiftUI status | AppKit answer |
|---|---|---|---|
| **Selection emphasis on focus loss** | Tells the user which pane keyboard input drives | `List` gets it free; custom `LazyVStack` does not | `\.appearsActive` + `\.isEmphasized` env, or `NSTableRowView.isEmphasized` |
| **Context-menu target focus ring** | Menu acts on the *right-clicked* row, not the selected one | Impossible outside `List` — no API to know a context menu is open | `NSTableView` row highlight |
| **Drag-session visibility** | Dim/remove the dragged row; recover if dropped outside the window | Source has no session visibility; row can get stuck dimmed | `NSDraggingSource` callbacks |
| **Type-in-search + arrow-through-results** | Spotlight-standard: keep typing while ↑/↓ move the result selection | `TextField` swallows arrow keys | `NSEvent` monitor / `NSSearchField` bridge |
| **Toolbar placement precision** (3-pane) | Muscle memory for where actions live per pane | `.primaryAction`/`.secondaryAction` are unpredictable across the split | Explicit `NSToolbar` where precision is required |

## First adoption: the document inspector + reading-surface list

The reading-surface document list and the tabbed inspector are where these gaps bite hardest
(selection, context-menu target, drag). They are the **first** place we apply the fidelity bridge,
because that's the surface Daniel lives in. Scope each bridge to the single failing behavior.

## Guardrails (unchanged, restated)

- Engine **may be remote** — the inspector renders from HTTP payloads, never local file paths.
- Swift stays a **pure UI layer**: a fidelity bridge changes *presentation/interaction*, never
  business logic. No data ownership migrates into AppKit.
- New `.swift` files must be registered with `ruby scripts/add-swift-file.rb`.
- Before each new bridge: check Sosumi/Ref for a real SwiftUI API first; only bridge a *confirmed*
  gap; add it to the table in `swiftui-principles.md` §8 once it ships.
- Swift 6 concurrency rules apply inside the bridge (`@MainActor`, no `DispatchQueue.main`).

## What this is NOT

- Not a rewrite to AppKit. Not Catalyst. Not a license to bridge anything that's mildly annoying.
- Not an excuse to skip `List` where `List` already does the job.

Tracking: see the "Mac-assed app" EPIC and its children in GitHub Issues.

---

## Addendum 2026-06-08 — SwiftUI 2026 raises the bar (WWDC26)

The recipes above came from a **May-2026, pre-WWDC** blog. The 2026 OS / SwiftUI
release closes several of those gaps natively, so the order of preference tightens:

**Prefer SwiftUI 2026 native first**, AppKit-bridge only where it *still* can't reach:
- List/Grid/Section **content reordering** APIs (replaces hand-rolled move logic).
- **Swipe actions on any view** (row actions: approve/reject/merge without a menu).
- **Toolbar** visibility-priority + auto-minimizing (the 3-pane toolbar-precision gap).
- **AsyncImage caching** (reading-surface thumbnails — all via storage HTTP, never local paths).
- **Lazy `@State` init for Observable** (cheaper view-model construction at scale).
- `\.appearsActive` / `\.isEmphasized` for selection emphasis on focus loss.

**When a bridge is still needed**, the mechanism is the "Use SwiftUI with AppKit"
toolkit: `NSHostingView`/`NSHostingController`, the Observation framework for
auto-updating AppKit from `@Observable`, and AppKit gesture-recognizer bridging.
Same containment discipline; fold into the existing stack.

**Does NOT apply to us:** the new disk-access **Document protocol** (snapshot diffing
against local files) — Fichero's engine may be remote; data is HTTP, not local disk.
Swift's `FileDocument`/`ReferenceFileDocument` model is not our architecture.

**Profiling (#1815):** Xcode 27 **Instruments / Top Functions** is the SwiftUI-side
profiler to pair with the backend perf harness (the 225 ms doc-scoped entity path).

**Data structures:** adopt **swift-collections** (`OrderedSet`, `OrderedDictionary`)
for stable ordered grouping + entity/claim dedup substrate.

**Best Mac element for an item:** a `List` row (it's `NSTableView` underneath →
free selection/emphasis/context-menu-target). Convert custom `ScrollView`+`VStack`
item lists to `List` **only with an interaction spot-check**, since some of ours
(e.g. the inspector Entities tab) have *deliberately-built* standard-macOS multi-select
that a blind swap could regress — iterate, don't replace working selection behavior.

---

## Addendum 2026-06-08 (eve) — control choice + no swipe (Daniel)

**Best Mac control per surface:**
- **`List`** — single-column **item** lists: the document inspector (entities, claims, notes,
  annotations) and sidebar nav. NSTableView-backed → free selection emphasis + context-menu
  ring. Supports everything we need: **multi-select** (`selection:` Set), **hierarchy**
  (`Section` / `OutlineGroup` / `children:`), **drag-to-reorder** (`.onMove` /
  `.draggable`+`.dropDestination`). **This is the inspector's element — not `Table`.**
- **`Table`** — multi-**column** tabular data with sortable columns: the **library browser**
  (name/type/date/size). Use here, not in the inspector.
- **AppKit `NSOutlineView` / `NSTableView`** (bridged) — only if `List`+`OutlineGroup` can't
  express a needed hierarchy+reorder+column combo on macOS 26.

**Swipe actions are NOT Mac-normal.** `.swipeActions` is an iOS idiom. On macOS, row actions
(approve / reject / delete) go in the **context menu + toolbar + keyboard** — never a swipe.
**Remove `.swipeActions` from all Mac lists.**

**Every inspector/list surface must support:** single-click select · double-click open
(`.simultaneousGesture(TapGesture(count: 2))`) · multi-select · hierarchy · drag-to-reorder.

**Editing is navigation, not modal (Daniel).** Do NOT use modal sheets/dialogs to edit
entities / claims / items. Edit in place: an inline `TextField` for rename, or **push a
detail/edit view *inside* the inspector with a Back button** (`NavigationStack` — the existing
"Back to document" pattern). The inspector is itself the hierarchy you drill into and back out
of; keep it that way. Confirmations (delete) may stay as alerts; *editing* never does.
