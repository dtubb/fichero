# STATE — iOS compile gate paused for MCP build handover 2026-06-18

Branch `0.0.2` is **ahead of `origin/0.0.2` by 4 commits** (the iOS-gate round 1+2 work). Mac compile gate passes; iOS Simulator compile gate **paused at 8 errors** because the next build needs `mcp__xcode__BuildProject` (which I don't have in this session) to share Xcode.app's cache and avoid the build.db lock that stalled `xcodebuild` CLI mid-session. **Do NOT push until iOS `generic/platform=iOS Simulator` build is green.**

## ☀️ START HERE
**Role: MANAGER — drive, don't implement.** Build via Xcode MCP `BuildProject` (tab `windowtab3`), not CLI xcodebuild — the SWBBuildService held `fichero/build/xcode/Intermediates/XCBuildData/build.db` for 30 minutes of CPU and `xcodebuild` had to delete it mid-session. After MCP green, push to origin.

Handoff doc with full context: `handoff-2026-06-18-ios-gate-r2.md` (last 156 lines, written this session).

## In Progress / pending gate
- **iOS compile gate (#2098) — 8 errors remaining** out of ~25 at session start. Last log: `/tmp/iosrun13.log`. The 4 quick fixes are listed in the handoff doc; expect another 3–6 long-tail rounds after those.
- **visionOS gate (#2321–#2322):** behind iOS=0. PlatformAliases.swift already uses `canImport(AppKit)` / `canImport(UIKit)` so adding `canImport(Vision)` later is mechanical.

## Next Session — Start Here
1. **MCP build, then fix the 4 known issues:** NSCursor regex damage in `ContentViewHelperViews.swift` and `ClaimSummaryCard+Details.swift`; `GuardedWKWebView` setFrameSize override on UIKit; `.alternatingRowBackgrounds()` wrap; `PDFLoupeOverlay` iOS placeholder signature.
2. **Extend `scripts/verify_all.sh`** with `--ios` and `--macos` flags (suggested diff in handoff doc) so the manager gate catches future iOS regressions automatically. xcodebuild CLI works fine here — slow but it gates.
3. **Commit the unstaged spatial port** (db.py / db_migrations.py / spatial_models.py) once it's reviewed — it's an idempotent ALTER TABLE migration that adds pos_w/pos_h/z_index/depth/angle/style_data to spatialnode. From ms/macos-gating, marked unknown at session start.
4. **Commit the remaining 13 unstaged Swift files** (mostly the earlier Bucket-C gating passes that landed in the working tree before session start): MacPlainTextEditor, AttributedTextEditor, ImageWithCursorTracking, TrackingImageView, MagnifierPanel, PDFPageView, ScrollWheelZoom, ResearchBrowserPane (unused AppKit import removed), SidebarView+ActivityRows, SidebarView+ViewComponents, FicheroApp.swift (`#if os(macOS)` wrap), InspectorLayoutTests (`#if os(macOS)` guard), AppIcon.appiconset (iOS App Store icon entry).

**Held (do not touch):** worktrees `entitytable-2020` (#2020), `lan-tls-2157` (#2157), `importers`, `ms/macos-gating`. Daniel is testing ICANH-Clean.fichero on :8765; do not start/stop the backend.

## Mac Behaviour
Every commit on 0.0.2 this session preserves Mac behaviour byte-identically (PlatformHSplitView is a `typealias` to HSplitView on macOS, FicheroApp.swift still wraps the macOS @main, every `NSColor.platform*` resolves to the same NSColor). iOS gets compile-clean no-ops; iPad-native replacements are #2100.
