import SwiftUI
// swiftlint:disable file_length

// MARK: - ReadingPaneView

/// Self-contained knowledge/WebKit reading surface with its own pin state.
/// Extracting this to a separate View (rather than inline in widescreenReadingPane)
/// gives each SplittablePane instance its own independent @State, so left and
/// right split panes can be pinned/unpinned independently.
private struct ReadingPaneView: View {
    // Live values forwarded from ContentView; overridden by pin state when locked.
    let liveDocument: Document?
    let liveActivePageNumber: Int?
    let livePageCount: Int?
    let scrollSync: DocumentScrollSyncState
    let onPageSelected: (Int) -> Void
    /// Called when the user taps the × button. Omit to hide the button.
    var onClose: (() -> Void)?

    @EnvironmentObject private var apiClient: APIClient
    @Environment(KGFocusState.self) private var kgFocusState
    @EnvironmentObject private var claimFocusState: ClaimFocusState
    @Environment(\.splitAxisActions) private var splitAxisActions

    @State private var isPinned = false
    @State private var pinnedDocument: Document?
    @State private var pinnedActivePageNumber: Int?
    @State private var pinnedPageCount: Int?
    @State private var webZoom: Double = 1.0
    @State private var activeTab: KGSurfaceTab = .transcript

    private var effectiveDocument: Document? { isPinned ? pinnedDocument : liveDocument }
    private var effectivePageNumber: Int? { isPinned ? pinnedActivePageNumber : liveActivePageNumber }
    private var effectivePageCount: Int? { isPinned ? pinnedPageCount : livePageCount }

    /// X button: collapses the active split when inside one,
    /// otherwise calls onClose to hide the whole reading pane.
    private func closePane() {
        if let actions = splitAxisActions, actions.hasHorizontal || actions.hasVertical {
            // Collapse the active axis one pane at a time so 3 -> 2 -> 1.
            actions.onCollapseSplit()
            return
        }
        onClose?()
    }

