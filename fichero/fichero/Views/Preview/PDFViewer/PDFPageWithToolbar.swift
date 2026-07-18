import OSLog
import SwiftUI

// MARK: - PDFPageWithToolbar

/// A PDF page plus its page toolbar (title / paging / close). It carries no
/// zoom controls by design: the standalone zoom toolbars (`PDFPageView`'s old
/// embedded one, #656/#1010, and `ImageZoomToolbar`, deleted in #3032) were
/// removed because they duplicated the inspector's zoom surface. Zoom is PDFKit
/// native (⌘+ / ⌘-) plus the inspector, which stays the canonical zoom surface.
struct PDFPageWithToolbar: View {
    let documentId: String
    let pageIndex: Int
    var onPageIndexChange: ((Int) -> Void)?
    /// Display name shown in the toolbar title slot.
    /// `= nil` is load-bearing: 3 call sites omit this arg.
    var documentTitle: String? = nil // swiftlint:disable:this implicit_optional_initialization
    /// Called when the user taps the × close button. Omit to hide the button.
    /// `= nil` is load-bearing: 3 call sites omit this arg.
    var onClose: (() -> Void)? = nil // swiftlint:disable:this implicit_optional_initialization

    @State private var zoom = PDFZoomController()
    @State private var pageNav = PDFPageController()

    // Each split-pane instance gets its own loupe state so toggling loupe
    // in one pane doesn't affect sibling panes. (@AppStorage would be shared
    // across all instances in the same window.)
    @State private var loupeEnabled = false
    @State private var loupeMagnification: Double = 3.0
    @State private var loupeSize: Double = 150.0
    @State private var loupeLocked = false

    @State private var loupePosition: CGPoint = .init(x: 0.5, y: 0.5)
    @State private var loupeLockedPosition: CGPoint = .init(x: 0.5, y: 0.5)

    // Per-window reading layout (#2090). @SceneStorage keeps each window's PDF
    // page arrangement independent; stored as the PageLayoutMode rawValue so the
    // saved value stays stable across launches.
    @SceneStorage("reader.pageLayout") private var pageLayoutRaw = PageLayoutMode.singlePage.rawValue
    private var pageLayout: PageLayoutMode { PageLayoutMode(rawValue: pageLayoutRaw) ?? .singlePage }
    private var pageLayoutBinding: Binding<PageLayoutMode> {
        Binding(
            get: { PageLayoutMode(rawValue: pageLayoutRaw) ?? .singlePage },
            set: { pageLayoutRaw = $0.rawValue }
        )
    }

    @Environment(\.splitAxisActions) private var splitAxisActions
    // Secondary split panes manage their own page index so navigating in one
    // pane doesn't force all other panes to the same page.
    @Environment(\.isSecondarySplitPane) private var isSecondarySplitPane
    @State private var localPageIndex: Int = 0

    // Per-pane pin: when pinned, the pane ignores global selection changes
    // and stays on the document and page that were active at pin time.
    @State private var isPinned = false
    @State private var pinnedDocumentId: String?

    /// Per-window active-surface marker (#3579). A direct click in this pane
    /// makes it active; the reader toolbar draws an accent hairline when it is.
    @Environment(ActiveSurfaceState.self) private var activeSurfaceState: ActiveSurfaceState?
    /// Stable identity for THIS pane instance — minted once at mount, so left
    /// and right splits are tracked independently (mirrors per-instance pin).
    @State private var surfaceId = SurfaceID()

    /// Open-in-new-tab/window plumbing for the pane's title-bar context menu
    /// (#3582, browser-tab metaphor). Reuses the shared WindowOpener path.
    @Environment(\.openWindow) private var openWindow

    /// Open THIS pane's document in a native tab (`asTab`) or a new window,
    /// via the same Safari-style path library rows use.
    private func openThisDocumentInNewWindow(asTab: Bool) {
        let libraryId = LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId
        WindowOpener.open(libraryId: libraryId, documentId: effectiveDocumentId, asTab: asTab, using: openWindow)
    }

    // Bounding-box annotation state (#2458). `isDrawingRegion` arms a region
    // drag on the page; `pendingTool` carries the kind into the saved box.
    @Environment(AnnotationStore.self) private var annotationStore: AnnotationStore
    @State private var isDrawingRegion = false
    @State private var pendingTool: ReaderAnnotationTool = .highlight

    /// Document ID to actually render — pinned value when locked, live prop otherwise.
    private var effectiveDocumentId: String {
        isPinned ? (pinnedDocumentId ?? documentId) : documentId
    }

