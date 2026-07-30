import SwiftUI

// MARK: - Toolbar item identity

enum ContentToolbarID {
    static let engineStatus = "fichero.engineStatus"
    static let navigationBack = "fichero.nav.back"
    static let navigationForward = "fichero.nav.forward"
    static let inspectorToggle = "fichero.inspectorToggle"
    static let compactInspectorToggle = "fichero.inspectorToggle.compact"
    static let activityStatus = "fichero.activityStatus"
    static let viewMenu = "fichero.viewMenu"
    static let viewDisplayMode = "fichero.viewDisplayMode"
    static let libraryPaneToggle = "fichero.libraryPane.toggle"
    static let previewPaneToggle = "fichero.previewPane.toggle"
    static let readingPaneToggle = "fichero.readingPane.toggle"
    static let librarySortMenu = "fichero.library.sortMenu"
    static let libraryFilterToggle = "fichero.library.filterToggle"
    static let breadcrumb = "fichero.breadcrumb"
    static let statusIsland = "fichero.statusIsland"
}

// MARK: - Toolbar Content
//
// Members called from ContentView.swift's body (contentPane/trailing/principal
// toolbar content, inspectorToggleButton, syncFocusedDocumentSelection) are
// internal, not private: `private` is FILE-scoped, and the body now lives in a
// different file. The rest stay private to this file.

extension ContentView {
    // MARK: Zoned toolbar (Mail-style)
    @ToolbarContentBuilder
    var mainToolbarContent: some ToolbarContent {
        leadingToolbarContent
    }

    /// LEADING zone: engine status + back/forward history navigation in the
    /// content-column toolbar.
    @ToolbarContentBuilder
    private var leadingToolbarContent: some ToolbarContent {
        // Engine status now lives in the center status island
        // (`ContentToolbarID.statusIsland`, principal zone) beside the title,
        // not here in the leading zone.
        ToolbarItem(id: ContentToolbarID.navigationBack, placement: .navigation) {
            Button {
                navigateBack()
            } label: {
                Label("Back", systemImage: ToolbarSymbols.navigateBack)
            }
            .help("Back (⌘')")
            .keyboardShortcut("'", modifiers: [.command])
            .disabled(!navigationHistory.canGoBack)
        }

        ToolbarItem(id: ContentToolbarID.navigationForward, placement: .navigation) {
            Button {
                navigateForward()
            } label: {
                Label("Forward", systemImage: ToolbarSymbols.navigateForward)
            }
            .help("Forward (⌘⇧')")
            .keyboardShortcut("'", modifiers: [.command, .shift])
            .disabled(!navigationHistory.canGoForward)
        }
    }

    /// TRAILING zone: activity status (#2309).
    /// The inspector toggle moved to the `.inspector()` panel's toolbar so
    /// macOS places it in the inspector section (far right) rather than the
    /// content section (see `mainContentView`).
    @ToolbarContentBuilder
    var trailingToolbarContent: some ToolbarContent {
        #if !os(macOS)
        if showInspectorToggle && !usesDockedInspector {
            ToolbarItem(id: ContentToolbarID.compactInspectorToggle, placement: .topBarTrailing) {
                inspectorToggleButton
            }
        }
        #endif

        // Activity status now lives in the center status island
        // (`ContentToolbarID.statusIsland`, principal zone) beside the title.
        // Show/hide-panes + view-mode control on every platform's toolbar,
        // including Mac (previously menu-bar only) so it matches iPad/iOS (#2493).
        ToolbarItem(id: ContentToolbarID.viewMenu, placement: .primaryAction) {
            platformViewMenuButton
        }
    }