    var body: some View {
        VStack(spacing: 0) {
            // Layout: [× close] [icon] [title] [spacer] | [split buttons] [pin]
            MiniToolbar(content: {
                // × close: collapses split when inside one, hides whole pane otherwise.
                let isInSplit = splitAxisActions.map { $0.hasVertical || $0.hasHorizontal } ?? false
                if onClose != nil || isInSplit {
                    Button {
                        closePane()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help(isInSplit ? "Close this split" : "Close reading pane")

                    Divider().frame(height: 16)
                }

                Image(systemName: "text.book.closed")
                    .imageScale(.small)
                    .foregroundStyle(.secondary)
                Text(effectiveDocument?.name ?? "Views")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                // The view switcher (Transcript/Digest/Graph/Claims/Timeline/
                // Map) is NOT a row of icons in this mini-toolbar anymore
                // (#2432). The mini-toolbar carries reader ACTIONS only (zoom).
                // Representation switching lives in the main window toolbar /
                // View menu, driven by the `documentRepresentation` focused
                // value that `DocumentKGSurface` publishes — `activeTab` below
                // is updated through that path.

                Spacer(minLength: 0)

                ViewThatFits(in: .horizontal) {
                    zoomControls
                    zoomMenu
                }

                Spacer(minLength: 0)
            }, trailing: {
                // Pin — far right, after split buttons.
                Divider().frame(height: 16)

                Button {
                    if isPinned {
                        isPinned = false
                    } else {
                        pinnedDocument = liveDocument
                        pinnedActivePageNumber = liveActivePageNumber
                        pinnedPageCount = livePageCount
                        isPinned = true
                    }
                } label: {
                    Image(systemName: isPinned ? "pin.fill" : "pin")
                        .font(.system(size: 11))
                }
                .buttonStyle(.plain)
                .foregroundStyle(isPinned ? Color.accentColor : Color.secondary)
                .help(isPinned ? "Unpin — follow current selection" : "Pin to current document")
            })

            surfaceView

            PaneFilterBar { Spacer(minLength: 0) }
        }
    }

    @ViewBuilder
    private var zoomControls: some View {
        Button { webZoom = max(0.5, webZoom - 0.1) } label: {
            Image(systemName: "minus.magnifyingglass")
        }
        .buttonStyle(.plain)
        .help("Zoom Out")

        Text("\(Int(webZoom * 100))%")
            .font(.caption)
            .monospacedDigit()
            .frame(width: 44)

        Button { webZoom = min(3.0, webZoom + 0.1) } label: {
            Image(systemName: "plus.magnifyingglass")
        }
        .buttonStyle(.plain)
        .help("Zoom In")

        Button { webZoom = 1.0 } label: {
            Image(systemName: "1.square")
        }
        .buttonStyle(.plain)
        .help("Reset Zoom")
    }

    @ViewBuilder
    private var zoomMenu: some View {
        Menu {
            Button("Zoom Out") {
                webZoom = max(0.5, webZoom - 0.1)
            }
            Button("Zoom In") {
                webZoom = min(3.0, webZoom + 0.1)
            }
            Button("Reset Zoom") {
                webZoom = 1.0
            }
        } label: {
            Label("Zoom", systemImage: "magnifyingglass")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
    }

    @ViewBuilder
    private var surfaceView: some View {
        if let doc = effectiveDocument,
           let libraryPath = apiClient.currentLibraryPath, !libraryPath.isEmpty {
            let kgDocId = (doc.docType == .page && doc.parentId != nil) ? doc.parentId! : doc.id
            DocumentKGSurface(
                documentId: kgDocId,
                documentScope: doc.docType == .page ? .page : .folder,
                libraryPath: libraryPath,
                selectedEntityId: kgFocusState.focusedEntityId,
                selectedClaimId: kgFocusState.focusedClaimId ?? claimFocusState.selectedClaimId,
                activePageNumber: effectivePageNumber,
                pageCount: effectivePageCount,
                onPageSelected: isPinned ? { _ in } : onPageSelected,
                scrollSync: scrollSync,
                zoom: webZoom,
                externalActiveTab: activeTab,
                onTabSelected: { activeTab = $0 }
            )
        } else {
            Text("No selection")
                .font(.callout)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(.textBackgroundColor))
        }
    }
}

// MARK: - ContentView View Builders Extension
// Agent: ViewBuilderAgent
// Responsibility: Complex view builders for sidebar, content, preview, inspector

extension ContentView {
    private var clampedWidescreenContentPaneWidth: CGFloat {
        CGFloat(min(max(widescreenContentPaneWidth, ContentView.contentListMinWidth), 900))
    }

    var effectiveCenterIdealWidth: Double {
        // .inspector() is now a sibling of NavigationSplitView, not nested inside the detail
        // column. The split view gets whatever width the inspector leaves, so the content
        // ideal is the same whether the inspector is shown or hidden.
        max(contentWidth, 600)
    }

    // MARK: - Pane Focus Indicator

    /// Returns a view that shows an accent-colored border when the given pane has keyboard focus,
    /// then fades out after a brief moment (like Tinderbox's focus highlight).
    func paneFocusIndicator(for pane: PaneFocus) -> some View {
        FadingFocusBorder(isActive: focusedPane == pane)
            .allowsHitTesting(false)
    }

    // MARK: - Sidebar

