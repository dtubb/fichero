import SwiftUI
// swiftlint:disable file_length

// MARK: - ReadingPaneView

// swiftlint:disable type_body_length
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

    @Environment(APIClient.self) private var apiClient
    @Environment(KGFocusState.self) private var kgFocusState
    @Environment(ClaimFocusState.self) private var claimFocusState
    @Environment(AnnotationStore.self) private var annotationStore
    @Environment(\.splitAxisActions) private var splitAxisActions
    /// Shared annotation focus for the Notes tab's list ↔ detail selection.
    @State private var focusedAnnotation = FocusedAnnotation.shared

    @State private var isPinned = false
    @State private var pinnedDocument: Document?
    @State private var pinnedActivePageNumber: Int?
    @State private var pinnedPageCount: Int?
    @State private var webZoom: Double = 1.0
    // The KG surface sub-mode. Defaults to Graph — transcript moved to the Page
    // tab, so the Knowledge surface opens on a "what we know" view.
    @State private var activeTab: KGSurfaceTab = .graph
    /// The reader's top-level tab (Page/Knowledge/Notes) — the reader IA fold
    /// (2026-07-11 design). Per-window via @SceneStorage. Defaults to Page: the
    /// reader reads the source first (Daniel 2026-07-12); Knowledge and Notes
    /// are secondary top tabs.
    @SceneStorage("reader.topTab") private var readerTabRaw = ReaderTab.page.rawValue
    private var readerTab: ReaderTab { ReaderTab(rawValue: readerTabRaw) ?? .page }
    private var readerTabBinding: Binding<ReaderTab> {
        Binding(get: { readerTab }, set: { readerTabRaw = $0.rawValue })
    }
    /// Page-tab layout: source / split / transcript (#3502). Per-window.
    @SceneStorage("reader.page.layout") private var pageLayoutRaw = ReaderPageLayout.source.rawValue
    private var pageLayout: ReaderPageLayout { ReaderPageLayout(rawValue: pageLayoutRaw) ?? .source }
    private var pageLayoutBinding: Binding<ReaderPageLayout> {
        Binding(get: { pageLayout }, set: { pageLayoutRaw = $0.rawValue })
    }
    /// Page-turn animation for image-sequence navigation in the Page tab (#2485).
    /// Shares the reader.pageTurnAnimated key with the immersive reader so the
    /// setting is unified; reduce-motion falls back to a crossfade.
    @AppStorage("reader.pageTurnAnimated") private var pageTurnAnimated = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// Direction of the last page change, tracked from the page sequence so the
    /// image swap curls the right way.
    @State private var pageTurnForward = true

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
            // Native top tabs (Page/Knowledge/Notes) — fixed chrome over the
            // WebKit/native content beneath (reader IA fold, 2026-07-11).
            ReaderTabBar(selection: readerTabBinding)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
            Divider()

            readerTabContent

            PaneFilterBar { Spacer(minLength: 0) }

            // Bottom-anchored mini-toolbar (#3060 / #2670): close/title/zoom/pin
            // now sit at the bottom, matching every other pane bar.
            // Layout: [× close] [icon] [title] [spacer] | [split buttons] [pin]
            Divider()
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

    /// Routes the selected reader tab to its content, native chrome over the
    /// WebKit/native surfaces (reader IA fold). Page = read the source (image /
    /// PDF with loupe #2419 / transcript); Knowledge = the WebKit KG surface;
    /// Notes = the reading layer (highlights/notes/bookmarks).
    @ViewBuilder
    private var readerTabContent: some View {
        switch readerTab {
        case .page:
            pageTabContent
        case .knowledge:
            knowledgeTabContent
        case .notes:
            notesTabContent
        }
    }

    /// Knowledge tab — explore what we know. A native sub-mode switcher for the
    /// exploration views (Graph, Claims, Timeline, Map — Timeline/Map are
    /// sub-modes, not top tabs, #3504) sits alongside a set-apart **Digest**
    /// section (the AI summary), so the digest reads as a distinct section rather
    /// than a co-equal sub-mode or its own tab (#3505/#3512, design Q1).
    /// Transcript is excluded — it lives in the Page tab. The surface is the
    /// shared `DocumentKGSurface` WebKit view, driven by `activeTab`.
    @ViewBuilder
    private var knowledgeTabContent: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Picker("Knowledge view", selection: knowledgeVizBinding) {
                    ForEach(Self.knowledgeVizModes) { mode in
                        Label(mode.title, systemImage: mode.icon)
                            .help(mode.helpText)
                            .tag(mode as KGSurfaceTab?)
                    }
                }
                .pickerStyle(.segmented)
                .labelStyle(.iconOnly)
                .fixedSize()
                .accessibilityIdentifier("readerKnowledgeSubMode")

                Spacer(minLength: 8)

                // Digest is the AI summary SECTION, set apart from the
                // exploration sub-modes (design Q1 / #3512).
                Divider().frame(height: 16)
                Button {
                    activeTab = .digest
                } label: {
                    Label(KGSurfaceTab.digest.title, systemImage: KGSurfaceTab.digest.icon)
                }
                .buttonStyle(.borderless)
                .labelStyle(.titleAndIcon)
                .font(.caption)
                .foregroundStyle(activeTab == .digest ? Color.accentColor : .secondary)
                .help(KGSurfaceTab.digest.helpText)
                .accessibilityIdentifier("readerKnowledgeDigest")
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)

            Divider()

            surfaceView
        }
    }

    /// The KG exploration sub-modes in the Knowledge tab. Transcript is a Page
    /// concern; Digest is a separate section (below). Graph/Claims/Timeline/Map
    /// are the "what we know" visualization views.
    private static let knowledgeVizModes: [KGSurfaceTab] = [.graph, .claims, .timeline, .map]

    /// Binds the exploration sub-mode picker to `activeTab`. When the Digest
    /// section is active (`activeTab == .digest`) the selection is nil so no viz
    /// segment is highlighted; any stale non-knowledge value clamps to Graph.
    private var knowledgeVizBinding: Binding<KGSurfaceTab?> {
        Binding(
            get: {
                if Self.knowledgeVizModes.contains(activeTab) { return activeTab }
                return activeTab == .digest ? nil : .graph
            },
            set: { if let mode = $0 { activeTab = mode } }
        )
    }

    /// The KG tab actually shown: a valid viz sub-mode or the digest section;
    /// anything else (e.g. a stale `.transcript`) falls back to Graph.
    private var effectiveKnowledgeTab: KGSurfaceTab {
        (Self.knowledgeVizModes.contains(activeTab) || activeTab == .digest) ? activeTab : .graph
    }

    /// Page tab — read the source. A source/split/transcript toggle (#3502) lays
    /// out the page image and its transcript alone or side by side. The source is
    /// a PDF page in the native `PDFPageWithToolbar` (bottom loupe #2419 + page
    /// nav) or an image via `DocumentCanvas` (storage HTTP, never a local path);
    /// the transcript is the annotatable `PageContentPane`.
    @ViewBuilder
    private var pageTabContent: some View {
        if let doc = effectiveDocument {
            VStack(spacing: 0) {
                Picker("Page layout", selection: pageLayoutBinding) {  // #3502
                    ForEach(ReaderPageLayout.allCases) { layout in
                        Label(layout.title, systemImage: layout.icon)
                            .help(layout.help)
                            .tag(layout)
                    }
                }
                .pickerStyle(.segmented)
                .labelStyle(.iconOnly)
                .fixedSize()
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .accessibilityIdentifier("readerPageLayout")

                Divider()

                switch pageLayout {
                case .source:
                    pageSource(for: doc)
                case .transcript:
                    PageContentPane(document: doc)
                case .split:
                    HStack(spacing: 0) {
                        pageSource(for: doc)
                            .frame(maxWidth: .infinity)
                        Divider()
                        PageContentPane(document: doc)
                            .frame(width: 320)
                    }
                }
            }
            // Track page-turn direction from the sequence so the image swap
            // curls the right way (#2485).
            .onChange(of: doc.sequence ?? -1) { oldSeq, newSeq in
                if oldSeq != -1, newSeq != -1 { pageTurnForward = newSeq >= oldSeq }
            }
        } else {
            readerEmptyState
        }
    }

    /// The page's source rendering: a PDF page (loupe #2419 + page nav via
    /// `PDFPageWithToolbar`), an image (`DocumentCanvas`, storage HTTP), or the
    /// transcript as a last resort for text-only documents.
    ///
    /// The page-turn (#2485) rides only the image branch: each image page is its
    /// own document, so an id-swap animates cleanly. PDFs page *inside*
    /// `PDFPageWithToolbar` (PDFKit owns rendering) — forcing an id-swap there
    /// would reload the whole PDF each turn, so it keeps stable identity.
    @ViewBuilder
    private func pageSource(for doc: Document) -> some View {
        if doc.docType == .page, let parentId = doc.parentId {
            PDFPageWithToolbar(documentId: parentId, pageIndex: max(0, (doc.sequence ?? 1) - 1))
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if doc.fileType == .pdf {
            PDFPageWithToolbar(documentId: doc.id, pageIndex: 0)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if doc.fileType == .image {
            DocumentCanvas(content: .imageStorageDisplay(documentId: doc.id))
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .id(doc.id)
                .transition(pageTurnTransition)
                .animation(pageTurnAnimation, value: doc.id)
        } else {
            PageContentPane(document: doc)
        }
    }

    /// Notes tab — the human reading layer: highlights / notes / bookmarks
    /// anchored to the page, via the shared `AnnotationsInspectorPane`
    /// (AnnotationStore-backed, list + detail, reveal-in-source, promote-to-claim).
    /// The parent loads the document-scoped slice; the pane owns the mutations.
    @ViewBuilder
    private var notesTabContent: some View {
        if let doc = effectiveDocument {
            AnnotationsInspectorPane(
                document: doc,
                annotations: annotationStore.annotations,
                focused: focusedAnnotation
            )
            .task(id: doc.id) {
                await annotationStore.loadAnnotations(for: annotationScope(for: doc), force: true)
            }
        } else {
            readerEmptyState
        }
    }

    /// Annotation scope for the focused document — page / folder / document.
    private func annotationScope(for doc: Document) -> AnnotationScope {
        switch doc.docType {
        case .folder: return .folder(doc.id)
        case .page: return .page(doc.id)
        default: return .document(doc.id)
        }
    }

    /// Page-turn transition for the Page tab's image navigation (#2485). Off ⇒
    /// no transition; reduce-motion ⇒ crossfade; otherwise the 3D page-turn.
    private var pageTurnTransition: AnyTransition {
        guard pageTurnAnimated else { return .identity }
        guard !reduceMotion else { return .opacity }
        return .pageTurn(forward: pageTurnForward)
    }

    private var pageTurnAnimation: Animation? {
        guard pageTurnAnimated else { return nil }
        return .easeInOut(duration: reduceMotion ? 0.2 : 0.45)
    }

    private var readerEmptyState: some View {
        Text("No selection")
            .font(.callout)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
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
                externalActiveTab: effectiveKnowledgeTab,
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
// swiftlint:enable type_body_length

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
        .environment(savedSearchService)
        .environment(conversationService)
        .environment(ErrorService.shared)
        .environment(performanceService)
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
        // Was the publish point for the View menu's 3D "Space" (.realitykit)
        // button via @FocusedValue; that button and its FocusedValues were
        // retired with the Mind Palace renderer. Now a plain passthrough — the
        // toolbar picker drives viewDisplayMode directly.
        contentView
    }

    @ViewBuilder
    var centerContent: some View {
        // Clickable location breadcrumb pinned above the content (#1928). The bar
        // renders nothing at the Library root, so this inset is invisible there.
        centerContentRouting
            .safeAreaInset(edge: .top, spacing: 0) { breadcrumbBar }
    }

    @ViewBuilder
    private var centerContentRouting: some View {
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
                            // The library pane must never paint past its own split
                            // column — otherwise list/grid rows can bleed under the
                            // shell sidebar or off the left window edge.
                            .clipped()
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
        // Keep every library/preview/reader combination inside the detail
        // column bounds. Without this outer clip, inner split panes can still
        // paint under the shell sidebar or past the left window edge (#3336).
        .clipped()
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
        CompactShellPolicy.route(
            horizontalSizeClass: horizontalSizeClass,
            appViewMode: viewMode,
            isEntitySelection: isEntityLibrarySelection
        ) == .libraryReader
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

    /// Compact (iPhone) list→detail stack for the inner-sidebar modes
    /// (Research / Workflow / Activity, #3010). Mirrors `compactLibraryReaderStack`:
    /// the mode's list is the `NavigationStack` root and selecting an item pushes
    /// its detail; `Back` (or a nil `selection`) pops to the list. Compact-only —
    /// regular width keeps its existing two-column rail (the caller's `else`).
    /// `selection` binds the mode's own selection store, so setting it to nil pops.
    @ViewBuilder
    func compactInnerModeStack<Item: Hashable, ListContent: View, DetailContent: View>(
        title: String,
        selection: Binding<Item?>,
        @ViewBuilder list: () -> ListContent,
        @ViewBuilder detail: @escaping (Item) -> DetailContent
    ) -> some View {
        NavigationStack {
            list()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .navigationTitle(title)
                #if !os(macOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .navigationDestination(item: selection) { item in
                    detail(item)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        #if !os(macOS)
                        .navigationBarTitleDisplayMode(.inline)
                        #endif
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
                onClose: { setPaneVisible(.canvas, false) }
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
                onClose: { setPaneVisible(.reading, false) }
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
            .environment(documentStore.documentService)
            .environment(artifactService)
            .environment(entityService)
            .environment(kgCurationService)
            .environment(documentStore)
            .environment(artifactStore)
            .environment(entityStore)
            .environment(claimStore)

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
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .inspector })
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(.bar)
    }

    // MARK: - Breadcrumb

    /// Clickable Finder/Xcode-style breadcrumb for the content header (#1928):
    /// Library ▸ folder ▸ … ▸ document ▸ page. Hidden unless there's a path
    /// beyond the Library root (so it never shows an empty "Library" strip).
    @ViewBuilder
    var breadcrumbBar: some View {
        let segments = breadcrumbSegments
        if segments.count > 1 {
            HStack(spacing: 4) {
                ForEach(Array(segments.enumerated()), id: \.element.id) { index, segment in
                    if index > 0 {
                        Image(systemName: "chevron.right")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    breadcrumbSegmentLabel(segment, isLast: index == segments.count - 1)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12)
            .frame(height: 24)
            .background(.bar)
            .accessibilityIdentifier("contentBreadcrumbBar")
        }
    }

    @ViewBuilder
    private func breadcrumbSegmentLabel(_ segment: BreadcrumbBuilder.Segment, isLast: Bool) -> some View {
        // The current (last) segment is where you already are — plain text, not a
        // button. Ancestors + the Library root are clickable and navigate up.
        if segment.isNavigable && !isLast {
            Button(segment.name) { navigateToBreadcrumb(segment) }
                .buttonStyle(.plain)
                .font(.caption)
                .foregroundStyle(.secondary)
        } else {
            Text(segment.name)
                .font(.caption)
                .foregroundStyle(isLast ? .primary : .secondary)
                .lineLimit(1)
        }
    }

    /// Library ▸ folder ▸ … ▸ document ▸ page segments for the current library
    /// selection. Reuses the same parent-lookup as `breadcrumbSubtitle`.
    var breadcrumbSegments: [BreadcrumbBuilder.Segment] {
        guard case .library(let document) = viewMode else {
            return [BreadcrumbBuilder.Segment(name: "Library", documentId: nil, isRoot: true)]
        }
        let parentLookup: BreadcrumbBuilder.DocumentLookup = { parentId in
            documentStore.currentDocuments.first { $0.id == parentId }
                ?? documentStore.collections.first { $0.id == parentId }
        }
        let pageLabel: String? = if let page = activeLocationDocument, page.docType == .page {
            page.pageThumbnailLabel
        } else {
            nil
        }
        return BreadcrumbBuilder.buildSegments(
            from: document,
            parentLookup: parentLookup,
            pageLabel: pageLabel
        )
    }

    private func navigateToBreadcrumb(_ segment: BreadcrumbBuilder.Segment) {
        if segment.isRoot {
            viewMode = .library(nil)
            sidebarSelectionState.selectedItemId = nil
            detailDocument = nil
            browserSelection = []
            return
        }
        guard let documentId = segment.documentId,
              let doc = documentStore.currentDocuments.first(where: { $0.id == documentId })
                  ?? documentStore.collections.first(where: { $0.id == documentId }) else { return }
        viewMode = .library(doc)
        sidebarSelectionState.selectedItemId = "doc:\(documentId)"
        detailDocument = nil
        browserSelection = []
    }
}
