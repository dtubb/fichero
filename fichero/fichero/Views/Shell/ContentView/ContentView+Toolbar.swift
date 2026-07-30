import SwiftUI

// MARK: - Toolbar item identity

enum ContentToolbarID {
    static let engineStatus = "fichero.engineStatus"
    static let navigationBack = "fichero.nav.back"
    static let navigationForward = "fichero.nav.forward"
    static let inspectorToggle = "fichero.inspectorToggle"
    static let compactInspectorToggle = "fichero.inspectorToggle.compact"
    static let activityStatus = "fichero.activityStatus"
    static let viewDisplayMode = "fichero.viewDisplayMode"
    /// The three pane toggles as ONE control (#4374). A group collapses as a
    /// unit under overflow instead of shedding an arbitrary pane toggle into
    /// the overflow menu, which is what a flat `.automatic` run did.
    static let paneToggleGroup = "fichero.paneToggles"
    /// Sort + filter: controls that act on the library LIST, grouped apart
    /// from the pane toggles because they are a different kind of thing.
    static let libraryControlsGroup = "fichero.library.controls"
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
        //
        // The "View" menu button used to sit here. It rendered the shared
        // view-menu commands — "choose visible panes and document views" —
        // which is the same three panes the toggles a few points away already
        // toggle, plus the display mode the adjacent menu already offers. It
        // existed so Mac matched iPad (#2493); the toggles now ship on every
        // platform, so the reason it existed has been satisfied by other means
        // (#4374). Those commands stay in the MENU BAR, which is where a
        // complete list of view commands belongs — see FicheroApp's View group.
        //
        // The test that pins this greps for the symbol, so this comment names
        // it in prose rather than in code.
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

            // ONE group, not three loose items (#4374). Six controls of three
            // different kinds used to sit in a single undifferentiated
            // `.automatic` run, so nothing told the system that these three
            // toggles are one control and the sort/filter pair is another —
            // which is why overflow shed an arbitrary pane toggle instead of
            // collapsing the set. The missing structure WAS the bug; spacing
            // was only its symptom.
            //
            // Order is the columns' own leading-to-trailing order: library
            // list (#4288, the standard Mac "hide the list, focus on reading"
            // control), then preview, then reading.
            //
            // Pane toggles are native `Toggle`s (#4360): the on-state is the
            // system's own treatment on the toolbar's Liquid Glass, so each
            // control keeps ONE position-encoded glyph. The old glyph-swap
            // grammar decayed both the library and preview toggles to the same
            // bare `rectangle` when hidden — two meanings on one symbol.
            ToolbarItemGroup(id: ContentToolbarID.paneToggleGroup, placement: .automatic) {
                libraryPaneToggleButton

                Toggle(isOn: Binding(
                    get: { showDocumentCanvas },
                    set: { setCanvasPaneVisible($0) }
                )) {
                    Label("Preview Pane", systemImage: ToolbarSymbols.previewPane)
                }
                .help(showDocumentCanvas ? "Hide preview pane" : "Show preview pane")

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
            // A SEPARATE group from the pane toggles (#4374): these act on the
            // library list's contents, not on which panes are visible, and
            // grouping them apart is what makes that legible.
            //
            // Declared unconditionally within this zone (#3163): the filter's
            // feature flag varies the item's CONTENT, it must not make the
            // toolbar item itself appear/disappear — that is the
            // duplicate-identifier crash class. The flag itself is deliberately
            // untouched here: it is OFF, not broken, and whether to enable or
            // delete it is a product decision that needs the filter bar
            // exercised first.
            ToolbarItemGroup(id: ContentToolbarID.libraryControlsGroup, placement: .automatic) {
                librarySortMenu

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
