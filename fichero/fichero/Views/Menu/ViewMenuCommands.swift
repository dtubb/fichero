import SwiftUI
// swiftlint:disable file_length

/// View menu commands - Sidebar modes, library layouts, preview modes, and inspector toggle
/// Extracted from FicheroApp.swift to maintain consistency with other menu command patterns
struct ViewMenuCommands: View {
    @Environment(ViewSettings.self) var viewSettings

    var body: some View {
        SidebarModeSection()

        Divider()

        LibraryLayoutSection(viewSettings: viewSettings)

        Divider()

        SortSection()

        Divider()

        PreviewModeSection(viewSettings: viewSettings)

        Divider()

        RepresentationSection()

        KnowledgeGraphViewModeSection()

        Divider()

        ImagePreviewMenuCommands()

        Divider()

        InspectorButton()

        PaneVisibilitySection()

        Divider()

        SelectionDrivenLayoutToggle()

        Divider()

        NavigateToParentButton()

        Divider()

        ShowRulerButton()

        Divider()

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

            // Research (8) + Knowledge Graph (9) menu entries. These exist in the
            // sidebar mode-icon bar but had dropped out of the View menu, so the
            // menu items + ⌃⌘8 / ⌃⌘9 shortcuts that surface the entity browser
            // (OntologyBrowser) went missing — the lost entry point in #1485.
            if featureManager.isResearchEnabled {
                SidebarModeButton(
                    mode: .research,
                    label: SidebarMode.research.label,
                    icon: SidebarMode.research.icon,
                    shortcut: SidebarMode.research.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .research
                }
            }

            if featureManager.isKnowledgeGraphEnabled {
                Divider()

                // Knowledge Graph mode — entity list + per-entity KG (OntologyBrowser).
                SidebarModeButton(
                    mode: .knowledgeGraph,
                    label: SidebarMode.knowledgeGraph.label,
                    icon: SidebarMode.knowledgeGraph.icon,
                    shortcut: SidebarMode.knowledgeGraph.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .knowledgeGraph
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
    @Bindable var viewSettings: ViewSettings
    @ObservedObject var featureManager = FeatureManager.shared
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
    @Bindable var viewSettings: ViewSettings
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
/// Daniel: "the stuff shown in the WebKit/content view are really views that can
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

// MARK: - Inspector Button

/// Inspector show/hide command.
/// Reads/writes the focused window's inspector visibility via FocusedValues so
/// the toggle is per-window, not app-wide (#1451). Defaults to "Show" when no
/// window is focused (e.g. the command is evaluated with no key window).
struct InspectorButton: View {
    @FocusedValue(\.showInspector) var showInspector

    private var isVisible: Bool {
        showInspector?.wrappedValue ?? false
    }

    var body: some View {
        Button {
            showInspector?.wrappedValue.toggle()
        } label: {
            Label(
                isVisible ? "Hide Inspector" : "Show Inspector",
                systemImage: "sidebar.right"
            )
        }
        .keyboardShortcut("i", modifiers: [.command, .option])
        .disabled(showInspector == nil)
    }
}

// MARK: - Pane Visibility Section

/// View-menu items that mirror the reading-surface pane toggles already present
/// as toolbar buttons (#1215). Each reads the focused window's pane-visibility
/// binding via FocusedValues so the command is per-window (same rationale as
/// `InspectorButton`) and stays in sync with the toolbar. A binding is only
/// published while its window is focused, so each item disables when no
/// reading-capable window is key.
struct PaneVisibilitySection: View {
    @FocusedValue(\.showDocumentGrid) private var showDocumentGrid
    @FocusedValue(\.showDocumentCanvas) private var showDocumentCanvas
    @FocusedValue(\.showReadingPane) private var showReadingPane

    var body: some View {
        Section("Panes") {
            PaneToggleButton(
                binding: showDocumentGrid,
                showLabel: "Show Library Browser",
                hideLabel: "Hide Library Browser",
                icon: "books.vertical",
                shortcut: KeyboardShortcut("g", modifiers: [.command, .shift])
            )
            PaneToggleButton(
                binding: showDocumentCanvas,
                showLabel: "Show Preview",
                hideLabel: "Hide Preview",
                icon: "doc.richtext",
                shortcut: nil
            )
            PaneToggleButton(
                binding: showReadingPane,
                showLabel: "Show Reading Pane",
                hideLabel: "Hide Reading Pane",
                icon: "text.book.closed",
                shortcut: nil
            )
            ShowMiniToolbarToggle()
        }
    }
}

/// Reusable Show/Hide pane command. Mirrors `InspectorButton`: toggles the
/// focused window's binding and disables when no window publishes it.
struct PaneToggleButton: View {
    let binding: Binding<Bool>?
    let showLabel: String
    let hideLabel: String
    let icon: String
    let shortcut: KeyboardShortcut?

    private var isVisible: Bool {
        binding?.wrappedValue ?? false
    }

    var body: some View {
        Button {
            binding?.wrappedValue.toggle()
        } label: {
            Label(isVisible ? hideLabel : showLabel, systemImage: icon)
        }
        .keyboardShortcut(shortcut)
        .disabled(binding == nil)
    }
}

// MARK: - Selection-driven Layout

/// Opt-in toggle for selection-driven layout changes. OFF by default so the
/// visible pane set is stable — selecting a folder vs a PDF shows the same
/// panes. ON restores the legacy behaviour where a folder collapses the
/// preview pane. App-wide @AppStorage, so a Toggle reflects external changes
/// (mirrors ShowRulerButton's rationale). (#1452)
struct SelectionDrivenLayoutToggle: View {
    @AppStorage("layout.followsSelection") private var layoutFollowsSelection: Bool = false

    var body: some View {
        Toggle(isOn: $layoutFollowsSelection) {
            Label("Selection Changes Layout", systemImage: "rectangle.on.rectangle")
        }
    }
}

// MARK: - Show Mini Toolbar (#2460)

/// App-wide toggle for reader mini-toolbars. Toggle in a CommandMenu renders as
/// a checkmark item that stays in sync with @AppStorage changes from any window
/// (same rationale as ShowRulerButton). Key must match MiniToolbar.toolbarVisibilityKey.
struct ShowMiniToolbarToggle: View {
    @AppStorage("fichero.ui.showMiniToolbar") private var showMiniToolbar: Bool = true

    var body: some View {
        Toggle(isOn: $showMiniToolbar) {
            Label("Show Mini Toolbar", systemImage: "rectangle.topthird.inset.filled")
        }
    }
}

// MARK: - Go Up (Cmd+`)

// Walks one level up the folder hierarchy via the focused window's
// navigateToParent action. Lets users ascend when the sidebar is hidden,
// since there's no other way to climb back out of a folder. (#786)
struct NavigateToParentButton: View {
    @FocusedValue(\.navigateToParentAction) private var action

    var body: some View {
        Button {
            action?.run()
        } label: {
            Label("Go Up", systemImage: "arrow.up.to.line.compact")
        }
        .keyboardShortcut("`", modifiers: [.command])
        .disabled(action == nil)
    }
}

/// App-wide toggle for the rich-text ruler. Keeps the menu checkmark in sync
/// with the persisted preference and forwards the actual toggle to the focused
/// text view when one exists.
struct ShowRulerButton: View {
    @AppStorage("editor.rulersVisible") private var rulersVisible: Bool = true

    private var binding: Binding<Bool> {
        Binding(
            get: { rulersVisible },
            set: { newValue in
                rulersVisible = newValue
                #if canImport(AppKit)
                NSApp.sendAction(#selector(NSTextView.toggleRuler(_:)), to: nil, from: nil)
                #endif
            }
        )
    }

    var body: some View {
        Toggle(isOn: binding) {
            Label("Show Ruler", systemImage: "ruler")
        }
    }
}

/// Triggers the focused text view's inline find bar. Targets the first
/// responder via `performFindPanelAction(_:)`, which SwiftUI's `TextEditor`
/// (AppKit-backed on macOS) handles — no app-wide search. (#2453: the editor
/// is now SwiftUI `TextEditor`, not a custom NSTextView representable.)
struct ShowFindBarButton: View {
    var body: some View {
        #if canImport(AppKit)
        Button {
            let item = NSMenuItem()
            item.tag = Int(NSFindPanelAction.showFindPanel.rawValue)
            NSApp.sendAction(
                #selector(NSTextView.performFindPanelAction(_:)),
                to: nil,
                from: item
            )
        } label: {
            Label("Find in Artifact", systemImage: "magnifyingglass")
        }
        .keyboardShortcut("f", modifiers: .command)
        #else
        Button {
        } label: {
            Label("Find in Artifact", systemImage: "magnifyingglass")
        }
        .keyboardShortcut("f", modifiers: .command)
        .disabled(true)
        #endif
    }
}
