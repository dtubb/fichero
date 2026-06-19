# STATE — iOS compile gate handoff for terminal Codex — 2026-06-18

Branch `0.0.2` is **ahead of `origin/0.0.2` by 5 commits** and still has a large intentional dirty worktree from the ongoing cross-platform/iOS gate plus the pre-existing spatial-node backend port. **Do NOT push until an iOS Simulator build is green.**

## ☀️ START HERE
Use Xcode or a Codex session that has a callable Xcode MCP `BuildProject`. In this desktop session the Xcode MCP appeared discoverable but never became directly callable, so final verification depended on Daniel running builds in Xcode while fixes landed in the worktree.

## In Progress / pending gate
- **iOS compile gate (#2098)** is much closer than at session start: this session cleared another chunk of macOS-only API/compiler blockers (`onDeleteCommand`, `onMoveCommand`, `NSApplication`, `NSSavePanel`, AppKit find-panel action, `onModifierKeysChanged`, stale imported-type `Identifiable` warnings, `Text + Text` deprecations, AppleScript stub sendability issue).
- Xcode was still surfacing some stale diagnostics while indexing/typechecking; repeated warnings for already-fixed lines were common until a fresh pass recompiled those files.
- **visionOS gate (#2321–#2322)** still stays behind iOS=0. `PlatformAliases.swift` already uses the right `canImport(...)` pattern.

## Next Session — Start Here
1. Run a fresh iOS Simulator build in Xcode/Xcode MCP after indexing settles. Trust current file contents over stale diagnostics; clean build folder if Xcode repeats already-fixed lines.
2. If the build blocks on app icons, patch `fichero/fichero/Resources/Assets.xcassets/AppIcon.appiconset/Contents.json`: the current 1024x1024 iOS entry is `idiom: universal`; Xcode likely wants the `ios-marketing` slot.
3. Continue the long-tail iOS sweep from the current dirty worktree, especially remaining AppKit/macOS-only surfaces in `ContentView*`, library/inspector helpers, and any fresh compiler errors that Xcode reports after a clean pass.
4. After iOS goes green, review/commit the pre-existing spatial-node backend port (`db.py`, `db_migrations.py`, `spatial_models.py`) and the remaining Swift gating files in coherent batches, then push.

**Held (do not touch):** worktrees `entitytable-2020` (#2020), `lan-tls-2157` (#2157), `importers`, `ms/macos-gating`. Daniel may still be using backend state on `:8765`; do not start/stop it casually.

## Mac Behaviour
All fixes this session were intended as compile-time/platform-gating changes only. The guiding pattern was: preserve macOS behavior, add iOS-safe no-ops/placeholders, and prefer `canImport(AppKit)` blocks or shared platform aliases over per-site ad hoc forks.
