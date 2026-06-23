# Handoff — iOS Build Gate (Round 2, paused mid-iteration) — 2026-06-18

**Branch:** `0.0.2`
**Date:** 2026-06-18
**State:** paused for model swap. Working tree has 16 unstaged files (engine + Swift UI gates) plus 4 prior commits already on `0.0.2`.

## Goal Recap

Get the Fichero SwiftUI codebase compiling cleanly for `generic/platform=iOS Simulator` so we can drive a single iOS/Mac source toward visionOS later. Mac behaviour must stay byte-identical; iOS gets no-op placeholders for the few surfaces that need iPad-native work later (#2100).

## What's Already Shipped (commits on `0.0.2`)

```
c92d06af feat(ios): gate Mac-only SwiftUI APIs and add cross-platform colour shims (#2098)
187cd1d3 fix(ios): BackendConnectionView uses Image(platformImage:) (#2098)
4c86df97 feat(ios): replace HSplitView/VSplitView with Platform shims (#2098)
39d55956 build(ios): register FicheroApp_iOS.swift in Xcode target + add SwiftUI iOS entry (#2098)
```

The first commit (`39d55956`) re-registered `FicheroApp_iOS.swift` via `scripts/add-swift-file.rb`. The xcodeproj gem normalised a few cosmetic fields at the same time (build-config naming, dstSubfolder, shellScript quoting) — no behaviour change.

## Last `xcodebuild` Run

```
xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero \
  -destination 'generic/platform=iOS Simulator' \
  -skipPackagePluginValidation build
```

Last error count: **8 errors** (down from ~25 at the start of the session).

## Remaining iOS Compile Errors (from `/tmp/iosrun13.log`)

These are the next 8 to fix:

1. `Views/ContentViewHelperViews.swift:30,32` — `NSCursor.resizeLeftRight.set()` / `arrow.set()` (in `.onHover`). Already wrapped once but my regex pass left the iOS branch malformed (`.onHover { ... #if os(macOS) ... #else _ = false arrow #endif }`). Needs a clean rewrite.
2. `Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCard+Details.swift:77,79` — same `NSCursor` pattern. Same regex damage.
3. `Views/Library/DocumentKGWebPane.swift:491,494` — `GuardedWKWebView` iOS branch overrides `setFrameSize(_:)` which doesn't exist on UIKit's WKWebView. The second attempt (override `layoutSubviews`) compiled then hit a different error; the file currently still has the broken `setFrameSize` form.
4. `Views/Library/LibraryView+TableMapViews.swift:24` — `.alternatingRowBackgrounds()` is macOS-only. Wrap in `#if os(macOS)` / `#endif`.
5. `Views/Library/PDFPageWithToolbar.swift:272` — `PDFLoupeOverlay(...)` call passes an argument list that the iOS placeholder view (just `Color.clear`) doesn't accept. The placeholder view needs the same parameter list as the macOS one (or wrap the call site in `#if os(macOS)`).

## Strategy for the Next Model

1. Fix `ContentViewHelperViews.swift` and `ClaimSummaryCard+Details.swift` — replace the broken `#if os(macOS) ... #else _ = false arrow #endif` block with a proper `#if os(macOS) if ... else ... #endif` block. Easy `apply_patch`.
2. Fix `DocumentKGWebPane.swift` iOS branch — drop the `override func setFrameSize` and replace with `override func layoutSubviews()` that clamps `bounds.size` before calling `super.layoutSubviews()`.
3. Wrap `.alternatingRowBackgrounds()` in `LibraryView+TableMapViews.swift` with `#if os(macOS)`.
4. Make `PDFLoupeOverlay` iOS placeholder accept the same parameter list as macOS (`documentId`, `pageIndex`, `cursorPosition`, `magnification`, `loupeSize`) and ignore them. That keeps the call site untouched.
5. Re-run `xcodebuild` and iterate. Expect 3–6 more rounds — there's still a long tail (chat / search / activity panes haven't been hit yet by the iOS compiler).

## Files Currently Unstaged (16)

