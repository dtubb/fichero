import SwiftUI
// swiftlint:disable file_length

/// View menu commands - Sidebar modes, library layouts, preview modes, and inspector toggle
/// Extracted from FicheroApp.swift to maintain consistency with other menu command patterns
struct ViewMenuCommands: View {
    @EnvironmentObject var viewSettings: ViewSettings

    var body: some View {
        SidebarModeSection()

        Divider()

        LibraryLayoutSection(viewSettings: viewSettings)

        Divider()

        SortSection()

        Divider()

        PreviewModeSection(viewSettings: viewSettings)

        Divider()

        ImagePreviewMenuCommands()

        Divider()

        InspectorButton(viewSettings: viewSettings)

        Divider()

        ShowRulerButton()
        ShowFindBarButton()
    }
}

// MARK: - Sidebar Mode Section

/// Sidebar mode selection commands with keyboard shortcuts
/// Uses @FocusedValue to update the current window's sidebar mode (reads from focusedSceneValue)
struct SidebarModeSection: View {
    @FocusedValue(\.sidebarMode) var sidebarMode

    // Feature manager to hide modes
    @ObservedObject var featureManager = FeatureManager.shared

    /// Current mode, defaulting to .library if no window is focused
    private var currentMode: SidebarMode {
        sidebarMode?.wrappedValue ?? .library
    }

    var body: some View {
        Section("Sidebar") {
            // Content modes (1-2 always, 3-4 conditional)
            SidebarModeButton(
                mode: .library,
                label: SidebarMode.library.label,
                icon: SidebarMode.library.icon,
                shortcut: SidebarMode.library.shortcutNumber,
                current: currentMode
            ) {
                sidebarMode?.wrappedValue = .library
            }

            if featureManager.isSearchEnabled {
                SidebarModeButton(
                    mode: .search,
                    label: SidebarMode.search.label,
                    icon: SidebarMode.search.icon,
                    shortcut: SidebarMode.search.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .search
                }
            }

            if featureManager.isChatEnabled {
                SidebarModeButton(
                    mode: .chat,
                    label: SidebarMode.chat.label,
                    icon: SidebarMode.chat.icon,
                    shortcut: SidebarMode.chat.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .chat
                }
            }

            if featureManager.isWorkflowsEnabled {
                SidebarModeButton(
                    mode: .workflows,
                    label: SidebarMode.workflows.label,
                    icon: SidebarMode.workflows.icon,
                    shortcut: SidebarMode.workflows.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .workflows
                }
            }

            if featureManager.isAutomationEnabled {
                Divider()
            }

            if featureManager.isAutomationEnabled {
                SidebarModeButton(
                    mode: .automation,
                    label: SidebarMode.automation.label,
                    icon: SidebarMode.automation.icon,
                    shortcut: SidebarMode.automation.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .automation
                }
            }

            if featureManager.isActivityEnabled {
                Divider()

                // Activity mode (7) - unified view of all workflow runs
                SidebarModeButton(
                    mode: .activity,
                    label: SidebarMode.activity.label,
                    icon: SidebarMode.activity.icon,
                    shortcut: SidebarMode.activity.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .activity
                }
            }
        }
    }
}

/// Reusable sidebar mode button with checkmark when active
struct SidebarModeButton: View {
    let mode: SidebarMode
    let label: String
    let icon: String
    let shortcut: String
    let current: SidebarMode
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(label, systemImage: icon)
            if current == mode {
                Image(systemName: "checkmark")
            }
        }
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.control, .command]
        )
    }
}

// MARK: - Library Layout Section

/// Library layout selection commands (Icons, List, Table, Map)
/// Only shown for Library and Search modes
struct LibraryLayoutSection: View {
    @ObservedObject var viewSettings: ViewSettings
    @ObservedObject var featureManager = FeatureManager.shared
    @FocusedValue(\.sidebarMode) var sidebarMode

    /// Only show view options for modes that need them (Library, Search)
    private var shouldShowViewOptions: Bool {
        guard let mode = sidebarMode?.wrappedValue else { return false }
        switch mode {
        case .library, .search:
            return true
        case .chat, .workflows, .automation, .activity:
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
        return [.icons, .list, .table, .map]
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
                        label: "as Table",
                        icon: "tablecells",
                        shortcut: "3",
                        current: viewSettings.libraryLayout
                    ) {
                        viewSettings.libraryLayout = .table
                    }
                }

