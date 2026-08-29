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
    static let breadcrumb = "fichero.breadcrumb"
    static let modelChip = "fichero.modelChip"
    static let workflowSuggest = "fichero.workflowSuggest"
    static let searchToggle = "fichero.searchToggle"
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
        // Engine status now lives in the center status island (hosted inside
        // the `ContentToolbarID.breadcrumb` principal item, #4519) beside the
        // title, not here in the leading zone.
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

    /// TRAILING zone: the compact inspector toggle, and nothing else.
    ///
    /// Activity status lives in the centre status island (hosted inside the
    /// `ContentToolbarID.breadcrumb` principal item, #4519) beside the title, and
    /// the inspector toggle moved to the `.inspector()` panel's own toolbar so
    /// macOS places it in the inspector section rather than the content section
    /// (see `mainContentView`).
    ///
    /// The "View" menu button used to sit here. It rendered the shared
    /// view-menu commands — "choose visible panes and document views" — which
    /// is the same three panes the toggles a few points away already toggle,
    /// plus the display mode the adjacent menu already offers. It existed so
    /// Mac matched iPad (#2493); the toggles now ship on every platform, so the
    /// reason it existed has been satisfied by other means (#4374). Those
    /// commands stay in the MENU BAR, where a complete list of view commands
    /// belongs — see FicheroApp's View group. The test that pins this greps for
    /// the symbol, so this comment names it in prose rather than in code.
    ///
    /// On macOS the compact toggle is compiled out and the View menu is gone,
    /// so this zone has NOTHING left — and an empty `@ToolbarContentBuilder`
    /// body does not type-check. The whole property is therefore compiled out
    /// on macOS and its call site guarded to match, rather than kept alive by a
    /// placeholder: an `EmptyView()` filler would ship a real, invisible
    /// toolbar item, which is a worse answer than not declaring the zone.
    #if !os(macOS)
    @ToolbarContentBuilder
    var trailingToolbarContent: some ToolbarContent {
        if showInspectorToggle && !usesDockedInspector {
            ToolbarItem(id: ContentToolbarID.compactInspectorToggle, placement: .topBarTrailing) {
                inspectorToggleButton
            }
        }
    }
    #endif

    @ToolbarContentBuilder
    var contentPaneToolbarContent: some ToolbarContent {
        // The preview/reading pane toggles only make sense in the multi-pane
        // reading workspace. In the compact (iPhone) flow the reader is a single
        // navigation stack, not split panes, so the toggles do nothing and are
        // hidden (#2813).
        if supportsReadingWorkspace
            && !Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
            // The view-mode picker LEFT the toolbar (Daniel, 2026-08-23): it
            // is the library pane head's lens now (LibraryView+PaneHead).

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
            // No `id:` — `ToolbarItemGroup` has no identified initialiser, only
            // `(placement:content:)`. The group is positional; customisation
            // identity belongs to the items a user can reorder, and these three
            // move as one by construction.
            ToolbarItemGroup(placement: .automatic) {
                libraryPaneToggleButton

                Toggle(isOn: Binding(
                    get: { showDocumentCanvas },
                    set: { setCanvasPaneVisible($0) }
                )) {
                    Label("Preview", systemImage: ToolbarSymbols.previewPane)
                }
                .help(showDocumentCanvas ? "Hide the Preview" : "Show the Preview")

                Toggle(isOn: Binding(
                    get: { showReadingPane },
                    set: { setReadingPaneVisible($0) }
                )) {
                    Label("Reader", systemImage: ToolbarSymbols.readingPane)
                }
                .help(showReadingPane ? "Hide the Reader" : "Show the Reader — transcripts, translations, and the knowledge graph")

                // Chat is a ROW pane (Daniel 2026-08-12: "there is no button
                // to turn it on and off") — fourth member of the pane group,
                // same grammar as preview/reading.
                Toggle(isOn: Binding(
                    get: { showChatPane },
                    set: { setChatPaneVisible($0) }
                )) {
                    Label("Chat", systemImage: ToolbarSymbols.chatPane)
                }
                .help(showChatPane ? "Hide the Chat" : "Show the Chat")
            }

            // The resident search field MOVED to the inspector-section
            // toolbar (ContentView+InspectorContainer, 2026-08-23): Daniel
            // wants it RIGHT of the inspector toggle, and the content section
            // always renders left of the inspector section.
        }

        // Sort and filter used to sit here, outside the split-pane block, with
        // a comment explaining that "sorting and filtering a list is not a
        // split-pane concept". That special case is GONE rather than ported
        // (#4407): the controls now live in the library's own mini toolbar, so
        // they follow their pane — including in the compact flow — and there is
        // nothing left to except. See `LibraryView+MiniToolbar`.
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

    // Library sort + filter moved to `LibraryView+MiniToolbar` (#4407 /
    // #4374 finding 3): a control lives with the surface it acts on, and these
    // act on the library list, not the window.

    /// How library items are shown. This is a LIBRARY control by the same rule
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
            // ONE `.principal` item hosting the breadcrumb AND, to its right,
            // the status island (#4519). The island's #4378 home was a
            // standalone `.automatic` item — which macOS laid in the same
            // trailing run as the pane-toggle group, so status glyphs read as
            // a third and fourth toggle (#4391's ambiguity). Status is a
            // report about *what the app is doing*; the path answers *where am
            // I* — natural neighbours, and nothing like the pane controls.
            //
            // Riding INSIDE the breadcrumb item keeps `.principal` claimed by
            // exactly one identifier (two claimants is the #3163
            // duplicate-identifier crash class, per #4378), and the island
            // stays unconditionally declared — only its CONTENT varies (#3163).
            // Its message-length contract (#4366) is unchanged by the move.
            // The model a run would use, LEFT of the island (Daniel,
            // 2026-08-28: the island says what is selected, so the model
            // belongs beside it). Its own item + spacer so it gets its own
            // Liquid Glass section rather than fusing into the island capsule.
            ToolbarItem(id: ContentToolbarID.modelChip, placement: .principal) {
                ModelChipToolbarItem(prefersVision: selectionPrefersVisionModel)
            }
            ToolbarSpacer(.fixed, placement: .principal)
            ToolbarItem(id: ContentToolbarID.breadcrumb, placement: .principal) {
                // NO location breadcrumb here any more (Daniel, 2026-08-23):
                // every pane carries its own crumb, so the island answers only
                // "what is selected" (focus-tracking is a candidate addition).
                HStack(spacing: 10) {
                    // No painted lozenge (#4360): the toolbar's own Liquid Glass
                    // carries this principal item; the old low-opacity primary
                    // fill was a hand-rolled approximation of that material.
                    // Search field removed from the principal zone (#3037), and
                    // the window-level `.searchable` that replaced it is gone too
                    // (#4407) — search now lives in the library's mini toolbar,
                    // with the pane it acts on.

                    StatusIslandToolbarItem(
                        isImporting: isImporting,
                        importProgress: importProgress,
                        libraryId: windowState.libraryId,
                        libraryName: windowState.library?.displayName ?? "Library",
                        selection: StatusIslandSelection(
                            count: browserSelection.count,
                            label: inspectorDocument.map { DocumentTitle.displayName(for: $0) },
                            icon: inspectorDocument.map { PaneCrumb.icon(for: $0) },
                            noun: {
                                let ids = Set(browserSelection)
                                let docs = documentStore.currentDocuments.filter { ids.contains($0.id) }
                                guard !docs.isEmpty else { return "items" }
                                if docs.allSatisfy({ $0.fileType == .image }) { return "images" }
                                if docs.allSatisfy({ $0.docType == .page }) { return "pages" }
                                if docs.allSatisfy({ $0.docType == .folder }) { return "folders" }
                                return "items"
                            }()
                        ),
                        importError: $importError
                    )
                }
            }
            // Engine + activity are their OWN items (Daniel, 2026-08-23: the
            // island must separate from server status and activity): each gets
            // its own Liquid Glass section instead of fusing into the island's
            // capsule. ToolbarSpacer is what actually BREAKS the glass group —
            // adjacent items share one capsule without it (Daniel's 2026-08-24
            // screenshot: still fused). Unconditional, content-only variance.
            ToolbarSpacer(.fixed, placement: .principal)
            ToolbarItem(id: ContentToolbarID.workflowSuggest, placement: .principal) {
                workflowSuggestButton
            }
            ToolbarSpacer(.fixed, placement: .principal)
            ToolbarItem(id: ContentToolbarID.engineStatus, placement: .principal) {
                EngineStatusToolbarItem()
            }
            ToolbarSpacer(.fixed, placement: .principal)
            ToolbarItem(id: ContentToolbarID.activityStatus, placement: .principal) {
                ActivityStatusToolbarItem(
                    isImporting: isImporting,
                    importProgress: importProgress,
                    libraryId: windowState.libraryId,
                    libraryName: windowState.library?.displayName ?? "Library",
                    importError: $importError
                )
            }
        }
    }

    /// ONE button where four crowded (Daniel, 2026-08-29: "we don't need the
    /// select workflow button or the other two beside it"). It toggles the
    /// capability bar and wears the SAME bolt as the sidebar's Workflows
    /// section, so the icon means one thing everywhere. The old Run Workflow
    /// picker duplicated what the bar is for, and the per-selection
    /// suggestion buttons were unlabelled mystery glyphs — if suggestions
    /// return, they belong INSIDE the bar as a recommended row, not as
    /// toolbar chrome.
    @ViewBuilder
    var workflowSuggestButton: some View {
        Button {
            showWorkflowBar.toggle()
        } label: {
            Label(
                showWorkflowBar ? "Hide Workflows" : "Show Workflows",
                // The SAME glyph the sidebar's workflow rows wear
                // (SidebarItem: arrow.triangle.branch) — the bolt collided
                // with quick-run's old meaning (Daniel, 2026-08-29: "should
                // be the same as the workflows in the sidebar").
                systemImage: "arrow.triangle.branch"
            )
            .labelStyle(.iconOnly)
        }
        .help(showWorkflowBar
              ? "Hide the workflow bar"
              : "Show the workflow bar — run workflows and tools on the selection")
        .accessibilityLabel(showWorkflowBar ? "Hide workflow bar" : "Show workflow bar")
    }

    func syncFocusedDocumentSelection(_ document: Document?) {
        if let document {
            focusedDocument.select(document, libraryId: windowState.libraryId)
        } else {
            focusedDocument.clear()
        }
    }
}
