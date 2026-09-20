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
    // `static`/`nonisolated`, not instance methods: pure conversions with no view state, so a
    // non-@MainActor Swift Testing suite can call them directly (`LibraryLayoutSection` is a
    // `View`, @MainActor-isolated by default — same reasoning as `ContentView.canSplit`,
    // `WorkspaceSplitStack.resolvedFixedExtent` elsewhere in this slice).
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

                // Miller columns (⌘6, #4160 step 4) — APPENDED so ⌘1-5 muscle
                // memory is untouched; the table reverts to "as Table" now a
                // real columns mode exists.
                if availableLayouts.contains(.columns) {
                    LibraryLayoutButton(
                        layout: .columns, label: "as Columns", icon: "rectangle.split.3x1",
                        shortcut: "6", current: effectiveCurrent
                    ) { selectLayout(.columns) }
                }

                // "Space" (⌘5) — the RealityKit 3D renderer restored (#3088), a
                // second renderer on the same shared canvas stores as ⌘4 Canvas.
                if availableLayouts.contains(.space) {
                    LibraryLayoutButton(
                        layout: .space, label: "as Space", icon: "cube.transparent",
                        shortcut: "5", current: effectiveCurrent
                    ) { selectLayout(.space) }
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
        Button(action: action) {
            HStack(spacing: 8) {
                if current == layout {
                    Image(systemName: "checkmark")
                        .frame(width: 12)
                }
                Image(systemName: icon)
                    .frame(width: 16)
                Text(label)
            }
        }
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.command]
        )
    }
}

// MARK: - Sort Section

/// Sort By and direction commands for the library/search content area
/// Only shown for Library and Search modes; reads/writes LibraryView sort state via FocusedValues
struct SortSection: View {
    @FocusedValue(\.sidebarMode) var sidebarMode
    @FocusedValue(\.librarySortField) var sortField
    @FocusedValue(\.librarySortAscending) var sortAscending

    private var shouldShow: Bool {
        sidebarMode?.wrappedValue == .library
    }

    var body: some View {
        if shouldShow {
            // No inner title: the parent flyout is "View ▸ Sort ▸", so a
            // "Sort By" header here would read as "Sort ▸ Sort By".
            Section {
                // The focused value carries the search context now, so this
                // menu offers Relevance exactly when the toolbar's does — and
                // never over a browsed folder, where it would name a ranking
                // that does not exist.
                ForEach(LibrarySortField.fields(isSearching: sortField?.isSearching ?? false)) { field in
                    Button {
                        sortField?.set(field.rawValue)
                    } label: {
                        Label(field.rawValue, systemImage: field.icon)
                        if sortField?.value == field.rawValue {
                            Image(systemName: "checkmark")
                        }
                    }
                }

                Divider()

                Button {
                    sortAscending?.set(true)
                } label: {
                    Text("Ascending")
                    if sortAscending?.value == true {
                        Image(systemName: "checkmark")
                    }
                }

                Button {
                    sortAscending?.set(false)
                } label: {
                    Text("Descending")
                    if sortAscending?.value == false {
                        Image(systemName: "checkmark")
                    }
                }
            }
        }
    }
}

// MARK: - Preview Mode Section

/// Preview mode selection commands (None, Standard, Widescreen)
/// Only shown for modes with preview panes (Library, Search, Chat)
struct PreviewModeSection: View {
    @Bindable var viewSettings: ViewSettings
    let featureManager = FeatureManager.shared
    @FocusedValue(\.sidebarMode) var sidebarMode

    /// Only show preview options for modes that have preview panes
    private var shouldShowPreviewOptions: Bool {
        availablePreviewModes.count > 1
    }

    private var availablePreviewModes: [PreviewMode] {
        guard let mode = sidebarMode?.wrappedValue else { return [] }
        switch mode {
        case .library:
            if !featureManager.isLibrarySearchSplitLayoutsEnabled {
                return [.standard]
            }
            return [.none, .standard, .widescreen]
        case .chat:
            return [.none, .standard, .widescreen]
        case .workflows, .automation, .activity, .research:
            return []
        }
    }

