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
    /// (2026-07-11 design). Per-window via @SceneStorage. Page hosts the REAL
    /// multi-page WebKit transcript (#3765); the old "reader reads the source
    /// first" note is retired — the source lives in Preview, never here.
    @SceneStorage("reader.topTab") private var readerTabRaw = ReaderTab.page.rawValue
    var readerTab: ReaderTab { ReaderTab(rawValue: readerTabRaw) ?? .page }
    private var readerTabBinding: Binding<ReaderTab> {
        Binding(get: { readerTab }, set: { readerTabRaw = $0.rawValue })
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
            // Shared top-tab chrome (Page/Knowledge/Notes) — the same
            // SurfaceTabBar icon row the Inspector uses (#3530), fixed over the
            // WebKit/native content beneath (reader IA fold, 2026-07-11).
            SurfaceTabBar(tabs: ReaderTab.allCases, selection: readerTabBinding)
            Divider()

            // In-reader find (#4338): the shared filter bar hosts the find
            // field — match count + prev/next drive the WebKit highlight. Its
            // edge is the component's ONE platform decision (#4362): top on the
            // Mac (controls near the head of the content), bottom on touch
            // platforms (reachability). Behaviour is identical on both edges.
            if MiniToolbarPlacement.preferredForReader == .top {
                PaneFilterBar(placement: .top) { readerFindBar }
            }

            readerTabContent

            if MiniToolbarPlacement.preferredForReader == .bottom {
                PaneFilterBar(placement: .bottom) { readerFindBar }
            }

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
                        // `xmark`, not `xmark.circle.fill` (#4360): the circled
                        // fill is the platform's clear-a-text-field affordance
                        // and the reader find bar uses it for exactly that —
                        // closing a pane must not wear the same glyph.
                        Image(systemName: ToolbarSymbols.closePane)
                            .foregroundStyle(.secondary)
                            .readerIconTarget()
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
                    Image(systemName: isPinned ? "pin.fill" : ToolbarSymbols.pin)
                        .imageScale(.small)
                        .readerIconTarget()
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
}
