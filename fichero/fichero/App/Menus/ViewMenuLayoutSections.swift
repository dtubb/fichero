import SwiftUI

// MARK: - Library Layout Section

/// Library layout selection commands (Icons, List, Table, Map)
/// Only shown for Library and Search modes
struct LibraryLayoutSection: View {
    @Bindable var viewSettings: ViewSettings
    let featureManager = FeatureManager.shared
    @FocusedValue(\.sidebarMode) var sidebarMode

    /// Only show view options for modes that need them (Library, Search)
    private var shouldShowViewOptions: Bool {
        guard let mode = sidebarMode?.wrappedValue else { return false }
        switch mode {
        case .library, .search:
            return true
        case .chat, .workflows, .automation, .activity, .research, .knowledgeGraph:
            return false
        }
    }

    private var availableLayouts: [LibraryLayout] {
        guard let mode = sidebarMode?.wrappedValue else { return [] }
        if mode == .library && !featureManager.isLibraryAdvancedViewsEnabled {
            return [.icons]
        }
        if mode == .search && !featureManager.isSearchAdvancedViewsEnabled {
            return [.list]
        }
        return [.icons, .list, .table, .canvas, .space]
    }

    var body: some View {
        if shouldShowViewOptions {
            Section("View") {
                if availableLayouts.contains(.icons) {
                    LibraryLayoutButton(
                        layout: .icons,
                        label: "as Icons",
                        icon: "square.grid.2x2",
                        shortcut: "1",
                        current: viewSettings.libraryLayout
                    ) {
                        viewSettings.libraryLayout = .icons
                    }
                }

                if availableLayouts.contains(.list) {
                    LibraryLayoutButton(
                        layout: .list,
                        label: "as List",
                        icon: "list.bullet",
                        shortcut: "2",
                        current: viewSettings.libraryLayout
                    ) {
                        viewSettings.libraryLayout = .list
                    }
                }

                if availableLayouts.contains(.table) {
                    LibraryLayoutButton(
                        layout: .table,
                        label: "as Columns",
                        icon: "tablecells",
                        shortcut: "3",
                        current: viewSettings.libraryLayout
                    ) {
                        viewSettings.libraryLayout = .table
                    }
                }

                if availableLayouts.contains(.canvas) {
                    LibraryLayoutButton(
                        layout: .canvas,
                        label: "as Canvas",
                        icon: "rectangle.3.group",
                        shortcut: "4",
                        current: viewSettings.libraryLayout
                    ) {
                        viewSettings.libraryLayout = .canvas
                    }
                }

                // "Space" (⌘5) — the RealityKit 3D renderer restored (#3088), a
                // second renderer on the same shared canvas stores as ⌘4 Canvas.
                if availableLayouts.contains(.space) {
                    LibraryLayoutButton(
                        layout: .space,
                        label: "as Space",
                        icon: "cube.transparent",
                        shortcut: "5",
                        current: viewSettings.libraryLayout
                    ) {
                        viewSettings.libraryLayout = .space
                    }
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
        guard let mode = sidebarMode?.wrappedValue else { return false }
        return mode == .library || mode == .search
    }

    var body: some View {
        if shouldShow {
            Section("Sort By") {
                ForEach(LibrarySortField.allCases) { field in
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
        case .library, .search:
            if !featureManager.isLibrarySearchSplitLayoutsEnabled {
                return [.standard]
            }
            return [.none, .standard, .widescreen]
        case .chat:
            return [.none, .standard, .widescreen]
        case .workflows, .automation, .activity, .research, .knowledgeGraph:
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
            // Icons/List/Column/Map — is LibraryLayoutSection ⌘1-4, not here.)
            Section("Preview") {
                if availablePreviewModes.contains(.widescreen) {
                    PreviewModeButton(
                        mode: .widescreen,
                        label: "Show Side Preview",
                        icon: "rectangle.split.2x1",
                        shortcut: "5",
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
                        shortcut: "6",
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
                        shortcut: "7",
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
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.command]
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

// MARK: - Knowledge Graph View Mode Section

/// Global Knowledge Graph view-mode switcher (List/Graph/Chart/Timeline/Map),
/// surfaced as View-menu items instead of a segmented icon row inside the KG
/// pane toolbar (#2436, same principle as `RepresentationSection`). Reads/writes
/// the focused `OntologyBrowser`'s active mode via FocusedValues, so it's
/// per-window and disables when the KG browser is not focused.
struct KnowledgeGraphViewModeSection: View {
    @FocusedValue(\.knowledgeGraphViewMode) private var knowledgeGraphViewMode

    private var current: OntologyBrowser.ViewMode? {
        knowledgeGraphViewMode?.current
    }

    var body: some View {
        Section("Knowledge Graph View") {
            ForEach(OntologyBrowser.ViewMode.allCases) { mode in
                Button {
                    knowledgeGraphViewMode?.select(mode)
                } label: {
                    Label(mode.label, systemImage: mode.icon)
                    if current == mode {
                        Image(systemName: "checkmark")
                    }
                }
                .disabled(knowledgeGraphViewMode == nil)
            }
        }
    }
}
