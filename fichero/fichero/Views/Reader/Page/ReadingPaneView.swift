import SwiftUI
import UniformTypeIdentifiers

// MARK: - ReadingPaneView

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
    /// The full multi-selection, when more than one document is selected
    /// (2026-08-25: the multi view used to REPLACE this pane wholesale, so
    /// selecting three pages erased the head, the lens selector and the
    /// crumbs). With 2+ entries the Page lens renders all of them in archival
    /// order; the pane chrome is untouched.
    var multiDocuments: [Document] = []
    /// The active library-search query (Daniel, 2026-09-01). Selecting a
    /// search result must show the matched terms lit IN the reader, not just
    /// open the document. This seeds the pane's existing find-in-page state
    /// (#4338) — the same CSS Custom Highlight path the find bar drives — so
    /// there is one highlighter, not a search-specific second one. Empty
    /// outside a search; the user's own typing in the find bar always wins.
    var searchHighlightQuery: String = ""

    @Environment(APIClient.self) var apiClient
    /// THIS window's artifact service (2026-09-02): the lens loader used to
    /// resolve `LibraryManager.currentLibraryId` — the app-globally current
    /// library, not this pane's — so in a multi-library window the "Showing"
    /// artifact submenu queried the wrong library and came back empty.
    @Environment(ArtifactService.self) var paneArtifactService: ArtifactService?
    /// The existing busy-state source for per-page run progress (#4357): the
    /// store's run target record (#4295) plus the live page content it splices
    /// in mid-run (#4318). No second notion of "this document is working".
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    /// Run names for the artifact submenu's run headers, and the live
    /// completion counters that tell the menu a new run just wrote. Both
    /// optional: detached reader scenes may inject neither, and a submenu
    /// headed "Workflow Run" is degraded, not wrong.
    @Environment(WorkflowStore.self) var workflowStore: WorkflowStore?
    @Environment(WorkflowExecutionObserver.self) var executionObserver: WorkflowExecutionObserver?
    @Environment(KGFocusState.self) var kgFocusState
    @Environment(ClaimFocusState.self) var claimFocusState
    @Environment(AnnotationStore.self) var annotationStore
    @Environment(\.splitAxisActions) private var splitAxisActions
    /// Drives the compact (iPhone) collapse of the side-by-side page split — a
    /// fixed-width transcript beside the source doesn't fit at compact width
    /// (#3666). Always `.regular` on macOS, so the desktop layout is unchanged.
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
    @State var focusedAnnotation = FocusedAnnotation.shared
    /// Notes-tab sub-mode: anchored marks vs free-text notes (#3513). Per-window.
    @SceneStorage("reader.notes.mode") private var notesModeRaw = ReaderNotesMode.annotations.rawValue
    var notesMode: ReaderNotesMode { ReaderNotesMode(rawValue: notesModeRaw) ?? .annotations }
    var notesModeBinding: Binding<ReaderNotesMode> {
        Binding(get: { notesMode }, set: { notesModeRaw = $0.rawValue })
    }

    /// In-reader find (#4338): per-pane query + match navigation, driven from
    /// the shared filter bar (top on Mac, bottom on touch — #4362) and
    /// executed inside the shared WebKit surface.
    @State var searchState = ReaderSearchState()
    /// The `searchHighlightQuery` value already pushed into `searchState`, so
    /// a re-render never re-stomps a query the user has since edited or
    /// dismissed in the find bar — only an actual CHANGE of the library
    /// search re-seeds it.
    @State private var seededSearchHighlight: String = ""
    /// The reader's ARTIFACT lens (artifact-compare P1): non-nil pins this
    /// pane to one artifact's text instead of the live transcript. Per-pane
    /// state, so split readers compare two artifacts side by side.
    @State var artifactLens: ReaderArtifactLens?
    /// The shown document's artifacts, grouped BY RUN, newest run first
    /// (Daniel, 2026-09-04). Replaces the flat newest-first list: the flat one
    /// could not say which pass a row came from, and three reviews from one
    /// run read as three unrelated rows.
    @State var artifactLensGroups: [ReaderArtifactLensGroup] = []
    /// The representation the Page lens reads (Daniel, 2026-08-29): nil = the
    /// live content; a value = re-request the SAME WebKit page with
    /// `?representation=` (transcription, translation, …). Per-pane, so split
    /// readers can compare Content beside Translation.
    @State var readerRepresentation: String?
    /// Which representation types this document's scope actually HAS —
    /// artifact types present on the document or its pages. The switcher
    /// renders only these: a lens that goes nowhere is the menu lying.
    @State var readerRepresentationChoices: [String] = []
    /// The artifacts being COMPARED (Daniel, 2026-09-04). Two or more ids,
    /// the first being the baseline every other column is measured against.
    /// Empty = not comparing. Per-pane, like every other reader lens.
    @State var artifactCompareIds: [String] = []
    @State var artifactCompareColumns: [ReaderArtifactDiff.Column] = []
    @State var artifactCompareError: String?
    /// A `.md` document's text, rendered as Markdown (Daniel, 2026-09-04).
    /// nil = not a Markdown document. Rendered by `MarkdownText`, the app's
    /// ONE Markdown renderer — the chat bubbles and the preview canvas already
    /// use it, and a second implementation is a second answer to "what does
    /// this heading look like".
    @State var readerMarkdownText: String?
    /// A `.csv` document rendered as a real table (Daniel, 2026-09-04: "will
    /// a reader show csv? should our reader have a csv option, to render it
    /// properly?"). nil = not a CSV document, or its text is not honest CSV —
    /// in which case the ordinary reader shows the text, which is still true.
    @State var readerCSVHTML: String?
    /// The CSV behind the shown table representation, ready to drag out as a
    /// real file or save via the exporter (Daniel, 2026-08-29 bedtime).
    /// Non-nil only while a table representation is on screen and loaded.
    @State var readerTableExport: ReaderTableCSVExport?
    @State var isExportingTableCSV = false
    @State var isPinned = false
    @State private var pinnedDocument: Document?
    @State private var pinnedActivePageNumber: Int?
    @State private var pinnedPageCount: Int?
    @State var webZoom: Double = 1.0
    /// Pages a run has touched since this document loaded (#4357). A page stays
    /// tracked after its run finishes so the FINAL write — the one that actually
    /// lands the transcription — still reaches the reader.
    @State var trackedRunPages: Set<Int> = []
    // The KG surface sub-mode. Defaults to Entities — the entities WITH the
    // statements made about them, i.e. the "what we know" reading, NOT the graph
    // visualisation (2026-07-14, #3765 Q6).
    @State var activeTab: KGSurfaceTab = .entities
    /// The reader's top-level tab (Page/Knowledge/Notes) — the reader IA fold
    /// (2026-07-11 design). Per-PANE @State (Daniel, 2026-08-23: two split
    /// readers must switch lenses independently — @SceneStorage is per WINDOW,
    /// so one pane's change dragged its sibling). Page hosts the REAL
    /// multi-page WebKit transcript (#3765).
    /// ponytail: the lens no longer survives relaunch; per-pane persistence
    /// needs pane-identity keys, add with the saved-workspaces program.
    @State private var readerTabRaw = ReaderTab.page.rawValue
    var readerTab: ReaderTab { ReaderTab(rawValue: readerTabRaw) ?? .page }
    /// The pane head's lens — ONE user-facing value over the two internal
    /// enums (R3). Setting it writes both, so the head, the menu bar and the
    /// restored scene state cannot disagree about what is showing.
    var readerLensBinding: Binding<ReaderLens> {
        Binding(
            get: { ReaderLens.lens(for: readerTab, representation: activeTab) },
            set: { lens in
                readerTabRaw = lens.tab.rawValue
                if let representation = lens.representation { activeTab = representation }
            }
        )
    }

    var effectiveDocument: Document? { isPinned ? pinnedDocument : liveDocument }
    var effectivePageNumber: Int? { isPinned ? pinnedActivePageNumber : liveActivePageNumber }
    var effectivePageCount: Int? { isPinned ? pinnedPageCount : livePageCount }

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
            // In-reader find (#4338): the shared filter bar hosts the find
            // field — match count + prev/next drive the WebKit highlight. Its
            // edge is the component's ONE platform decision (#4362): top on the
            // Mac (controls near the head of the content), bottom on touch
            // platforms (reachability). Behaviour is identical on both edges.
            if MiniToolbarPlacement.preferredForReader == .top {
                PaneFilterBar(placement: .top) { readerFindBar }
            }

            readerTabContent
                // R1/R7: the head floats OVER the content's top edge — no grey
                // bar, content scrolls under. It replaces the Page/Knowledge/
                // Notes SurfaceTabBar: those three are lenses now, alongside
                // the five knowledge surfaces that were reachable only from the
                // menu bar (Daniel, 2026-08-23).
                // safeAreaInset, not overlay (Daniel, 2026-08-23: "first
                // row needs more margin — it's under the icons"): the first
                // row starts BELOW the head, while scrolled content still
                // passes under the glass.
                .safeAreaInset(edge: .top, spacing: 0) { paneHead }

            if MiniToolbarPlacement.preferredForReader == .bottom {
                PaneFilterBar(placement: .bottom) { readerFindBar }
            }

            // The bottom bar PERSISTS as the pane's one bottom host (Daniel,
            // 2026-08-23): find/filter live IN it (the PaneFilterBar above is
            // that bar) and future controls are added to it, never stacked as
            // a second row. The pane CHROME — close, pin, split, zoom — lives
            // in the floating PaneHead at the top.
        }
        // The #3579 active-surface hairline used to hang here: a 2pt accent
        // rectangle along the pane's top edge. GONE (Daniel, 2026-09-01: "no
        // focus or active rings anywhere"). It was the blue line reported at
        // the top of the reader pane — the AppKit focus rings suppressed below
        // were only half of it. Active-surface TRACKING stays: which pane the
        // verbs act on is real state, it just does not draw itself.
        //
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
            if newID != nil { revealInTranscript() }
        }
        // Per-page run progress (#4357): remember every page a run touches so
        // its live text keeps flowing to the reader after the run ends.
        .onChange(of: busyReaderPageNumbers) { _, busy in
            trackedRunPages = ReaderPageProgress.trackedPages(
                alreadyTracked: trackedRunPages,
                busy: busy
            )
        }
        .onChange(of: effectiveDocument?.id) { _, _ in trackedRunPages = [] }
        // Light the library search's terms in the reader (Daniel, 2026-09-01:
        // selecting a result showed the document but nothing about WHY it
        // matched). One seed per distinct query — `seededSearchHighlight`
        // guards the re-render case so a query the user has since edited or
        // dismissed in the find bar is never re-imposed on them.
        .onChange(of: searchHighlightQuery, initial: true) { _, _ in
            seedReaderHighlight()
        }
        // …and again when the document arrives, because the passage anchor is
        // latched at selection time and the pane is frequently built one frame
        // later (the `ReaderPassageFocus` case the anchor exists for).
        .onChange(of: effectiveDocument?.id, initial: true) { _, _ in
            seedReaderHighlight()
        }
        // Mandate 1, consumer 1: ONE fetch brings the anchor's whole
        // neighbourhood — the crumb chain stops losing middle ancestors the
        // moment this lands in the store's caches.
        .task(id: effectiveDocument?.id) {
            if let id = effectiveDocument?.id {
                await documentStore.loadOutline(for: id)
            }
            await loadArtifactLensChoices()
        }
        // The CSV-out chip's payload follows the representation switcher: a
        // table representation loads its newest full artifact; anything else
        // clears the chip. Doc changes re-fire via the reset in
        // loadArtifactLensChoices (readerRepresentation returns to nil).
        .task(id: readerRepresentation) { await loadReaderTableExport() }
        .task(id: artifactCompareIds) { await loadArtifactComparison() }
        .task(id: effectiveDocument?.id) { await loadReaderCSVTable() }
        .task(id: effectiveDocument?.id) { await loadReaderMarkdown() }
        // A comparison is about ONE document's artifacts; carrying it to the
        // next document would diff two texts that were never on screen together.
        .onChange(of: effectiveDocument?.id) { _, _ in stopComparingArtifacts() }
        // The artifact submenu REFRESHES when artifacts change (Daniel,
        // 2026-09-04: three transcription reviews from seconds earlier were
        // in the artifacts panel and missing from this menu). Same signal the
        // Artifacts inspector already reloads on, so the two surfaces cannot
        // disagree about what exists; the reader's current lens survives.
        .onChange(of: executionObserver?.fileCompletedCount) { _, _ in
            Task { await loadArtifactLensChoices(resetSelection: false) }
        }
        .onChange(of: executionObserver?.workflowCompletedCount) { _, _ in
            Task { await loadArtifactLensChoices(resetSelection: false) }
        }
        // Click rung for the CSV chip (sandbox-proof beside the drag): a
        // plain SwiftUI file exporter writing the same Transferable.
        .fileExporter(
            isPresented: $isExportingTableCSV,
            item: readerTableExport,
            contentTypes: [.commaSeparatedText],
            defaultFilename: readerTableExport?.filename
        ) { result in
            if case .failure(let error) = result {
                readerTableExportLogger.error(
                    "Saving the table CSV failed: \(error.localizedDescription, privacy: .public)"
                )
            }
        }
    }

    /// Open this reader's document in a native tab (`asTab`) or a new window
    /// (#3582), via the same Safari-style path library rows use.
    private func openThisDocumentInNewWindow(_ documentId: String, asTab: Bool) {
        let libraryId = LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId
        WindowOpener.open(libraryId: libraryId, documentId: documentId, asTab: asTab, using: openWindow)
    }

    /// Bring the Reader to the Page tab so a revealed claim/entity lands on the
    /// transcript, which scrolls to the page anchor (#3226). There is no longer a
    /// source layout to switch: the source is Preview's job (#3765 Q4), and the
    /// reveal drives that pane separately via `.ficheroNavigateToPage`.
    /// Seed the reader's find with the best available description of WHY this
    /// document is on screen: the matched PASSAGE when a search anchor names
    /// it, otherwise the library query's terms.
    ///
    /// The passage wins because it is more specific — "the road to Bagadó"
    /// lands on the sentence, where the bare query terms light every
    /// occurrence of a common word. It goes through find-in-page rather than
    /// through `scrollToSpan`: the reader renders the parent's ASSEMBLED
    /// transcript, so the anchor's page-relative offsets address the wrong
    /// text there, and a confidently wrong highlight over a manuscript is
    /// worse than none (`ReaderPassageAnchor.findPhrase`).
    ///
    /// `seededSearchHighlight` remembers what was seeded, so a re-render never
    /// re-imposes something the user has since edited or dismissed.
    private func seedReaderHighlight() {
        let seed = Self.readerHighlightSeed(
            anchor: ReaderPassageFocus.latest,
            documentId: effectiveDocument?.id,
            searchQuery: searchHighlightQuery
        )
        guard seed != seededSearchHighlight else { return }
        seededSearchHighlight = seed
        if seed.isEmpty {
            searchState.dismiss()
        } else {
            searchState.query = seed
            searchState.isActive = true
        }
    }

    /// Pure: what the reader's find should hold. The anchor wins ONLY when it
    /// names the document actually on screen — an anchor for another document
    /// is not a description of this one.
    static func readerHighlightSeed(
        anchor: ReaderPassageAnchor?,
        documentId: String?,
        searchQuery: String
    ) -> String {
        if let anchor, let documentId, anchor.documentId == documentId {
            let phrase = anchor.findPhrase
            if !phrase.isEmpty { return phrase }
        }
        return searchQuery
    }

    private func revealInTranscript() {
        if readerTab != .page { readerTabRaw = ReaderTab.page.rawValue }
    }

    /// Explicitly typed and extracted (2026-08-23 gate red): the combined
    /// generic inference — key-paths-as-functions + three @ViewBuilder slots +
    /// the Binding — collapsed the type checker at this call site ("failed to
    /// produce diagnostic"). Bounded sub-expressions are the LibraryWindow.body
    /// rule applied here.
    private var readerSelector: PaneKindSelector<ReaderLens> {
        PaneKindSelector(
            kindTitle: "Reader",
            kindIcon: "book",
            lenses: ReaderLens.allCases,
            lensTitle: { (lens: ReaderLens) in lens.title },
            lensIcon: { (lens: ReaderLens) in lens.icon },
            // ONE icon (Daniel, 2026-09-01). The kind glyph and the Content
            // lens glyph were two document pictures a divider apart, with the
            // breadcrumb's proxy icon a capsule away — three ways of saying
            // "a page". The kind icon now opens the lens menu itself.
            collapsesKindIntoLens: true,
            // The head SAYS what it is showing (Daniel, 2026-09-02) — the
            // glyph alone could not tell content from a translation from one
            // named artifact — and the View menu carries the "Showing"
            // submenu those choices used to need two extra head menus for.
            shownLabel: readerShownLabel,
            extraLensMenu: { self.readerShowingMenu() },
            lens: readerLensBinding
        )
    }

    private var publishedReaderLens: FocusedReaderLens {
        FocusedReaderLens(
            value: readerLensBinding.wrappedValue,
            set: { readerLensBinding.wrappedValue = $0 }
        )
    }

    /// The pane's floating head (R1/R3/R5/R7). Generic parameters SPELLED OUT
    /// and the modifier chained on a named value: the inferred form collapsed
    /// the type checker twice ("failed to produce diagnostic").
    private var paneHead: some View {
        // The head collapses splits itself; onClose is only the whole-pane
        // hide. (closePane stays for the toolbar/menu paths.)
        let closeAction = onClose
        let head = PaneHead(
            crumbs: readerCrumbs,
            onClose: closeAction,
            isPinned: readerPinBinding,
            // Crumb click = reveal that node in the sidebar, which selects it
            // through the same seam a click uses — the pane follows. The
            // jump-bar child menus read the store's children cache.
            onCrumb: { crumb in
                NotificationCenter.default.post(
                    name: .sidebarRevealDocument,
                    object: nil,
                    userInfo: ["documentId": crumb.id]
                )
            },
            crumbChildren: { crumb in
                (documentStore.outline(for: crumb.id)?.children
                    ?? documentStore.childrenCache[crumb.id]
                    ?? []).map(PaneCrumb.init)
            },
            crumbDragPayload: { crumb in
                LibraryManager.shared.currentLibraryId.flatMap {
                    paneCrumbDragPayload(crumb, store: documentStore, libraryId: $0)
                }
            },
            // The proxy icon drags the TEXT (Daniel, 2026-09-01). Ancestors
            // still drag as library items; only the leaf — the pane's proxy
            // icon — promises what the reader is actually showing.
            leafDragItemProvider: readerMarkdownProvider,
            selector: { self.readerSelector },
            // The representation and artifact-lens menus folded INTO the
            // View menu's "Showing" submenu (Daniel, 2026-09-02): the head
            // carried three menus that all changed what you were reading and
            // none of which named it. The CSV chip stays — it is an action on
            // what is shown, not another way to choose it.
            controls: {
                self.readerTableExportControl
            },
            tools: { EmptyView() }
        )
        // The menu bar shows the SAME lens list, reading this publication —
        // one binding rendered twice, never a second switch (R3).
        // Reader zoom is menu-command only (⌘+/⌘−/⌘0), on the reader's OWN
        // key (2026-08-24): sharing the preview's key meant two publishers
        // whenever both panes were mounted — the multiple-times-per-frame
        // fault survived the active-surface gating. One key, one publisher;
        // the menu prefers the preview's actions and falls back to these.
        return head
            .focusedSceneValue(\.readerLens, publishedReaderLens)
            // What File ▸ Export ▸ Markdown/Word act on (Daniel, 2026-09-03).
            // Published from the pane, so the commands are live exactly when a
            // reader is — and they name the documents the pane is SHOWING,
            // per the visible-surface selection ruling.
            .focusedSceneValue(\.readerExportTargets, readerExportTargets)
            .focusedSceneValue(\.readerZoomActions, ImageZoomActions(
                zoomIn: { webZoom = min(3.0, webZoom + 0.1) },
                zoomOut: { webZoom = max(0.5, webZoom - 0.1) },
                actualSize: { webZoom = 1.0 },
                zoomToFit: { webZoom = 1.0 },
                canZoomIn: webZoom < 3.0,
                canZoomOut: webZoom > 0.5
            ))
            // "Open in New Tab/Window" (#3582) followed the chrome up from the
            // retired bottom bar: right-click the HEAD to pop this document out.
            .contextMenu {
                if let docId = effectiveDocument?.id {
                    OpenInMenuItems(
                        openInNewTab: { openThisDocumentInNewWindow(docId, asTab: true) },
                        openInNewWindow: { openThisDocumentInNewWindow(docId, asTab: false) }
                    )
                    Divider()
                    // Export what you are reading, where you are reading it —
                    // the same two commands the File menu carries, so there is
                    // one implementation and two doors to it.
                    ReaderExportMenuItems()
                }
            }
    }

    /// The proxy icon's payload: this document's transcript as Markdown, or
    /// nil when there is nothing to promise (an unread page, a multi-selection
    /// whose leaf is a count rather than a document) — in which case the head
    /// falls back to the shared library-item drag.
    private var readerMarkdownProvider: (() -> NSItemProvider)? {
        guard multiDocuments.count <= 1,
              let document = effectiveDocument,
              let text = document.pageContent,
              let provider = ReaderMarkdownDrag.itemProvider(
                  text: text,
                  documentName: document.name,
                  identity: readerProxyIdentity(for: document, text: text)
              )
        else { return nil }
        return { provider }
    }

    /// WHO the proxy icon is dragging — the in-app half of the payload
    /// (Daniel, 2026-09-02: dragging it into the workflow bar's "With" slot
    /// must run the workflow on this document, or on the artifact the pane is
    /// pointed at). The lens wins over the document, because the pane's head
    /// names the artifact and the drag must promise what the head says.
    private func readerProxyIdentity(for document: Document, text: String) -> LibraryItemDrag {
        if let lens = artifactLens {
            return LibraryItemDrag(
                kind: .artifact,
                id: lens.artifactId,
                documentId: document.id,
                text: text,
                libraryId: LibraryManager.shared.currentLibraryId,
                name: lens.label
            )
        }
        return LibraryItemDrag(
            kind: document.docType == .page ? .page : .document,
            id: document.id,
            documentId: document.id,
            text: text,
            libraryId: LibraryManager.shared.currentLibraryId,
            name: DocumentTitle.displayName(for: document)
        )
    }

    /// Pinning freezes this pane on its current view (Daniel, 2026-08-23);
    /// the shared head renders the pin menu from this binding. NO zoom
    /// controls in the head: reader zoom is a menu command (⌘+/⌘−/⌘0) via
    /// the shared `imageZoomActions` focused value below.
    private var readerPinBinding: Binding<Bool> {
        Binding(
            get: { isPinned },
            set: { pin in
                if pin {
                    pinnedDocument = liveDocument
                    pinnedActivePageNumber = liveActivePageNumber
                    pinnedPageCount = livePageCount
                }
                isPinned = pin
            }
        )
    }

    // readerCrumbs / libraryName live in ReadingPaneView+Crumbs.swift —
    // split out when the multi-selection honesty rule pushed this file past
    // the 400-line lint threshold (2026-08-29).
}
