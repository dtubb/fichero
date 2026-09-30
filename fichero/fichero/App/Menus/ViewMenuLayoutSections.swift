import SwiftUI

// MARK: - Library Layout Section

/// Library layout selection commands (Icons, List, Table, Map)
/// Only shown for Library mode
struct LibraryLayoutSection: View {
    @Bindable var viewSettings: ViewSettings
    let featureManager = FeatureManager.shared
    @FocusedValue(\.sidebarMode) var sidebarMode
    /// Slice E (#4965, source-model panes recon, 2026-09-20): when a Library pane is focused in
    /// a workspace, these commands write to THAT pane's own `PaneConfig.libraryLayout` instead of
    /// `viewSettings.libraryLayout` (a window-wide setting a workspace-defined layout always
    /// overrides — Root E of the recon, verified: only a workspace definition could ever set
    /// `\.paneLibraryLayout`, so this menu's picks had nowhere to land in a workspace). `nil`
    /// fields (`commands` itself absent, or `setFocusedLibraryLayout` nil within it) fall back to
    /// today's window-wide write — "if no Library pane is focused, the commands act as today."
    @FocusedValue(\.windowLayoutCommands) private var commands

    /// Only show view options for modes that need them (Library)
    private var shouldShowViewOptions: Bool {
        guard let mode = sidebarMode?.wrappedValue else { return false }
        switch mode {
        case .library:
            return true
        case .chat, .workflows, .automation, .activity, .research:
            return false
        }
    }

    private var availableLayouts: [LibraryLayout] {
        guard let mode = sidebarMode?.wrappedValue else { return [] }
        if mode == .library && !featureManager.isLibraryAdvancedViewsEnabled {
            return [.icons]
        }
        return [.icons, .list, .table, .columns, .canvas, .space]
    }

    /// `LibraryLayout` ↔ the raw string `PaneConfig.libraryLayout`/`ViewDisplayMode
    /// (paneLibraryLayout:)` already parse — NOT `LibraryLayout.rawValue` (capitalized,
    /// "Icons"/"List"/…, a DIFFERENT vocabulary; see `App/ViewSettings.swift`). `nil` for a case
    /// the per-pane field doesn't recognize (`.grid`/`.cards`/`.timeline`/`.calendar`/`.geoMap` —
    /// Dataset-Stage-2 cases this menu doesn't even render buttons for, per `availableLayouts`).
    /// `static`/`nonisolated`, not instance methods: pure conversions with no view state, so a
    /// non-@MainActor Swift Testing suite can call them directly (`LibraryLayoutSection` is a
    /// `View`, @MainActor-isolated by default — same reasoning as `ContentView.canSplit`,
    /// `WorkspaceSplitStack.resolvedFixedExtent` elsewhere in this slice).
    nonisolated static func paneLayoutRawValue(for layout: LibraryLayout) -> String? {
        switch layout {
        case .icons: "icons"
        case .list: "list"
        case .table: "table"
        case .columns: "columns"
        case .canvas: "canvas"
        case .space: "space"
        case .grid, .cards, .timeline, .calendar, .geoMap: nil
        }
    }

    nonisolated static func libraryLayout(fromPaneRaw raw: String) -> LibraryLayout? {
        switch raw.lowercased() {
        case "icon", "icons": .icons
        case "list": .list
        case "table", "column", "columns-table": .table
        case "columns", "millercolumns": .columns
        case "canvas": .canvas
        case "space": .space
        default: nil
        }
    }

    /// What THIS button's checkmark compares against: the focused Library leaf's own explicit
    /// choice when one exists and this menu recognizes it, else the window-wide default —
    /// unchanged fallback, so a non-workspace window (or a focused non-Library pane) reads
    /// exactly as before.
    private var effectiveCurrent: LibraryLayout {
        guard let raw = commands?.focusedLibraryLayout, let layout = Self.libraryLayout(fromPaneRaw: raw) else {
            return viewSettings.libraryLayout
        }
        return layout
    }

    /// Write the pick to the focused Library leaf's own field when one exists AND this menu's
    /// vocabulary covers it; otherwise today's window-wide write (`viewSettings.libraryLayout`) —
    /// team-lead's own "if no Library pane is focused, the commands act as today."
    private func selectLayout(_ layout: LibraryLayout) {
        if let setFocusedLibraryLayout = commands?.setFocusedLibraryLayout, let raw = Self.paneLayoutRawValue(for: layout) {
            setFocusedLibraryLayout(raw)
        } else {
            viewSettings.libraryLayout = layout
        }
    }

    var body: some View {
        if shouldShowViewOptions {
            // No inner title: the parent flyout is already "View ▸ Layout ▸",
            // so a "View"/"Layout" header here would read redundantly.
            Section {
                if availableLayouts.contains(.icons) {
                    LibraryLayoutButton(
                        layout: .icons, label: "as Icons", icon: "square.grid.2x2",
                        shortcut: "1", current: effectiveCurrent
                    ) { selectLayout(.icons) }
                }

                if availableLayouts.contains(.list) {
                    LibraryLayoutButton(
                        layout: .list, label: "as List", icon: "list.bullet",
                        shortcut: "2", current: effectiveCurrent
                    ) { selectLayout(.list) }
                }

                if availableLayouts.contains(.table) {
                    LibraryLayoutButton(
                        layout: .table, label: "as Table", icon: "tablecells",
                        shortcut: "3", current: effectiveCurrent
                    ) { selectLayout(.table) }
                }

                if availableLayouts.contains(.canvas) {
                    LibraryLayoutButton(
                        layout: .canvas, label: "as Canvas", icon: "rectangle.3.group",
                        shortcut: "4", current: effectiveCurrent
                    ) { selectLayout(.canvas) }
                }

                // "Space" (⌘5) — the RealityKit 3D renderer restored (#3088), a
                // second renderer on the same shared canvas stores as ⌘4 Canvas.
                if availableLayouts.contains(.space) {
                    LibraryLayoutButton(
                        layout: .space, label: "as Space", icon: "cube.transparent",
                        shortcut: "5", current: effectiveCurrent
                    ) { selectLayout(.space) }
                }
                // Miller columns (⌘6, #4160 step 4) — APPENDED so ⌘1-5 muscle
                // memory is untouched; the table reverts to "as Table" now a
                // real columns mode exists.
                if availableLayouts.contains(.columns) {
                    LibraryLayoutButton(
                        layout: .columns, label: "as Columns", icon: "rectangle.split.3x1",
                        shortcut: "6", current: effectiveCurrent
                    ) { selectLayout(.columns) }
                }

            }
        }
    }
}

/// Reusable library layout button with checkmark when active
struct LibraryLayoutButton: View {
    let layout: LibraryLayout
    let label: String
    let icon: String
    let shortcut: String
    let current: LibraryLayout
    let action: () -> Void

    var body: some View {
        // A Toggle with a Label, not a Button around an HStack: macOS menus flatten an HStack and
        // drop its images, so the icons never showed and the checkmark was hand-drawn. As a
        // native item the menu draws the checkmark and the icon itself, as Finder's View menu does.
        Toggle(isOn: Binding(get: { current == layout }, set: { _ in action() })) {
            Label(label, systemImage: icon)
        }
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.command]
        )
    }
}