    @ToolbarContentBuilder
    var contentPaneToolbarContent: some ToolbarContent {
        // The preview/reading pane toggles only make sense in the multi-pane
        // reading workspace. In the compact (iPhone) flow the reader is a single
        // navigation stack, not split panes, so the toggles do nothing and are
        // hidden (#2813).
        if supportsReadingWorkspace
            && !Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
            if showViewModePicker && availableViewDisplayModes.count > 1 {
                ToolbarItem(id: ContentToolbarID.viewDisplayMode, placement: .automatic) {
                    viewDisplayModeMenu
                }
            }

            // Library list pane toggle (#4288) — the standard Mac "hide the
            // list, focus on reading" control, first in the pane group because
            // the list is the leading column.
            ToolbarItem(id: ContentToolbarID.libraryPaneToggle, placement: .automatic) {
                libraryPaneToggleButton
            }

            // Pane toggles are native `Toggle`s (#4360): the on-state is the
            // system's own treatment on the toolbar's Liquid Glass, so each
            // control keeps ONE position-encoded glyph. The old glyph-swap
            // grammar decayed both the library and preview toggles to the same
            // bare `rectangle` when hidden — two meanings on one symbol.
            ToolbarItem(id: ContentToolbarID.previewPaneToggle, placement: .automatic) {
                Toggle(isOn: Binding(
                    get: { showDocumentCanvas },
                    set: { setCanvasPaneVisible($0) }
                )) {
                    Label("Preview Pane", systemImage: ToolbarSymbols.previewPane)
                }
                .help(showDocumentCanvas ? "Hide preview pane" : "Show preview pane")
            }

            ToolbarItem(id: ContentToolbarID.readingPaneToggle, placement: .automatic) {
                Toggle(isOn: Binding(
                    get: { showReadingPane },
                    set: { setReadingPaneVisible($0) }
                )) {
                    Label("Reading Pane", systemImage: ToolbarSymbols.readingPane)
                }
                .help(showReadingPane ? "Hide reading pane" : "Show reading pane")
            }
        }