    @ViewBuilder
    var sidebarContent: some View {
        SidebarView(
            sidebarMode: $sidebarMode,
            viewMode: $viewMode,
            selectionState: sidebarSelectionState,
            libraryManager: LibraryManager.shared,
            itemRegistry: itemRegistry,
            apiClient: apiClient,
            windowPersistenceId: sidebarWindowPersistenceId,
            onOpenChatWithCurrentScope: {
                openChatWithCurrentScope()
            }
        )
        .environmentObject(savedSearchService)
        .environmentObject(conversationService)
        .environmentObject(ErrorService.shared)
        .environmentObject(performanceService)
        .overlay { paneFocusIndicator(for: .sidebar) }
        // Make the sidebar focusable so arrow keys navigate the List.
        // (Removing this broke arrow-key navigation — see #560.)
        .focusable()
        .focused($focusedPane, equals: .sidebar)
        .focusEffectDisabled()
        // Track the column's live rendered width so each mode's @AppStorage
        // ideal is updated when the user drags the divider. The GeometryReader
        // fires on every layout pass — guard with a min-delta to avoid writing
        // on every pixel during animation.
        .background(
            GeometryReader { geo in
                Color.clear
                    .onChange(of: geo.size.width) { _, newWidth in
                        guard newWidth > 0, abs(newWidth - sidebarWidth) > 2 else { return }
                        sidebarWidth = newWidth
                    }
            }
        )
        // min: 180 lets the sidebar collapse tight enough that the mode
        // icons dominate the column with minimal wasted space (#615).
        // Was 250 — felt bloated on small screens.
        //
        .navigationSplitViewColumnWidth(
            min: ContentView.sidebarMinWidth,
            ideal: sidebarWidth,
            max: 600
        )
        .focusedSceneValue(\.sidebarMode, $sidebarMode)
        // NOTE: \.showInspector is published from the detail column in
        // ContentView.navigationSplitColumn (always present), NOT here — the
        // sidebar leaves the hierarchy when collapsed, which disabled ⌘⌥I
        // and the View-menu toggle while the sidebar was hidden (#1513).
        .focusedSceneValue(\.navigateToParentAction, FocusedLibraryAction(isEnabled: true, run: navigateToParent))
    }

    // MARK: - Center Content (with Layout Modes)

    // The library/search view-mode icon rail (`horizontalModeStrip`) that used
    // to sit at the top of the content column was removed (#2032): presentation
    // controls live in the View menu (ViewMenuCommands.LibraryLayoutSection,
    // ⌘1–4), not in a floating in-content icon bar. The mode-switch state is
    // unchanged — the View menu still drives `viewSettings.libraryLayout`.
    @ViewBuilder
    var contentWithOptionalModeRail: some View {
        contentView
            // Publish viewDisplayMode + available modes so the View menu's
            // SpatialViewSection can read/write them via @FocusedValue.
            // (#2032 regression: the old icon rail was the only entry point
            // for .realitykit/.spatial; this restores menu-driven access.)
            .focusedSceneValue(\.libraryDisplayMode, $viewDisplayMode)
            .focusedSceneValue(\.availableLibraryDisplayModes, availableViewDisplayModes)
    }