    var body: some View {
        if shouldShowPreviewOptions {
            // Preview LAYOUT — where the document preview sits relative to the
            // library list. Mail-modeled radio group (#2032/§6d):
            //   .widescreen → list and preview side-by-side  → "Show Side Preview"
            //   .standard   → list above, preview below       → "Show Bottom Preview"
            //   .none       → list only, no preview           → "Hide Preview"
            // (This is the PREVIEW position; the list's own column layout —
            // Icons/List/Table/Canvas/Space/Columns — is LibraryLayoutSection
            // ⌘1-6, not here.)
            //
            // Shortcuts are ⌃⌘ + letter (Daniel, 2026-09-05), NOT ⌘-numbers:
            // the layout section already owns ⌘1-6, and both sections render in
            // Library/Search mode, so ⌘5/⌘6 meant BOTH "as Space"/"as Columns"
            // AND "Show Side"/"Show Bottom" — a live collision. ⌃⌘ is the pane
            // family (the inspector toggle is ⌃⌘I); sidebar MODES take ⌃⌘
            // NUMBERS, so ⌃⌘ letters here don't collide with those either.
            // No inner title: the parent flyout is "View ▸ Preview ▸", so a
            // "Preview" header here would read as "Preview ▸ Preview".
            //
            // Menu audit 2026-09-17: "Show Side Preview" was ⌃⌘S — the macOS
            // HIG chord for Show/Hide Sidebar, which this app has no command
            // for at all (`toggleSidebar()` in ContentView+ActionsUI.swift has
            // zero callers). Freed to ⌃⌘J so a future Show/Hide Sidebar
            // command can claim ⌃⌘S; see MenuShortcutUniquenessTests' denylist,
            // which blocks ⌃⌘S until that command exists.
            Section {
                if availablePreviewModes.contains(.widescreen) {
                    PreviewModeButton(
                        mode: .widescreen,
                        label: "Show Side Preview",
                        icon: "rectangle.split.2x1",
                        shortcut: "j",
                        current: viewSettings.previewMode
                    ) {
                        viewSettings.previewMode = .widescreen
                    }
                }

                if availablePreviewModes.contains(.standard) {
                    PreviewModeButton(
                        mode: .standard,
                        label: "Show Bottom Preview",
                        icon: "rectangle.split.1x2",
                        shortcut: "b",
                        current: viewSettings.previewMode
                    ) {
                        viewSettings.previewMode = .standard
                    }
                }

                if availablePreviewModes.contains(.none) {
                    PreviewModeButton(
                        mode: .none,
                        label: "Hide Preview",
                        icon: "square",
                        shortcut: "h",
                        current: viewSettings.previewMode
                    ) {
                        viewSettings.previewMode = .none
                    }
                }
            }
        }
    }
}

/// Reusable preview mode button with checkmark when active
struct PreviewModeButton: View {
    let mode: PreviewMode
    let label: String
    let icon: String
    let shortcut: String
    let current: PreviewMode
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if current == mode {
                    Image(systemName: "checkmark")
                        .frame(width: 12)
                }
                Image(systemName: icon)
                    .frame(width: 16)
                Text(label)
            }
        }
        // ⌃⌘ (control+command), NOT plain ⌘: the plain ⌘-number range belongs to
        // the library layouts (⌘1-6), which render in the same mode — see the
        // collision note in PreviewModeSection.
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.command, .control]
        )
    }
}

// MARK: - Representation Section ("Add View")

/// Document content-area representation switcher, surfaced as View-menu items
/// instead of a floating icon bar over the WebKit content (#2032 / reform §G).
/// The maintainer: "the stuff shown in the WebKit/content view are really views that can
/// be ADDED — so the switcher should be MENU ITEMS, not icons." Reads/writes the
/// focused `DocumentKGSurface`'s active representation via FocusedValues, so it's
/// per-window and disables when no document surface is focused (same rationale as
/// `InspectorButton` / `PaneVisibilitySection`).
struct RepresentationSection: View {
    @FocusedValue(\.documentRepresentation) private var representation

    private var current: KGSurfaceTab? {
        representation?.current
    }

    var body: some View {
        Section("Add View") {
            ForEach(KGSurfaceTab.allCases) { tab in
                Button {
                    representation?.select(tab)
                } label: {
                    Label(tab.title, systemImage: tab.icon)
                    if current == tab {
                        Image(systemName: "checkmark")
                    }
                }
                .keyboardShortcut(
                    KeyEquivalent(tab.representationShortcut),
                    modifiers: [.control, .option, .command]
                )
                .disabled(representation == nil)
            }
        }
    }
}

// Knowledge Graph View Mode Section DELETED (#4705 increment 3): it switched
// the focused `OntologyBrowser`'s own List/Graph/Chart/Timeline/Map mode via
// FocusedValues — with `OntologyBrowser` retired there is no subject left for
// it to control. The `\.knowledgeGraphViewMode` FocusedValues entry and its
// `KnowledgeGraphViewModeFocus` wrapper (both `OntologyBrowser`-only) retire
// alongside it.