        // Finder-style sort + filter for the CURRENT library view (#4289).
        // Available in the compact flow too — sorting and filtering a list is
        // not a split-pane concept — so this sits outside the block above.
        if supportsReadingWorkspace {
            ToolbarItem(id: ContentToolbarID.librarySortMenu, placement: .automatic) {
                librarySortMenu
            }

            // Declared unconditionally within this zone (#3163): the feature
            // flag varies the item's CONTENT, it must not make the toolbar item
            // itself appear/disappear — that is the duplicate-identifier crash
            // class.
            ToolbarItem(id: ContentToolbarID.libraryFilterToggle, placement: .automatic) {
                libraryFilterToggleButton
            }
        }
    }

    // MARK: Library pane toggle (#4288)

    private var libraryPaneToggleButton: some View {
        let model = LibraryPaneToggleModel(paneVisibility: paneVisibility)
        return Toggle(isOn: Binding(
            get: { model.isVisible },
            set: { newValue in
                withAnimation(FrameAnimation.snappy) {
                    setLibraryPaneVisible(newValue)
                }
            }
        )) {
            Label(model.title, systemImage: model.systemImage)
        }
        .disabled(!model.isEnabled)
        .help(model.help)
        .accessibilityLabel(model.title)
    }

    // MARK: Library sort + filter (#4289)

    /// Drives `libraryToolbarState` — the SAME sort model the View menu, the
    /// table column headers, and the per-folder `@SceneStorage` persistence in
    /// `LibraryView` already share. There is deliberately no second sort path
    /// here (#4282).
    private var librarySortMenu: some View {
        let model = libraryToolbarState.sortMenuModel
        return Menu {
            Section("Sort By") {
                ForEach(model.fields) { field in
                    Button {
                        libraryToolbarState.apply(model.selecting(field))
                    } label: {
                        Label(field.rawValue, systemImage: field.icon)
                        if model.isSelected(field) {
                            Image(systemName: "checkmark")
                        }
                    }
                    .accessibilityLabel("Sort by \(field.rawValue)")
                }
            }

            Section {
                Button {
                    libraryToolbarState.apply(model.settingAscending(true))
                } label: {
                    Label("Ascending", systemImage: "arrow.up")
                    if model.ascending {
                        Image(systemName: "checkmark")
                    }
                }

                Button {
                    libraryToolbarState.apply(model.settingAscending(false))
                } label: {
                    Label("Descending", systemImage: "arrow.down")
                    if !model.ascending {
                        Image(systemName: "checkmark")
                    }
                }
            }
        } label: {
            Label(model.label, systemImage: model.systemImage)
        }
        .help(model.help)
    }

    /// Reveals the inline per-view filter bar (the ⌘F row pinned to the bottom
    /// of the library list) — NOT the global `.searchable` field.
    @ViewBuilder
    private var libraryFilterToggleButton: some View {
        let model = LibraryFilterToggleModel(
            isAvailable: FeatureManager.shared.isLibraryFilterToolbarEnabled,
            isActive: libraryToolbarState.showFilterBar
        )
        if model.isAvailable {
            Toggle(isOn: Binding(
                get: { model.isActive },
                set: { libraryToolbarState.setFilterBar($0) }
            )) {
                Label(model.title, systemImage: model.systemImage)
            }
            .help(model.help)
            .accessibilityLabel(model.title)
        }
    }

    private var viewDisplayModeMenu: some View {
        Menu {
            ForEach(availableViewDisplayModes) { mode in
                Button {
                    updateViewDisplayMode(mode)
                } label: {
                    Label(mode.label, systemImage: mode.icon)
                }
            }
        } label: {
            Label(viewDisplayMode.label, systemImage: viewDisplayMode.icon)
        }
        .help("Choose how library items are shown")
    }

    @ViewBuilder
    private var platformViewMenuButton: some View {
        Menu {
            ViewMenuCommands()
                .environment(viewSettings)
        } label: {
            Label("View", systemImage: ToolbarSymbols.viewMenu)
        }
        .help("Choose visible panes and document views")
    }

    /// Native `Toggle` — the system's on-state on the toolbar glass replaces
    /// the old hand-rolled highlight helper (a rounded rect with a painted
    /// primary-tint fill), which was a custom approximation of exactly this
    /// treatment (#4360).
    var inspectorToggleButton: some View {
        Toggle(isOn: Binding(
            get: { showInspectorSidebar },
            set: { newValue in
                withAnimation(FrameAnimation.snappy) {
                    showInspectorSidebar = newValue
                }
            }
        )) {
            Label("Inspector", systemImage: ToolbarSymbols.inspector)
        }
        .help(showInspectorSidebar ? "Hide Inspector (⌘⌥I)" : "Show Inspector (⌘⌥I)")
    }

    /// PRINCIPAL zone: breadcrumb lozenge + scoped search (#2309/#2039).
    /// Layout: [Library Name] > [item icon + title] [search current content]
    /// The whole breadcrumb sits in a subtle rounded-rect lozenge with
    /// extra horizontal padding so it reads as a single interactive label.
    @ToolbarContentBuilder
    var principalToolbarContent: some ToolbarContent {
        // The breadcrumb lozenge + fixed 220pt search field is Mac/iPad window
        // chrome. At compact width (iPhone) it overflows the nav bar, so it's
        // dropped — the nav title carries the context and search moves to the
        // native `.searchable` field instead (#2814).
        if horizontalSizeClass != .compact {
            ToolbarItem(id: ContentToolbarID.breadcrumb, placement: .principal) {
                let libraryName: String? = {
                guard case .library(let doc) = viewMode, doc != nil else { return nil }
                return LibraryManager.shared.getLibrary(id: windowState.libraryId)?.displayName
            }()

            HStack(spacing: 4) {
                HStack(spacing: 4) {
                    if let libraryName {
                        HStack(spacing: 3) {
                            Image(systemName: ToolbarSymbols.breadcrumbLibrary)
                                .imageScale(.small)
                            Text(libraryName)
                                .font(.subheadline)
                        }
                        .foregroundStyle(.secondary)

                        // Compact chevron so the separator can't be read as the
                        // Forward button's `chevron.forward` (#4360).
                        Image(systemName: ToolbarSymbols.breadcrumbSeparator)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }

                    HStack(spacing: 3) {
                        Image(systemName: toolbarIcon)
                            .imageScale(.small)
                        Text(toolbarTitle)
                            .font(.headline)
                            .lineLimit(1)
                    }
                    .foregroundStyle(.primary)
                }
                // No painted lozenge (#4360): the toolbar's own Liquid Glass
                // carries this principal item; the old low-opacity primary
                // fill was a hand-rolled approximation of that material.
                // Search field removed (#3037) — now the native `.searchable`
                // bar (ToolbarSearchableModifier).
                }
            }

            // Xcode-style status island to the RIGHT of the breadcrumb path:
            // engine button + what's-going-on message + activity button.
            // Declared unconditionally within this zone (#3163: content
            // varies, the item never appears/disappears).
            ToolbarItem(id: ContentToolbarID.statusIsland, placement: .principal) {
                StatusIslandToolbarItem(
                    isImporting: isImporting,
                    importProgress: importProgress,
                    libraryId: windowState.libraryId,
                    libraryName: windowState.library?.displayName ?? "Library",
                    importError: $importError
                )
            }
        }
    }

    func syncFocusedDocumentSelection(_ document: Document?) {
        if let document {
            focusedDocument.select(document, libraryId: windowState.libraryId)
        } else {
            focusedDocument.clear()
        }
    }
}
