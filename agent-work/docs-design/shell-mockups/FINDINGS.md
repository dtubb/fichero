# Shell Mockup Findings

Lane F — Interactive per-device shell mockups. Files: `index.html`, `mac.html`, `ipad.html`, `iphone.html`, `appletv.html`, `visionos.html`.

## Files

| File | Device | Interaction |
|---|---|---|
| `index.html` | Landing | Links + zones diagram |
| `mac.html` | Mac | Mode switching, sidebar/inspector toggles, animated transitions, ⌘1–9 keyboard shortcuts |
| `ipad.html` | iPad | 3 pair states (Library+Preview / Reader+Preview / Reader+Inspector), sidebar overlay |
| `iphone.html` | iPhone | Horizontal swipe stack (4 zones), back nav, inspector as bottom sheet, touch swipe |
| `appletv.html` | Apple TV | 3 screens (Browse/Library/Reader), focus-ring navigation, arrow key nav |
| `visionos.html` | visionOS | 5 independent draggable glass windows, ornament toolbar, show/hide per-window |

## Interaction decisions

**Mac — mode switching is the core mechanic.** Clicking a sidebar item replaces *only* the content column. Sidebar and inspector never change structure. Inspector tabs (Info / KG / Annotations / Notes) persist across mode changes. `⌃⌘S` toggles sidebar, `⌃⌘I` toggles inspector — both with smooth `width` CSS transitions. The toolbar's center zone (lens-aware actions) updates per mode to show relevant actions.

**Mac — glass on nav surfaces only.** Sidebar and inspector use `backdrop-filter: blur(40px) saturate(180%)`. The content column stays opaque (`#f5f5f7` / dark equivalent). Reading archival documents through frosted glass would be wrong.

**iPad — "two zones max" constraint.** The constraint isn't arbitrary: a 10" iPad in landscape isn't wide enough to show three usable columns. The note is embedded in the sidebar overlay panel so Daniel sees it while using the mockup. The sidebar *overlays* Library rather than consuming a column — same pattern as Files.app on iPadOS.

**iPad — three meaningful pairs.** Library+Preview (browsing), Reader+Preview (reading with thumbnails), Reader+Inspector (reading with metadata). These are the three workflows Daniel actually does. The "sidebar overlay" state is a fourth state, but it's a transient overlay, not a pair.

**iPhone — swipe stack is the correct mental model.** Zone 0 (Sidebar/mode picker) → Zone 1 (Library) → Zone 2 (Reader) → Zone 3 (Inspector). Inspector *also* appears as a bottom sheet from Zone 2 (Reader), because on iPhone you'd often want to peek at the inspector without losing your place in the document.

**visionOS — each zone is an independent window.** This is the key design decision: don't try to fit the Mac shell into a single visionOS window. The user places them spatially — Reader big in front, Inspector floating to the right, Library below. The ornament toolbar (floating below all windows) mirrors the Mac toolbar concept but as a floating element in space.

## Open design questions

1. **Mind Palace as a mode vs. library view-mode.** The current plan (`#1455`) retires Mind Palace as a sidebar lens and folds it into the Library as a 2D/3D view-mode. The mockup shows it as a mode for context, but this may change. If it becomes a library view-mode, the sidebar drops to 8 items.

2. **Research + Chat → Agent lens?** The design proposal (`mac_shell_design_proposal.md §9`) asks: should Research + Chat converge into one "Agent" lens (#2067) now, or stay separate? If yes: the THINK band shrinks to one item. The mockup shows them separately for now.

3. **iPad: should Preview exist as a right column?** On iPad in landscape, Library+Preview is a natural pair. But in portrait or on smaller iPads, Preview may not have enough width to be useful. The mockup doesn't show portrait mode.

4. **visionOS immersive Spaces.** The BRIEF notes a future immersive mode (#2398) where images appear on real walls/floor. The mockup doesn't show this — it's outside the current shell design scope.

5. **iPhone: 4-zone stack vs. 5?** The mockup treats Sidebar + Library as the first two zones (Sidebar is the "home" zone). Preview is skipped as a standalone zone on iPhone — you go directly Sidebar → Library → Reader → Inspector. This is a deliberate UX call: Preview on a 6" screen is too narrow to be useful.

6. **Apple TV: is this worth building?** The TV mockup shows a read-only browse+read experience, which is a subset of what the app does. Building a tvOS target would be a significant investment. The mockup is here to show what it *could* look like, not to commit to building it.

## Implementation notes for SwiftUI

When adapting the Mac shell to adapt down to iPad/iPhone:

- The existing `NavigationSplitView` with `.sidebar`, `.content`, `.detail` columns is already the right structure.
- On iPad, `NavigationSplitView` can be set to show `preferredCompactColumn` when the size class is `.compact`.
- On iPhone, the split view collapses to a `NavigationStack` automatically.
- visionOS would need separate scene handling — each zone as its own `WindowGroup`.

The key insight the mockups demonstrate: **no new code is needed for the navigation model — SwiftUI's `NavigationSplitView` already adapts between these layouts at the framework level.** The implementation work is making the *content* of each zone work at each size (font sizes, touch target sizes, etc.), not rebuilding the navigation structure.
