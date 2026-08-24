import SwiftUI

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

    @Environment(APIClient.self) var apiClient
    /// The existing busy-state source for per-page run progress (#4357): the
    /// store's run target record (#4295) plus the live page content it splices
    /// in mid-run (#4318). No second notion of "this document is working".
    @Environment(DocumentStore.self) var documentStore: DocumentStore
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
        // Active-surface indicator (#3579): accent hairline along the pane's
        // top edge when this pane is the active one. Additive overlay — flips
        // one pane's fill, no relayout.
        .overlay(alignment: .top) {
            Rectangle()
                .fill(isActiveSurface ? Color.accentColor : Color.clear)
                .frame(height: 2)
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

    /// Bring the Reader to the Page tab so a revealed claim/entity lands on the
    /// transcript, which scrolls to the page anchor (#3226). There is no longer a
    /// source layout to switch: the source is Preview's job (#3765 Q4), and the
    /// reveal drives that pane separately via `.ficheroNavigateToPage`.
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
        let head = PaneHead<PaneKindSelector<ReaderLens>, EmptyView, EmptyView>(
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
                (documentStore.childrenCache[crumb.id] ?? []).map(PaneCrumb.init)
            },
            selector: { self.readerSelector },
            controls: { EmptyView() },
            tools: { EmptyView() }
        )
        // The menu bar shows the SAME lens list, reading this publication —
        // one binding rendered twice, never a second switch (R3).
        return head
            .focusedSceneValue(\.readerLens, publishedReaderLens)
            // Reader zoom is menu-command only (Daniel, 2026-08-23): the same
            // ⌘+/⌘−/⌘0 commands the preview uses drive `webZoom` here. The
            // preview's own publication wins whenever an image view is the
            // focused scene value's source — standard focused-value shadowing.
            .focusedSceneValue(\.imageZoomActions, ImageZoomActions(
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
                }
            }
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

    /// The pane's title line IS its breadcrumb (R1), not "Reader" — and it is
    /// the FULL ancestry (Daniel, 2026-08-23: "it's important"):
    /// "Marshall Diaries v4 › Inbox › 1933".
    ///
    /// Through `libraryPathCrumbs`, the walk the library's path bar already
    /// uses — root-first, cycle-guarded, depth-capped. A second ancestor walk
    /// for the same question is how two surfaces come to disagree about where
    /// you are.
    ///
    /// ponytail: names today. Daniel's proxy-icon crumbs (parents collapse to
    /// icons with chevrons, expanding on hover) are a later slice; the capsule
    /// truncates from the leading edge until then, so a deep path still shows
    /// the part that identifies it.
    private var readerCrumbs: [PaneCrumb] {
        guard let document = effectiveDocument else { return [] }
        let ancestry = libraryPathCrumbs(
            anchorId: document.id,
            resolve: { documentStore.resolveDocument($0) }
        )
        // The library is the root crumb: a path that starts at a folder does
        // not say WHICH library's Inbox you are in, and several are open at
        // once in the normal case. Not navigable from a reader (yet).
        var crumbs: [PaneCrumb] = []
        if let libraryName {
            crumbs.append(PaneCrumb(
                id: "library-root", name: libraryName,
                icon: "books.vertical.fill", isNavigable: false, tint: .accentColor
            ))
        }
        crumbs += ancestry.isEmpty ? [PaneCrumb(document)] : ancestry.map(PaneCrumb.init)
        return crumbs
    }

    /// The library the read document belongs to, for the root crumb.
    ///
    /// `Document` carries no library id — the current library IS the reading
    /// context, the same assumption the path bar and the sidebar reveal make.
    private var libraryName: String? {
        guard let libraryId = LibraryManager.shared.currentLibraryId,
              let library = LibraryManager.shared.getLibrary(id: libraryId)
        else { return nil }
        return library.displayName
    }

}
