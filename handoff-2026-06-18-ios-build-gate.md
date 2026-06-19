# Handoff — iOS Build Gate + Spatial Backend Port

**Branch:** `0.0.2` (current working branch)
**Date:** 2026-06-18
**Current user instruction:** STOP. User is going to hand this to a more powerful model via a session-end / handoff prompt.

## What Was In Progress

1. **iOS generic/platform=iOS Simulator build gate** — drive to 0 errors.
2. **Spatial/canvas backend port from `ms/macos-gating`** — already merged into `0.0.2` working tree (uncommitted).

## State of the Working Tree

Uncommitted changes on `0.0.2` include:

- `fichero-engine/src/fichero/spatial_models.py` — extended `SpatialNode` with layout fields, added canvas models.
- `fichero-engine/src/fichero/db_migrations.py` — added `migrate_spatial_node_layout_fields`.
- `fichero-engine/src/fichero/db.py` — wires the migration.
- `fichero/fichero/Resources/Assets.xcassets/AppIcon.appiconset/Contents.json` — iOS App Store icon entry.
- `fichero/fichero/Models/Platform/PlatformAliases.swift` — added `PlatformHSplitView` / `PlatformVSplitView` shims and macOS aliases.
- `fichero/fichero/Views/Sidebar/SidebarView+ViewComponents.swift` — removed unused `import AppKit`.
- `fichero/fichero/Views/Research/ResearchBrowserPane.swift` — removed unused `import AppKit`.
- `fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift` — gated AppKit usage.
- `fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+KGSection.swift` — gated AppKit usage.
- `fichero/fichero/Views/Sidebar/SidebarView+ActivityRows.swift` — gated AppKit/NSApp usage.
- `fichero/fichero/Views/AIProviders/ProvidersView.swift` — `HSplitView` → `PlatformHSplitView`.
- `fichero/fichero/Views/Library/AnnotationsInspectorPane.swift` — `VSplitView` → `PlatformVSplitView`.
- `fichero/fichero/Views/Notes/NotesInspectorPane.swift` — `VSplitView` → `PlatformVSplitView`.
- `fichero/fichero/Views/Library/StackedRepresentationPanes.swift` — `VSplitView` → `PlatformVSplitView`.
- `fichero/fichero/Views/Components/SplittablePane.swift` — `VSplitView` → `PlatformVSplitView` (4 usages).
- `fichero/fichero/Views/Library/PlatformTypes.swift` — deleted (duplicate of `PlatformAliases.swift`).
- `fichero/fichero.xcodeproj/project.pbxproj` — hand-edited to remove `PlatformTypes.swift` references because `xcodeproj` gem could not parse the project and `scripts/add-swift-file.rb` had a path bug. **Needs Xcode verification.**
- `fichero/fichero/FicheroApp_iOS.swift` — uncommitted file from earlier codemod; separate iOS `@main` entry point.

## Last Known Blockers

The iOS build was iterated via Xcode MCP `BuildProject`. The **only remaining raw `HSplitView` usages** at time of interruption:

- `fichero/fichero/Views/Automation/ScheduleEditorView.swift:41`
- `fichero/fichero/Views/Automation/TriggerEditorView.swift:57`

Both need to be changed from `HSplitView {` to `PlatformHSplitView {` (the shim is already defined in `PlatformAliases.swift`).

**Note:** User explicitly interrupted the `ScheduleEditorView.swift` edit and said "please stop." Do **not** resume editing without the user's explicit go-ahead.

## Next Steps for the Next Model

1. Confirm user wants to continue iOS build gate.
2. Replace remaining `HSplitView` usages in `ScheduleEditorView.swift` and `TriggerEditorView.swift` with `PlatformHSplitView`.
3. Run Xcode MCP `BuildProject` for iOS Simulator until 0 errors.
4. Run Mac build gate to ensure no regressions.
5. Commit all changes to `0.0.2` with conventional commits referencing relevant issues, then push to `origin/0.0.2`.
6. Verify `project.pbxproj` in Xcode is clean after the hand-removal of `PlatformTypes.swift`.

## Important Constraints

- **Do not hand-edit `project.pbxproj` further** unless `scripts/add-swift-file.rb` / `xcodeproj` gem is unavailable; if it must be hand-edited, note it in the commit message.
- **Do not create per-task branches** per `CLAUDE.md` rule 7; commit directly to `0.0.2`.
- **Run build/test/lint before marking complete.**
- **Never `rm -rf` a `~/code/fichero-*` sibling** — worktrees only under `~/code/fichero-worktrees/<name>`.

## Git Status Snapshot

- Branch: `0.0.2`
- Uncommitted: yes (the files listed above).
- Last successful push: `0.0.2` was ahead of origin and push succeeded earlier in session.