    @ViewBuilder
    var centerContent: some View {
        // COMPACT (iPhone/iOS) — Overcast-style forward navigation (#2551).
        // The library/search LIST is the root of a NavigationStack; tapping a
        // leaf document PUSHES the reader (the SAME EditorView the regular
        // content pane shows in its preview slot) with a Back button to return.
        // The macOS/iPad-regular split path is the `else` chain below and is
        // UNCHANGED — `usesCompactReaderFlow` is compile-time `false` on macOS
        // (shouldUseCompactNavigationFlow) and only ever true at compact width.
        if usesCompactReaderFlow {
            compactLibraryReaderStack
        } else if !showsPreviewPane {
            // Non-library/search modes (activity, workflows, chat, etc.) never use
            // the preview split — they own the full content area themselves.
            contentWithOptionalModeRail
                .overlay { paneFocusIndicator(for: .content) }
                .frame(maxWidth: .infinity)
        } else {
            // Folders now show the current layout so the WebKit/reading
            // pane remains visible for folder-level aggregate content (#1405).
            let layout: LayoutMode = currentLayoutMode
            // Group + .animation gives SwiftUI a stable outer identity so the
            // first .none → .standard/.widescreen transition (when the user
            // first activates a doc from full-grid) animates smoothly instead
            // of remounting + flashing every grid cell. (#770/#778 follow-up)
            Group {
                switch layout {
                case .none:
                    if showDocumentGrid {
                        contentWithOptionalModeRail
                            .overlay { paneFocusIndicator(for: .content) }
                            .frame(maxWidth: .infinity)
                    } else {
                        // Grid hidden (#616): show only the preview/editor at full width.
                        previewView
                            .overlay { paneFocusIndicator(for: .preview) }
                            .frame(maxWidth: .infinity)
                    }

                case .standard:
                    if showDocumentGrid {
                        PlatformVSplitView {
                            contentWithOptionalModeRail
                                .overlay { paneFocusIndicator(for: .content) }
                                .frame(minHeight: 150, idealHeight: 180)

                            previewView
                                .overlay { paneFocusIndicator(for: .preview) }
                                .frame(minHeight: 400, idealHeight: 720)
                        }
                        .frame(maxWidth: .infinity)
                    } else {
                        previewView
                            .overlay { paneFocusIndicator(for: .preview) }
                            .frame(maxWidth: .infinity)
                    }

                case .widescreen:
                    // Library/list, document canvas, and reading/WebKit are
                    // independently toggleable per-window (#1448). Hiding the
                    // Library pane must not collapse the reading workspace into
                    // a different single-preview layout.
                    let panePlan = adaptiveWidescreenPanePlan
                    HStack(spacing: 0) {
                        if panePlan.showsLibraryPane {
                            // When both reading panes are hidden the list takes the
                            // whole width instead of staying a fixed column with a
                            // blank grey area beside it (#1516). list-only is a valid
                            // state — the library list is the always-present spine.
                            // list-only is full-width. `width: .infinity` is an invalid
                            // frame dimension (SwiftUI logs "Invalid frame dimension
                            // (negative or non-finite)" #2006) — flex with maxWidth
                            // instead, and pin a fixed width only when a reading pane
                            // shares the row.
                            let widescreenContentFixedWidth: CGFloat? =
                                (panePlan.showsCanvasPane || panePlan.showsReadingPane)
                                    ? clampedWidescreenContentPaneWidth : nil
                            // Splittable (h/v) Library list pane — #2276.
                            adaptiveSplittablePane(storageKey: "library") {
                                contentWithOptionalModeRail
                            }
                            .overlay { paneFocusIndicator(for: .content) }
                            .frame(width: widescreenContentFixedWidth)
                            .frame(maxWidth: widescreenContentFixedWidth == nil ? .infinity : nil)
                        }

                        if panePlan.showsLibraryDivider {
                            ResizableDivider(
                                width: $widescreenContentPaneWidth,
                                minWidth: ContentView.contentListMinWidth,
                                maxWidth: 900,
                                edge: .leading
                            )
                        }

                        if panePlan.showsCanvasPane {
                            widescreenCanvasPane

                            if panePlan.showsCanvasReadingDivider {
                                ResizableDivider(
                                    width: $pageContentPaneWidth,
                                    minWidth: ContentView.readingPaneMinWidth,
                                    maxWidth: 900,
                                    edge: .trailing
                                )
                                widescreenReadingPane
                                    .frame(width: CGFloat(pageContentPaneWidth))
                            }
                        } else if panePlan.showsReadingPane {
                            widescreenReadingPane
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .animation(.easeInOut(duration: 0.18), value: layout)
        }
    }

    @ViewBuilder
    var detailShellColumn: some View {
        VStack(spacing: 0) {
            // Xcode-style detail chrome (tab strip + location/status path bars)
            // is a regular-width affordance. At compact width (iPhone) it wastes
            // the tiny screen and doesn't fit, so it's hidden — the reader gets
            // the full height (#2811). macOS reports a regular/nil size class, so
            // the chrome always renders there.
            if horizontalSizeClass != .compact {
                detailTabStrip
                detailLocationPathBar
                Divider()
            }
            centerContent
            if horizontalSizeClass != .compact {
                detailStatusPathBar
            }
        }
        .background(Color(platformColor: .textBackgroundColor))
    }

    private var detailTabStrip: some View {
        HStack(spacing: 8) {
            Label {
                Text(toolbarTitle)
                    .font(.subheadline)
                    .lineLimit(1)
            } icon: {
                Image(systemName: toolbarIcon)
            }
            .labelStyle(.titleAndIcon)

            Spacer(minLength: 8)

            Button {
                WindowOpener.open(libraryId: windowState.libraryId, asTab: true, using: openWindow)
            } label: {
                Image(systemName: "plus")
            }
            .buttonStyle(.borderless)
            .controlSize(.small)
            .help("Open current library in new tab")
        }
        .padding(.horizontal, 10)
        .frame(height: 32)
        .background(.bar)
    }

    private var detailStatusPathBar: some View {
        VStack(spacing: 0) {
            Divider()
            HStack(spacing: 8) {
                Text(selectionStatusText)
                    .font(.caption)
                    .lineLimit(1)
                Text(selectionPathText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 10)
            .frame(height: 24)
            .background(.bar)
        }
    }

    private var detailLocationPathBar: some View {
        HStack(spacing: 6) {
            Image(systemName: "point.topleft.down.curvedto.point.bottomright.up")
                .foregroundStyle(.secondary)
            Text(selectionPathText)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10)
        .frame(height: 22)
        .background(.bar)
        .accessibilityIdentifier("detailLocationPathBar")
    }

    // MARK: - Compact (iPhone) forward navigation (#2551)

    /// True only on COMPACT width for the library/search modes that own the
    /// list → reader pipeline (#2551). macOS/iPad-regular return `false` (the
    /// split layout is used instead, untouched). The entities browser is
    /// excluded — it drives the KG focus state, not a document reader.
    private var usesCompactReaderFlow: Bool {
        guard Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) else {
            return false
        }
        switch viewMode {
        case .library:
            return !isEntityLibrarySelection
        case .search:
            return true
        default:
            return false
        }
    }

    /// Resolves the current selection to a LEAF document for the compact reader
    /// push (#2551) — never a folder, so tapping a folder still drills in place.
    /// Falls back to the current selection when no promoted `detailDocument`
    /// exists (the .none/.standard promote policy is regular-width only). Resolves
    /// from the DISPLAYED `selectedDocuments` first, then `currentDocuments`, so a
    /// tap resolves even when those two momentarily disagree (#2666).
    private func compactReaderLeaf() -> Document? {
        let candidate = detailDocument
            ?? browserSelection.first.flatMap { id in
                selectedDocuments.first(where: { $0.id == id })
                    ?? documentStore.currentDocuments.first(where: { $0.id == id })
            }
        guard let doc = candidate, doc.docType != .folder else { return nil }
        return doc
    }

    /// Push the resolved leaf into `pushedReaderDocument` (#2666). Writing real
    /// @State — instead of feeding `.navigationDestination(item:)` a computed
    /// Binding — is what makes the push fire reliably on selection change.
    private func syncPushedReaderDocument() {
        let leaf = compactReaderLeaf()
        if pushedReaderDocument?.id != leaf?.id {
            pushedReaderDocument = leaf
        }
    }

    /// Compact (iPhone) library/search reader stack (#2551). The list is the
    /// root; selecting a leaf document pushes the reader — the SAME `previewView`
    /// EditorView the regular content pane shows in its preview slot, so there is
    /// no parallel reader. `NavigationStack` supplies the Back affordance.
    @ViewBuilder
    private var compactLibraryReaderStack: some View {
        NavigationStack {
            contentWithOptionalModeRail
                .overlay { paneFocusIndicator(for: .content) }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                // Title the list root so it isn't a blank bar and the pushed
                // reader's Back button names the section it returns to (#2810).
                .navigationTitle(toolbarTitle)
                #if !os(macOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                // Drive the push from real @State (#2666). Selection changes
                // recompute the leaf; popping (Back / back-swipe) sets the item
                // to nil, which clears the selection so the list returns clean.
                .navigationDestination(item: $pushedReaderDocument) { doc in
                    previewView
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .navigationTitle(doc.name)
                        #if !os(macOS)
                        // A pushed reader is a detail screen: keep the title bar
                        // compact (inline) rather than the default large title.
                        .navigationBarTitleDisplayMode(.inline)
                        #endif
                        // ponytail: full edge-swipe paging between pipeline stages
                        // is deferred. Back (NavigationStack) returns to the list,
                        // and EditorView already hosts SwipeSiblingNavigator for
                        // two/three-finger sibling paging. Add explicit
                        // stage-to-stage swiping later if Daniel wants it. (#2551)
                }
                .onChange(of: browserSelection) { _, _ in syncPushedReaderDocument() }
                .onChange(of: detailDocument) { _, _ in syncPushedReaderDocument() }
                .onChange(of: pushedReaderDocument) { _, newValue in
                    if newValue == nil {
                        detailDocument = nil
                        browserSelection = []
                    }
                }
        }
    }

    /// The document-canvas pane of the widescreen reading layout — a PDF page
    /// viewer when a PDF is active, otherwise the image/preview editor. Carries
    /// its own flexible width so it fills whatever the list/reading panes leave.
    /// Extracted so the canvas can be conditionally shown/hidden (#1448).
    @ViewBuilder
    var widescreenCanvasPane: some View {
        // Splittable (h/v) image / canvas viewer — #2276.
        adaptiveSplittablePane(storageKey: "canvas") {
            widescreenCanvasPaneContent
        }
    }

    @ViewBuilder
    private var widescreenCanvasPaneContent: some View {
        if let pdfDocumentId = detailPDFDocumentId {
            PDFPageWithToolbar(
                documentId: pdfDocumentId,
                pageIndex: selectedPageIndex,
                onPageIndexChange: { index in
                    guard documentScrollSync.beginDriving(.pdf) else { return }
                    syncGridSelectionToPDFPage(index: index)
                },
                documentTitle: detailDocument?.name,
                onClose: { showDocumentCanvas = false }
            )
            .overlay { paneFocusIndicator(for: .preview) }
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview })
            .frame(minWidth: ContentView.pdfCanvasMinWidth, maxWidth: .infinity)
        } else {
            let canvasDocument = CanvasDocumentPolicy.documentForCanvas(
                selectedDocumentIds: browserSelection,
                documents: documentStore.currentDocuments,
                detailDocument: detailDocument,
                inspectorDocument: inspectorDocument
            )
            EditorView(
                document: canvasDocument,
                showHeader: false,
                onPDFPageIndexChange: { index in
                    syncGridSelectionToPDFPage(index: index)
                },
                onNavigateToDocument: { docId in
                    selectDocument(withId: docId)
                },
                selectedDocumentIDs: browserSelection
            )
            .overlay { paneFocusIndicator(for: .preview) }
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview })
            .frame(maxWidth: .infinity)
        }
    }

