# iOS Bring-up Issue Plan — 2026-06-18

Source of truth reviewed:
- `/tmp/iosrun13.log` — latest recorded `generic/platform=iOS Simulator` build
- `STATE.md`
- `handoff-2026-06-18-ios-build-gate.md`
- GitHub issues `#2098`, `#2319`, `#2321`, `#2322`, `#2311`

## Latest authoritative backlog

The latest recorded iOS build shows **8 compile errors** and no durable warning list worth filing separately. Grouped by theme:

1. `PDFPageWithToolbar.swift`
   - `argument passed to call that takes no arguments`
2. `ContentViewHelperViews.swift` and `ClaimSummaryCard+Details.swift`
   - `cannot find 'NSCursor' in scope`
3. `LibraryView+TableMapViews.swift`
   - `'alternatingRowBackgrounds' is unavailable in iOS`
4. `DocumentKGWebPane.swift`
   - `method does not override any method from its superclass`
   - `WKWebView has no member 'setFrameSize'`

Separate from that log, the handoff still calls out two remaining raw `HSplitView` sites in:
- `ScheduleEditorView.swift`
- `TriggerEditorView.swift`

## Do not file — immediate branch fixes

These belong to the active `#2098` iOS compile gate and should be fixed on `0.0.2`, not split into fresh GitHub issues unless they survive the branch bring-up:

- The current 8 compile errors above
- The two remaining raw `HSplitView` replacements from the handoff
- Any app-icon catalog correction (`ios-marketing`) if it becomes the next build blocker

Also do **not** file duplicates for:
- `#2319` Sparkle iOS-link blocker — already open and recent commits indicate branch work is underway
- `#2321` / `#2322` visionOS bring-up — explicitly downstream of iOS=0
- `#2311` view display mode default bug — already closed
- A new row-stripes feature issue — `#2259` already covered the product-level table-striping work

## Issue candidates to file only after #2098 is green

1. **iOS follow-up: centralize pointer/hover affordances behind a platform helper**
   - Scope: replace ad hoc `NSCursor` usage in shared SwiftUI views with one platform abstraction or no-op iOS path.
   - Rationale: the latest build hit this in multiple files; it will recur outside the current two call sites.

2. **DocumentKGWebPane: split AppKit and UIKit WKWebView sizing/lifecycle code**
   - Scope: separate macOS-only `WKWebView` behavior from UIKit implementation and make shared pane code compile-clean on both.
   - Rationale: the `override` / `setFrameSize` errors show the current wrapper still leaks AppKit assumptions.

3. **Cross-platform audit: remove macOS-only table modifiers from shared Library views**
   - Scope: audit `Table`-related modifiers and extensions used by shared library surfaces; gate or replace macOS-only APIs cleanly.
   - Rationale: `alternatingRowBackgrounds` failed in iOS, and the same pattern is likely to reappear as more table surfaces compile.

4. **iOS polish: stabilize shared reading-surface toolbars after bring-up**
   - Scope: review `PDFPageWithToolbar` and related toolbar container APIs for cross-platform call-site drift after the compile gate lands.
   - Rationale: the current error is probably a local API mismatch, but the reading surface is cross-cutting enough to merit a cleanup ticket if more than one fix lands there.

5. **DX: add a clean iOS Simulator compile gate to manager/integrator verification**
   - Scope: make clean `generic/platform=iOS Simulator` compilation part of the normal cross-stack gate once `#2098` lands.
   - Rationale: several failures only surfaced in the clean iOS build, while stale Xcode diagnostics created noise during iteration.

## Filing threshold

File only the items that remain as **repeatable post-`#2098` follow-up work** after the branch reaches a green iOS Simulator build. If the active branch absorbs the fix while clearing the gate, do not create a separate issue.