                if availableLayouts.contains(.map) {
                    LibraryLayoutButton(
                        layout: .map,
                        label: "as Map",
                        icon: "rectangle.3.group",
                        shortcut: "4",
                        current: viewSettings.libraryLayout
                    ) {
                        viewSettings.libraryLayout = .map
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
                        sortField?.wrappedValue = field.rawValue
                    } label: {
                        Label(field.rawValue, systemImage: field.icon)
                        if sortField?.wrappedValue == field.rawValue {
                            Image(systemName: "checkmark")
                        }
                    }
                }

                Divider()

                Button {
                    sortAscending?.wrappedValue = true
                } label: {
                    Text("Ascending")
                    if sortAscending?.wrappedValue == true {
                        Image(systemName: "checkmark")
                    }
                }

                Button {
                    sortAscending?.wrappedValue = false
                } label: {
                    Text("Descending")
                    if sortAscending?.wrappedValue == false {
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
    @ObservedObject var viewSettings: ViewSettings
    @ObservedObject var featureManager = FeatureManager.shared
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
        case .workflows, .automation, .activity:
            return []
        }
    }

    var body: some View {
        if shouldShowPreviewOptions {
            Section("Preview") {
                if availablePreviewModes.contains(.none) {
                    PreviewModeButton(
                        mode: .none,
                        label: "None",
                        icon: "square",
                        shortcut: "5",
                        current: viewSettings.previewMode
                    ) {
                        viewSettings.previewMode = .none
                    }
                }

                if availablePreviewModes.contains(.standard) {
                    PreviewModeButton(
                        mode: .standard,
                        label: "Standard",
                        icon: "rectangle.split.1x2",
                        shortcut: "6",
                        current: viewSettings.previewMode
                    ) {
                        viewSettings.previewMode = .standard
                    }
                }

                if availablePreviewModes.contains(.widescreen) {
                    PreviewModeButton(
                        mode: .widescreen,
                        label: "Widescreen",
                        icon: "rectangle.split.2x1",
                        shortcut: "7",
                        current: viewSettings.previewMode
                    ) {
                        viewSettings.previewMode = .widescreen
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

// MARK: - Inspector Button

/// Inspector show/hide command
struct InspectorButton: View {
    @ObservedObject var viewSettings: ViewSettings

    var body: some View {
        Button {
            viewSettings.showInspector.toggle()
        } label: {
            Label(
                viewSettings.showInspector ? "Hide Inspector" : "Show Inspector",
                systemImage: "sidebar.right"
            )
        }
        .keyboardShortcut("i", modifiers: [.command, .option])
    }
}

// MARK: - Show Ruler

/// Toggles the inspector's text-editor ruler globally. Lives in Format > Text
/// in spirit but attaches to the View menu (FicheroApp wires this in).
/// AppStorage key matches the editor's `editor.rulersVisible` flag.
struct ShowRulerButton: View {
    @AppStorage("editor.rulersVisible") private var rulersVisible: Bool = true

    var body: some View {
        // Toggle in a CommandMenu renders as a checkmark menu item — and
        // unlike a Button with a dynamic label, the checkmark *does* update
        // when @AppStorage changes from elsewhere (e.g. the keyboard
        // shortcut). SwiftUI Commands cache Button labels and don't reliably
        // re-evaluate them on UserDefaults change (#781 follow-up).
        Toggle(isOn: $rulersVisible) {
            Label("Show Ruler", systemImage: "ruler")
        }
        .keyboardShortcut("r", modifiers: [.command, .control])
    }
}

/// Triggers the focused artifact panel's NSTextView inline find bar.
/// `usesFindBar = true` is already set in AttributedTextEditor, so AppKit
/// renders the bar across the top of that one editor — no app-wide search.
struct ShowFindBarButton: View {
    var body: some View {
        Button {
            let item = NSMenuItem()
            item.tag = Int(NSFindPanelAction.showFindPanel.rawValue)
            NSApp.sendAction(
                Selector(("performFindPanelAction:")),
                to: nil,
                from: item
            )
        } label: {
            Label("Find in Artifact", systemImage: "magnifyingglass")
        }
        .keyboardShortcut("f", modifiers: .command)
    }
}
