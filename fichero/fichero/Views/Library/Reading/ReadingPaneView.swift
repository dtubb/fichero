import SwiftUI
// swiftlint:disable file_length

// MARK: - ReadingPaneView

// swiftlint:disable type_body_length
/// Self-contained knowledge/WebKit reading surface with its own pin state.
/// Extracting this to a separate View (rather than inline in widescreenReadingPane)
/// gives each SplittablePane instance its own independent @State, so left and
/// right split panes can be pinned/unpinned independently.
struct ReadingPaneView: View {
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
    /// Drives the compact (iPhone) collapse of the side-by-side page split — a
    /// fixed-width transcript beside the source doesn't fit at compact width
    /// (#3666). Always `.regular` on macOS, so the desktop layout is unchanged.
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    /// Per-window source-navigation bus (#2105/#3437). A reveal brings the reader
    /// to the Page tab so the highlighted source is visible (#3521).
    @Environment(ClaimSourceNavigationState.self) private var claimSourceNavigationState: ClaimSourceNavigationState?
    /// Per-window active-surface marker (#3579). A direct click in this pane
    /// makes it active; the MiniToolbar draws an accent hairline when it is.
    @Environment(ActiveSurfaceState.self) private var activeSurfaceState: ActiveSurfaceState?
    /// Stable identity for THIS pane instance — minted once at mount, so left
    /// and right splits are tracked independently (mirrors per-instance pin).
    @State private var surfaceId = SurfaceID()
    /// Open-in-new-tab/window plumbing for the pane's title-bar context menu
    /// (#3582, browser-tab metaphor). Reuses the shared WindowOpener path.
    @Environment(\.openWindow) private var openWindow
    /// Shared annotation focus for the Notes tab's list ↔ detail selection.
    @State private var focusedAnnotation = FocusedAnnotation.shared
    /// Notes-tab sub-mode: anchored marks vs free-text notes (#3513). Per-window.
    @SceneStorage("reader.notes.mode") private var notesModeRaw = ReaderNotesMode.annotations.rawValue
    private var notesMode: ReaderNotesMode { ReaderNotesMode(rawValue: notesModeRaw) ?? .annotations }
    private var notesModeBinding: Binding<ReaderNotesMode> {
        Binding(get: { notesMode }, set: { notesModeRaw = $0.rawValue })
    }