    /// Which page to display: parent-driven for the primary unpinned pane,
    /// locally tracked for every secondary pane or any pinned pane.
    private var effectivePageIndex: Int {
        (isSecondarySplitPane || isPinned) ? localPageIndex : pageIndex
    }

    private var scaleBinding: Binding<CGFloat> {
        Binding(
            get: { zoom.scale },
            set: { zoom.scale = $0 }
        )
    }

    private var effectiveLoupePosition: CGPoint {
        loupeLocked ? loupeLockedPosition : loupePosition
    }

    /// X button action: collapses the active split when inside one,
    /// otherwise calls onClose to hide the whole pane.
    private func closePane() {
        if let actions = splitAxisActions, actions.hasHorizontal || actions.hasVertical {
            // Collapse the active axis one pane at a time so 3 -> 2 -> 1.
            actions.onCollapseSplit()
            return
        }
        onClose?()
    }

    private static let log = Logger(subsystem: "app.fichero.fichero", category: "ReaderToolbar")

    /// True when this pane is inside an active split — the × collapses the split.
    private var isInSplit: Bool {
        splitAxisActions.map { $0.hasVertical || $0.hasHorizontal } ?? false
    }

    /// Pin/unpin this pane to its current document + page.
    private func togglePin() {
        if isPinned {
            isPinned = false
        } else {
            pinnedDocumentId = documentId
            localPageIndex = pageIndex
            isPinned = true
        }
    }

    /// Reader-toolbar annotation tools (#2458). Highlight/Note arm a region
    /// drag on the PDF page; Bookmark is a whole-page marker.
    private func requestAnnotation(_ tool: ReaderAnnotationTool) {
        switch tool {
        case .highlight, .note:
            pendingTool = tool
            isDrawingRegion = true
        case .bookmark:
            isDrawingRegion = false
            persistRegion(nil, tool: .bookmark)
        }
    }

    /// Saved region boxes (normalized `[x,y,w,h]`) for the page on screen.
    private var pageRegionBoxes: [[Double]] {
        annotationStore.annotations
            .filter {
                $0.documentId == effectiveDocumentId
                    && $0.pageIndex == effectivePageIndex
                    && $0.hasRegion
            }
            .compactMap(\.bbox)
    }

    private func persistRegion(_ box: [Double]?, tool: ReaderAnnotationTool) {
        let kind: AnnotationKind = {
            switch tool {
            case .highlight: return .highlight
            case .note: return .note
            case .bookmark: return .bookmark
            }
        }()
        let documentId = effectiveDocumentId
        let pageIndex = effectivePageIndex
        isDrawingRegion = false
        Task {
            _ = await annotationStore.addNote(
                scope: .document(documentId),
                text: "",
                bbox: box,
                pageIndex: pageIndex,
                kind: kind
            )
        }
    }

    private func loadAnnotations() {
        let documentId = effectiveDocumentId
        Task { await annotationStore.loadAnnotations(for: .document(documentId), force: true) }
    }

    // Body kept tiny; the page content and the reader toolbar are each broken
    // into bounded computed vars so neither sub-expression trips the Swift
    // type-checker timeout (the LibraryWindow.body class of failure).
    var body: some View {
        VStack(spacing: 0) {
            pageContent
            Divider()
            readerToolbar
                // Active-surface indicator (#3579): accent hairline on the
                // toolbar strip when this pane is active. Additive, no relayout.
                .overlay(alignment: .top) {
                    Rectangle()
                        .fill(isActiveSurface ? Color.accentColor : Color.clear)
                        .frame(height: 2)
                }
                // Title-bar "Open in New Tab/Window" (#3582). Right-click the
                // pane's toolbar to pop THIS document out — the browser-tab
                // metaphor. Reuses the shared OpenInMenuItems (no "Open": the
                // pane already shows the document).
                .contextMenu {
                    OpenInMenuItems(
                        openInNewTab: { openThisDocumentInNewWindow(asTab: true) },
                        openInNewWindow: { openThisDocumentInNewWindow(asTab: false) }
                    )
                }
        }
        // A direct click anywhere in this pane makes it the active surface
        // (#3579). simultaneousGesture runs alongside PDFKit hit-testing so it
        // never steals the click — same pattern as focusedPane tracking.
        .simultaneousGesture(TapGesture().onEnded { activeSurfaceState?.activate(surfaceId) })
        // Join/leave the active-surface pool (#3580). Registering when it appears
        // makes a sole pane auto-active; toggling on isPinned clears active if it
        // pointed here (pinned panes never follow selection) and hands a lone
        // survivor the active slot.
        .onAppear { activeSurfaceState?.registerUnpinned(surfaceId) }
        .onDisappear { activeSurfaceState?.unregister(surfaceId) }
        .onChange(of: isPinned) { _, pinned in
            if pinned { activeSurfaceState?.unregister(surfaceId) }
            else { activeSurfaceState?.registerUnpinned(surfaceId) }
        }
    }