    /// The reading / WebKit "Knowledge" pane of the widescreen layout.
    /// Extracted so it can be conditionally shown/hidden per-window (#1448).
    @ViewBuilder
    var widescreenReadingPane: some View {
        // Each SplittablePane instance renders ReadingPaneView independently,
        // giving left and right split panes their own @State (including pin).
        adaptiveSplittablePane(storageKey: "reading") {
            ReadingPaneView(
                liveDocument: detailDocument,
                liveActivePageNumber: detailPDFDocumentId == nil ? nil : selectedPageIndex + 1,
                livePageCount: pdfDocPages.isEmpty ? nil : pdfDocPages.count,
                scrollSync: documentScrollSync,
                onPageSelected: { index in syncGridSelectionToPDFPage(index: index) },
                onClose: { showReadingPane = false }
            )
        }
        .overlay { paneFocusIndicator(for: .reading) }
        .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .reading })
    }

    @ViewBuilder
    private func adaptiveSplittablePane<Content: View>(
        storageKey: String,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        if shouldUseSplittablePane {
            SplittablePane(storageKey: storageKey) {
                content()
            }
        } else {
            content()
        }
    }

    // MARK: - Preview View

    /// Preview/editor view for selected item
    @ViewBuilder
    var previewView: some View {
        switch viewMode {
        case .library, .search:
            // Stable .id so EditorView keeps its mount across the
            // first detailDocument nil → some-doc transition. Without
            // a fixed id, SwiftUI's structural-identity pass treats
            // the EditorView differently when its document arg flips,
            // causing the LazyVGrid sibling to re-layout / first-click
            // flash (#788).
            VStack(spacing: 0) {
                let previewDocument = CanvasDocumentPolicy.documentForCanvas(
                    selectedDocumentIds: browserSelection,
                    documents: documentStore.currentDocuments,
                    detailDocument: detailDocument,
                    inspectorDocument: inspectorDocument
                )
                if let pdfDocumentId = detailPDFDocumentId {
                    PDFReadingView(
                        document: pageFocusDocument ?? detailDocument,
                        pdfDocumentId: pdfDocumentId,
                        pageIndex: selectedPageIndex,
                        contentWidth: $pageContentPaneWidth,
                        onPageIndexChange: { index in
                            guard documentScrollSync.beginDriving(.pdf) else { return }
                            syncGridSelectionToPDFPage(index: index)
                        }
                    )
                    .id("reader.pdf")
                    .background(
                        // Two/three-finger trackpad swipe → previous/next sibling
                        // (#593). Lives behind the reader so it sees the swipe
                        // without intercepting clicks/scrolls.
                        SwipeSiblingNavigator(
                            onNavigatePrevious: navigateSiblingPrevious,
                            onNavigateNext: navigateSiblingNext
                        )
                    )
                } else {
                    EditorView(
                        document: previewDocument,
                        onPDFPageIndexChange: { index in
                            syncGridSelectionToPDFPage(index: index)
                        }
                    )
                    .id("editor.library")
                    .background(
                        // Two/three-finger trackpad swipe → previous/next sibling
                        // (#593). Lives behind the editor so it sees the swipe
                        // without intercepting clicks/scrolls.
                        SwipeSiblingNavigator(
                            onNavigatePrevious: navigateSiblingPrevious,
                            onNavigateNext: navigateSiblingNext
                        )
                    )
                }
            }

        case .chat, .comparison:
            EmptyView()

        case .workflow, .chain:
            EmptyView()

        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            EmptyView()
        }
    }

    // MARK: - Inspector View

    /// Inspector/info sidebar view (rendered inside .inspector panel)
    @ViewBuilder
    var inspectorView: some View {
        switch viewMode {
        case .library, .search:
            DocumentInspector(
                document: inspectorDocument,
                onNavigateToSource: { sourceDocId in
                    Task { @MainActor in
                        await navigateToSourcePage(sourceDocId)
                    }
                }
            )

        case .chat, .comparison:
            ChatInspector(
                selectedDocuments: $chatSelectedDocuments,
                suggestedDocumentIDs: ChatScopeBuilder.currentScopeDocumentIds(
                    browserSelection: browserSelection,
                    currentDocuments: documentStore.currentDocuments,
                    detailDocument: detailDocument
                ),
                onAddSuggestedDocuments: {
                    let scopedIds = ChatScopeBuilder.currentScopeDocumentIds(
                        browserSelection: browserSelection,
                        currentDocuments: documentStore.currentDocuments,
                        detailDocument: detailDocument
                    )
                    chatSelectedDocuments = chatSelectedDocuments.union(scopedIds)
                }
            )

        case .workflow:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )

        case .chain:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )

        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            VStack(alignment: .leading, spacing: 8) {
                Text("Inspector")
                    .font(.headline)
                Text("Select an item to inspect.")
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding()
        }
    }

    // MARK: - Detail View (Right Column)

    @ViewBuilder
    var detailView: some View {
        inspectorView
            // Focus tracking without .focusable() — avoids swallowing first click
            .overlay { paneFocusIndicator(for: .inspector) }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(.bar)
    }

    // MARK: - Breadcrumb

    @ViewBuilder
    func breadcrumbView(for doc: Document) -> some View {
        HStack(spacing: 4) {
            Text(doc.name)
                .fontWeight(.medium)
        }
    }
}
