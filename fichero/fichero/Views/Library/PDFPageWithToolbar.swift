import OSLog
import SwiftUI

// MARK: - PDFPageWithToolbar

/// PDFPageView previously bundled its own zoom toolbar (#656). The
/// embedded toolbar duplicated the document inspector's zoom controls
/// + the LibraryView icon-zoom strip, producing two stacked sets of
/// magnifier pills (#1010). The toolbar is now removed; PDFKit's
/// native ⌘+ / ⌘- still work, and the inspector toolbar remains the
/// canonical zoom surface.
struct PDFPageWithToolbar: View {
    let documentId: String
    let pageIndex: Int
    var onPageIndexChange: ((Int) -> Void)?
    /// Display name shown in the toolbar title slot.
    var documentTitle: String? = nil
    /// Called when the user taps the × close button. Omit to hide the button.
    var onClose: (() -> Void)? = nil

    @StateObject private var zoom = PDFZoomController()
    @StateObject private var pageNav = PDFPageController()

    // Each split-pane instance gets its own loupe state so toggling loupe
    // in one pane doesn't affect sibling panes. (@AppStorage would be shared
    // across all instances in the same window.)
    @State private var loupeEnabled = false
    @State private var loupeMagnification: Double = 3.0
    @State private var loupeSize: Double = 150.0
    @State private var loupeLocked = false

    @State private var loupePosition: CGPoint = .init(x: 0.5, y: 0.5)
    @State private var loupeLockedPosition: CGPoint = .init(x: 0.5, y: 0.5)

    @Environment(\.splitAxisActions) private var splitAxisActions
    // Secondary split panes manage their own page index so navigating in one
    // pane doesn't force all other panes to the same page.
    @Environment(\.isSecondarySplitPane) private var isSecondarySplitPane
    @State private var localPageIndex: Int = 0

    // Per-pane pin: when pinned, the pane ignores global selection changes
    // and stays on the document and page that were active at pin time.
    @State private var isPinned = false
    @State private var pinnedDocumentId: String? = nil

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
        if let actions = splitAxisActions {
            // H-split is more local than V-split; collapse it first so clicking X
            // on a pane in a row collapses that row, not the whole left/right split.
            if actions.hasHorizontal { actions.onToggleHorizontal(); return }
            if actions.hasVertical   { actions.onToggleVertical();   return }
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

    /// Annotation tools are present in the unified reader toolbar but their
    /// region-anchored creation + on-canvas rendering is owned by **#2458**.
    /// Until that lands this is a clearly-marked stub so the section is visible
    /// and tappable without creating orphan annotations.
    private func requestAnnotation(_ tool: ReaderAnnotationTool) {
        Self.log.info(
            "Reader annotation '\(tool.rawValue, privacy: .public)' on PDF — pending region capture + rendering (#2458)"
        )
    }

    var body: some View {
        VStack(spacing: 0) {
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
                    onCursorMoved: { pos in loupePosition = pos }
                )
                .onAppear { localPageIndex = pageIndex }
                .onChange(of: pageIndex) { _, newIndex in
                    // Primary unpinned pane: keep in step with parent selection.
                    // Secondary or pinned pane: ignore parent changes.
                    if !isSecondarySplitPane && !isPinned { localPageIndex = newIndex }
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

            Divider()

            // Unified, persistent reader toolbar (#2423 / #2421) — bottom-anchored.
            // PDF capabilities: page-nav + zoom + loupe + annotation enabled;
            // the magnifier-panel and image-edit tools render greyed because they
            // don't apply to a PDF page. Pin lives in the trailing slot, after the
            // split buttons MiniToolbar injects from the environment.
            ReaderToolbar(
                title: documentTitle,
                onClose: (onClose != nil || isInSplit) ? closePane : nil,
                isInSplit: isInSplit,
                pageNav: ReaderPageNav(
                    pageIndex: pageNav.pageIndex,
                    pageCount: pageNav.pageCount,
                    canGoPrevious: pageNav.canGoPrevious,
                    canGoNext: pageNav.canGoNext,
                    goPrevious: { pageNav.goToPrevious() },
                    goNext: { pageNav.goToNext() }
                ),
                scalePercent: Int(zoom.scale * 100),
                zoomIn: { zoom.zoomIn() },
                zoomOut: { zoom.zoomOut() },
                fitToWindow: { zoom.fitToWindow() },
                actualSize: { zoom.actualSize() },
                magnifierEnabled: nil,
                loupeEnabled: $loupeEnabled,
                loupeLocked: Binding(
                    get: { loupeLocked },
                    set: { newValue in
                        if newValue, !loupeLocked { loupeLockedPosition = loupePosition }
                        loupeLocked = newValue
                    }
                ),
                loupeMagnification: $loupeMagnification,
                isEditing: nil,
                onAnnotate: requestAnnotation,
                isPinned: $isPinned,
                onTogglePin: togglePin
            )
        }
    }
}