    /// True when this pane instance is the window's active surface (#3579).
    private var isActiveSurface: Bool {
        activeSurfaceState?.activeSurfaceId == surfaceId
    }

    private var pageContent: some View {
        ZStack {
            PDFPageView(
                documentId: effectiveDocumentId,
                pageIndex: effectivePageIndex,
                onPageIndexChange: { newIndex in
                    if isSecondarySplitPane || isPinned {
                        localPageIndex = newIndex
                    } else {
                        onPageIndexChange?(newIndex)
                    }
                },
                zoomController: zoom,
                pageController: pageNav,
                onCursorMoved: { pos in loupePosition = pos },
                regionBoxes: pageRegionBoxes,
                isDrawingRegion: isDrawingRegion,
                onCreateRegion: { box in persistRegion(box, tool: pendingTool) },
                displayMode: pageLayout.pdfDisplayMode ?? .singlePage
            )
            .onAppear {
                localPageIndex = pageIndex
                loadAnnotations()
            }
            .onChange(of: pageIndex) { _, newIndex in
                // Primary unpinned pane: keep in step with parent selection.
                // Secondary or pinned pane: ignore parent changes.
                if !isSecondarySplitPane && !isPinned { localPageIndex = newIndex }
            }
            .onChange(of: effectiveDocumentId) { _, _ in
                isDrawingRegion = false
                loadAnnotations()
            }
            .onChange(of: annotationStore.changeToken) { _, _ in
                loadAnnotations()
            }

            if loupeEnabled {
                PDFLoupeOverlay(
                    documentId: effectiveDocumentId,
                    pageIndex: effectivePageIndex,
                    cursorPosition: effectiveLoupePosition,
                    magnification: loupeMagnification,
                    loupeSize: loupeSize
                )
                .allowsHitTesting(false)
            }
        }
    }

    /// × close handler — only present when there is something to close (an
    /// onClose callback or an active split). Computed explicitly so the body
    /// isn't a ternary mixing a method reference with `nil`.
    private var closeHandler: (() -> Void)? {
        guard onClose != nil || isInSplit else { return nil }
        return closePane
    }

    private var pdfPageNav: ReaderPageNav {
        ReaderPageNav(
            pageIndex: pageNav.pageIndex,
            pageCount: pageNav.pageCount,
            canGoPrevious: pageNav.canGoPrevious,
            canGoNext: pageNav.canGoNext,
            goPrevious: { pageNav.goToPrevious() },
            goNext: { pageNav.goToNext() }
        )
    }

    private var loupeLockedBinding: Binding<Bool> {
        Binding(
            get: { loupeLocked },
            set: { newValue in
                if newValue, !loupeLocked { loupeLockedPosition = loupePosition }
                loupeLocked = newValue
            }
        )
    }

    // Unified, persistent reader toolbar (#2423 / #2421) — bottom-anchored.
    // PDF capabilities: page-nav + zoom + loupe + annotation enabled; the
    // magnifier-panel and image-edit tools render greyed because they don't
    // apply to a PDF page. Pin lives in the trailing slot, after the split
    // buttons MiniToolbar injects from the environment.
    private var readerToolbar: some View {
        ReaderToolbar(
            title: documentTitle,
            onClose: closeHandler,
            isInSplit: isInSplit,
            pageNav: pdfPageNav,
            pageLayout: pageLayoutBinding,
            scalePercent: Int(zoom.scale * 100),
            zoomIn: { zoom.zoomIn() },
            zoomOut: { zoom.zoomOut() },
            fitToWindow: { zoom.fitToWindow() },
            actualSize: { zoom.actualSize() },
            magnifierEnabled: nil,
            loupeEnabled: $loupeEnabled,
            loupeLocked: loupeLockedBinding,
            loupeMagnification: $loupeMagnification,
            isEditing: nil,
            onAnnotate: requestAnnotation,
            isPinned: $isPinned,
            onTogglePin: togglePin
        )
    }
}