    @State private var isPinned = false
    @State private var pinnedDocument: Document?
    @State private var pinnedActivePageNumber: Int?
    @State private var pinnedPageCount: Int?
    @State private var webZoom: Double = 1.0
    // The KG surface sub-mode. Defaults to Entities — the entities WITH the
    // statements made about them, i.e. the "what we know" reading, NOT the graph
    // visualisation (Daniel 2026-07-14, #3765 Q6).
    @State private var activeTab: KGSurfaceTab = .entities
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
            // Shared top-tab chrome (Page/Knowledge/Notes) — the same
            // SurfaceTabBar icon row the Inspector uses (#3530), fixed over the
            // WebKit/native content beneath (reader IA fold, 2026-07-11).
            SurfaceTabBar(tabs: ReaderTab.allCases, selection: readerTabBinding)
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
                    .accessibilityLabel(isInSplit ? "Close this split" : "Close reading pane")

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
                .accessibilityLabel(isPinned ? "Unpin, follow current selection" : "Pin to current document")
            })
            // Active-surface indicator (#3579): accent hairline on the toolbar
            // strip when this pane is the active one. Additive overlay — flips
            // one pane's fill, no relayout.
            .overlay(alignment: .top) {
                Rectangle()
                    .fill(isActiveSurface ? Color.accentColor : Color.clear)
                    .frame(height: 2)
            }
            // Title-bar "Open in New Tab/Window" (#3582). Right-click the reader's
            // toolbar to pop THIS document out — the browser-tab metaphor. Reuses
            // the shared OpenInMenuItems; disabled implicitly when no document.
            .contextMenu {
                if let docId = effectiveDocument?.id {
                    OpenInMenuItems(
                        openInNewTab: { openThisDocumentInNewWindow(docId, asTab: true) },
                        openInNewWindow: { openThisDocumentInNewWindow(docId, asTab: false) }
                    )
                }
            }
        }
        // A direct click anywhere in this pane makes it the active surface
        // (#3579). simultaneousGesture runs alongside PDF/WebKit hit-testing so
        // it never steals the click — same pattern as focusedPane tracking.
        .simultaneousGesture(TapGesture().onEnded { activeSurfaceState?.activate(surfaceId) })
        // Join/leave the active-surface pool (#3580). Registering when it appears
        // makes a sole pane auto-active; toggling on isPinned clears active if it
        // pointed here (pinned panes never follow selection) and hands a lone
        // survivor the active slot.
        .onAppear { activeSurfaceState?.registerUnpinned(surfaceId) }
        .onDisappear { activeSurfaceState?.unregister(surfaceId) }
        .onChange(of: isPinned) { _, pinned in
            if pinned {
                activeSurfaceState?.unregister(surfaceId)
            } else {
                activeSurfaceState?.registerUnpinned(surfaceId)
            }
        }
        // A source reveal (#2105) brings the reader to the Page tab so the
        // highlighted / scrolled-to source is actually visible (#3521).
        .onChange(of: claimSourceNavigationState?.requestID) { _, newID in
            if newID != nil { revealSourceInPageTab() }
        }
    }

    /// True when this pane instance is the window's active surface (#3579).
    private var isActiveSurface: Bool {
        activeSurfaceState?.activeSurfaceId == surfaceId
    }

    /// Open this reader's document in a native tab (`asTab`) or a new window
    /// (#3582), via the same Safari-style path library rows use.
    private func openThisDocumentInNewWindow(_ documentId: String, asTab: Bool) {
        let libraryId = LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId
        WindowOpener.open(libraryId: libraryId, documentId: documentId, asTab: asTab, using: openWindow)
    }

    /// Switch the reader to the Page tab and, if it's showing only the source,
    /// split in the transcript — so a revealed claim/entity source shows with
    /// its highlight + scroll-to-anchor. The transcript highlight and scroll
    /// come from PageContentPane observing ClaimFocusState (#3511 on appear,
    /// #3226 anchor); the PDF page scroll comes from the reveal's
    /// `.ficheroNavigateToPage`.
    private func revealSourceInPageTab() {
        if readerTab != .page { readerTabRaw = ReaderTab.page.rawValue }
        if pageLayout == .source { pageLayoutRaw = ReaderPageLayout.split.rawValue }
    }

    @ViewBuilder
    private var zoomControls: some View {
        Button { webZoom = max(0.5, webZoom - 0.1) } label: {
            Image(systemName: "minus.magnifyingglass")
        }
        .buttonStyle(.plain)
        .help("Zoom Out")
        .accessibilityLabel("Zoom out")
        .accessibilityValue("\(Int(webZoom * 100)) percent")

        Text("\(Int(webZoom * 100))%")
            .font(.caption)
            .monospacedDigit()
            .frame(width: 44)
            // Spoken as the zoom buttons' accessibilityValue; as its own element it
            // would just be a bare number with no context.
            .accessibilityHidden(true)

        Button { webZoom = min(3.0, webZoom + 0.1) } label: {
            Image(systemName: "plus.magnifyingglass")
        }
        .buttonStyle(.plain)
        .help("Zoom In")
        .accessibilityLabel("Zoom in")
        .accessibilityValue("\(Int(webZoom * 100)) percent")

        Button { webZoom = 1.0 } label: {
            Image(systemName: "1.square")
        }
        .buttonStyle(.plain)
        .help("Reset Zoom")
        .accessibilityLabel("Reset zoom to 100 percent")
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
    /// concern; Digest is a separate section (below). Entities/Claims are native
    /// lists; Graph/Timeline/Map are the WebKit visualization views (#3503).
    private static let knowledgeVizModes: [KGSurfaceTab] = [.entities, .claims, .graph, .timeline, .map]

    /// Binds the exploration sub-mode picker to `activeTab`. When the Digest
    /// section is active (`activeTab == .digest`) the selection is nil so no viz
    /// segment is highlighted; any stale non-knowledge value clamps to Entities.
    private var knowledgeVizBinding: Binding<KGSurfaceTab?> {
        Binding(
            get: {
                if Self.knowledgeVizModes.contains(activeTab) { return activeTab }
                return activeTab == .digest ? nil : .entities
            },
            set: { if let mode = $0 { activeTab = mode } }
        )
    }

    /// The KG tab actually shown: a valid viz sub-mode or the digest section;
    /// anything else (e.g. a stale `.transcript`) falls back to Entities.
    private var effectiveKnowledgeTab: KGSurfaceTab {
        (Self.knowledgeVizModes.contains(activeTab) || activeTab == .digest) ? activeTab : .entities
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
                    if horizontalSizeClass == .compact {
                        // A 320pt transcript beside the source can't fit on an
                        // iPhone (#3666) — the source would collapse to a sliver.
                        // Show the source full-width; the layout picker still
                        // offers the transcript-only view for the text.
                        pageSource(for: doc)
                            .frame(maxWidth: .infinity)
                    } else {
                        HStack(spacing: 0) {
                            pageSource(for: doc)
                                .frame(maxWidth: .infinity)
                            Divider()
                            PageContentPane(document: doc)
                                .frame(width: 320)
                        }
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

    /// Notes tab — the human reading layer. A sub-mode toggle (#3513) switches
    /// between anchored **Marks** (highlights / notes / bookmarks via the shared
    /// `AnnotationsInspectorPane`) and free-text document **Notes** (NoteStore
    /// via `DocumentNotesTab`), so both loose notes and page-anchored marks live
    /// under one tab.
    @ViewBuilder
    private var notesTabContent: some View {
        if let doc = effectiveDocument {
            VStack(spacing: 0) {
                Picker("Notes mode", selection: notesModeBinding) {
                    ForEach(ReaderNotesMode.allCases) { mode in
                        Label(mode.title, systemImage: mode.icon)
                            .help(mode.help)
                            .tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .labelStyle(.titleAndIcon)
                .fixedSize()
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .accessibilityIdentifier("readerNotesMode")

                Divider()

                switch notesMode {
                case .annotations:
                    AnnotationsInspectorPane(
                        document: doc,
                        annotations: annotationStore.annotations,
                        focused: focusedAnnotation
                    )
                    .task(id: doc.id) {
                        await annotationStore.loadAnnotations(for: annotationScope(for: doc), force: true)
                    }
                case .notes:
                    DocumentNotesTab(document: doc)
                }
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
                onTabSelected: { activeTab = $0 },
                document: doc
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
// swiftlint:enable file_length
