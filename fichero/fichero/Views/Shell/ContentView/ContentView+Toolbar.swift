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

                // Chat is a ROW pane (Daniel 2026-08-12: "there is no button
                // to turn it on and off") — fourth member of the pane group,
                // same grammar as preview/reading.
                Toggle(isOn: Binding(
                    get: { showChatPane },
                    set: { setChatPaneVisible($0) }
                )) {
                    Label("Chat Pane", systemImage: ToolbarSymbols.chatPane)
                }
                .help(showChatPane ? "Hide chat pane" : "Show chat pane")
            }

            // Summoned search (#4521, Finder-shaped): the engine-search field
            // is no longer resident chrome — this toggle reveals it in the
            // library's mini toolbar and dismisses it again (dismissal exits
            // transient-search presentation through `clearTransientSearch`,
            // #4106/S2 semantics unchanged). Its OWN item, not a fourth member
            // of the pane group: the group is the three-pane control (#4374),
            // and search is a different kind of thing.
            ToolbarItem(id: ContentToolbarID.searchToggle, placement: .automatic) {
                Toggle(isOn: Binding(
                    get: { showSearchField },
                    set: { setSearchFieldVisible($0) }
                )) {
                    Label("Search", systemImage: ToolbarSymbols.findField)
                }
                .help(showSearchField ? "Hide the search field" : "Search the library")
            }
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
    /// that moved sort and filter, so it belongs in the mini toolbar too — but
    /// it still renders from `contentPaneToolbarContent`, because the display
    /// mode is also what the reading workspace switches between. Moving it is
    /// tracked with the rest of #4374; until then it stays declared beside its
    /// one use, so the symbol and its call site cannot drift apart again.
    private var viewDisplayModeMenu: some View {
        Menu {
            // Deferred to menu-OPEN (the stall sampler attributed 217ms
            // main-thread stalls to this menu's body, 2026-08-08 night):
            // toolbar menu content is evaluated on window render, and the
            // #4575 per-folder branch JSON-decodes the folder-mode map on
            // every evaluation. Same mechanism as the row context menus
            // (#4544) — one cheap struct init per render, the real work at
            // open time.
            SidebarDeferredMenuContent {
                ForEach(availableViewDisplayModes) { mode in
                    Button {
                        updateViewDisplayMode(mode)
                    } label: {
                        Label(mode.label, systemImage: mode.icon)
                    }
                }
                // NO per-folder items (Daniel's final #4575 ruling,
                // 2026-08-09: the mode never changes with the folder —
                // "confusing to have things jumping around"). The mode is one
                // choice per window; the restore in
                // handleSidebarSelectionChange is gone with this menu.
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
            ToolbarItem(id: ContentToolbarID.breadcrumb, placement: .principal) {
                let libraryName: String? = {
                    guard case .library(let doc) = viewMode, doc != nil else { return nil }
                    return LibraryManager.shared.getLibrary(id: windowState.libraryId)?.displayName
                }()

                HStack(spacing: 10) {
                    HStack(spacing: 4) {
                        if let libraryName {
                            HStack(spacing: 3) {
                                Image(systemName: ToolbarSymbols.breadcrumbLibrary)
                                    .imageScale(.small)
                                Text(libraryName)
                                    .font(.subheadline)
                                    .lineLimit(1)
                                    .layoutPriority(1)
                                    // Middle-truncate (Daniel #176): a long
                                    // name must never push toolbar icons out.
                                    .truncationMode(.middle)
                                    .frame(maxWidth: 200)
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
                                // The NAME wins the space fight (#184: 'I…ox'
                                // — the title was crushed to four characters
                                // while the island had room to spare).
                                .layoutPriority(2)
                                // CAPPED + middle-truncated (Daniel #176, live:
                                // a 70-char archival folder name swallowed the
                                // whole toolbar and the trailing icons with
                                // it). An ellipsis mid-name loses the least —
                                // archival names front-load the year and
                                // back-load the distinguishing tail.
                                // ponytail: fixed cap; a window-relative cap
                                // needs GeometryReader plumbing into toolbar
                                // content — upgrade if 380pt misfits a size.
                                .truncationMode(.middle)
                                .frame(maxWidth: 460)
                        }
                        .foregroundStyle(.primary)
                    }
                    // HUG the content (Daniel, 2026-08-10 #220: "this is too
                    // wide the island… spacing between icons and chevron and
                    // next is too much"): the per-text maxWidth caps (#176)
                    // are EXPANDING frames under the toolbar's generous
                    // proposal, so short names centered in wide frames read
                    // as giant gaps. fixedSize proposes nil width, which
                    // makes every frame(maxWidth:) hug its text (still
                    // capped and middle-truncated for long names), and the
                    // island shrinks to what it actually says. The edge
                    // padding gives the leading icon room from the capsule.
                    .fixedSize(horizontal: true, vertical: false)
                    .padding(.horizontal, 6)
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
                        selectionCount: browserSelection.count,
                        importError: $importError
                    )
                }
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
