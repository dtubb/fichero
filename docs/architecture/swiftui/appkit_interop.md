# AppKit Interop — "Mac-assed" Behavioral Fidelity

**Status:** Adopted 2026-06-08 (Daniel directive)
**Extends:** `SWIFTUI_PRINCIPLES.md` §8 ("Avoid AppKit Unless Absolutely Necessary")
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
  gap; add it to the table in `SWIFTUI_PRINCIPLES.md` §8 once it ships.
- Swift 6 concurrency rules apply inside the bridge (`@MainActor`, no `DispatchQueue.main`).

## What this is NOT

- Not a rewrite to AppKit. Not Catalyst. Not a license to bridge anything that's mildly annoying.
- Not an excuse to skip `List` where `List` already does the job.

Tracking: see the "Mac-assed app" EPIC and its children in GitHub Issues.