These were modified by the iOS-gate work but never committed (intentional — they belong to the same logical change as the last commit, just hadn't been swept up yet):

```
M fichero-engine/src/fichero/db.py                  # registers migrate_spatial_node_layout_fields
M fichero-engine/src/fichero/db_migrations.py      # the spatial_node layout migration (ms/macos-gating)
M fichero-engine/src/fichero/spatial_models.py     # new layout fields on SpatialNode
M fichero/fichero-tests/InspectorLayoutTests.swift # #if os(macOS) guard
M fichero/fichero/FicheroApp.swift                 # #if os(macOS) wrap
M fichero/fichero/Resources/Assets.xcassets/AppIcon.appiconset/Contents.json  # iOS App Store icon entry
M fichero/fichero/Views/Components/MacPlainTextEditor.swift     # already Mac-only gated by previous coder
M fichero/fichero/Views/Library/DocumentInspector/AttributedTextEditor.swift  # ditto
M fichero/fichero/Views/Library/ImageViewer/ImageWithCursorTracking.swift    # ditto
M fichero/fichero/Views/Library/ImageViewer/TrackingImageView.swift         # ditto
M fichero/fichero/Views/Library/MagnifierPanel.swift           # ditto
M fichero/fichero/Views/Library/PDFPageView.swift              # ditto
M fichero/fichero/Views/Library/ScrollWheelZoom.swift          # ditto
M fichero/fichero/Views/Research/ResearchBrowserPane.swift     # removed unused `import AppKit`
M fichero/fichero/Views/Sidebar/SidebarView+ActivityRows.swift  # gated NSApp usage
M fichero/fichero/Views/Sidebar/SidebarView+ViewComponents.swift  # ditto
```

The backend three (`db.py`, `db_migrations.py`, `spatial_models.py`) come from `ms/macos-gating` and were already on `0.0.2` working tree at session start. Per STATE.md ("manager did NOT commit because content/status unknown; review before committing"), please eyeball them — they're the spatial node layout fields migration (#2293), idempotent with sensible defaults, looks safe to commit but worth a glance.

## Out-of-Scope Files (don't touch)

- `fichero/Views/Components/PlatformSplitView.swift` and `fichero/Views/Library/PlatformTypes.swift` — both already deleted from disk (they were duplicate shims or stale leftovers; we use `PlatformAliases.swift` only).
- `handoff-2026-06-18-ios-build-gate.md` — the original first handoff; superseded by this one. Safe to delete.
- `agent-work/icanh-notes/` — Daniel's ICANH project notes, not part of Fichero.

## Cross-Platform Patterns Established

`Models/Platform/PlatformAliases.swift` is the canonical home for these. Add new shims here, not inline:

| Pattern | Mac form | iOS form |
|---|---|---|
| `PlatformImage` | `NSImage` | `UIImage` |
| `PlatformColor` | `NSColor` | `UIColor` |
| `PlatformFont` | `NSFont` | `UIFont` |
| `PlatformViewRepresentable` | `NSViewRepresentable` | `UIViewRepresentable` |
| `PlatformHSplitView` | `HSplitView` (NSSplitView) | `HStack` shim |
| `PlatformVSplitView` | `VSplitView` (NSSplitView) | `VStack` shim |
| `Image(platformImage:)` | `init(nsImage:)` | `init(uiImage:)` |
| `Color(platformColor:)` | `init(nsColor:)` | `init(uiColor:)` |
| `NSColor.platformQuaternaryLabel` | `quaternaryLabelColor` | n/a |
| `UIColor.platformQuaternaryLabel` | n/a | `quaternaryLabel` |
| `NSColor.platformSelectedControl` | `selectedControlColor` | n/a |
| `UIColor.platformSelectedControl` | n/a | `tertiarySystemFill` |

VisionOS will slot in cleanly: the `#if canImport(...)` blocks already use the `canImport(AppKit)` / `canImport(UIKit)` form, which is the right pattern for adding `canImport(Vision)` branches later.

## Build/Test Commands

Backend:
```bash
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived
```

iOS gate (the one we drive):
```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero \
  -destination 'generic/platform=iOS Simulator' \
  -skipPackagePluginValidation build 2>&1 | tee /tmp/iosrun.log
```

Mac gate (regression check):
```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero \
  -destination 'platform=macOS' \
  -skipPackagePluginValidation build 2>&1 | tee /tmp/macrun.log
```

Lint (cheap):
```bash
swiftlint lint --quiet --cache-path .swiftlint-cache fichero/fichero/
```

## verify_all.sh Updates Wanted

Add `--ios` / `--macos` flags to `scripts/verify_all.sh` so the manager gate can run both platforms in CI. Currently only `--full` does a Mac xcodebuild test. Suggested diff shape:

```bash
run_ios() {
  echo "verify_all tier: ios"
  run_fast   # swiftlint + ruff + guardrails
  run_check "xcodebuild iOS Simulator" xcodebuild \
    -project fichero/fichero.xcodeproj \
    -scheme Fichero \
    -destination 'generic/platform=iOS Simulator' \
    -skipPackagePluginValidation \
    build
}
```

Add `ios` and `macos` to the case dispatch and document in the help block. The manager gate should call `verify_all --ios --macos --standard` after every iOS-gate commit.

## Definition of Done (carry over from original)

1. `xcodebuild ... -destination 'generic/platform=iOS Simulator' build` returns 0 errors.
2. `xcodebuild ... -destination 'platform=macOS' build` still returns 0 errors (no regression).
3. Backend `ruff check` + `pytest fichero-engine/tests/unit/` still pass.
4. `swiftlint lint fichero/fichero/` shows no NEW warnings vs the baseline (warnings are pre-existing — the build only blocks errors).
5. Everything committed to `0.0.2` with conventional-commit messages referencing #2098 (and #2100 / #2321 for follow-ups).
6. `git push origin 0.0.2` succeeds.
7. STATE.md handoff doc updated to point at the next session.
