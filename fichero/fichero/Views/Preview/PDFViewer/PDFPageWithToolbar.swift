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
    /// The document whose GEOMETRY this overlay should show — the PDF PAGE
    /// child, when the caller knows it (#4418 follow-up).
    ///
    /// `documentId` is the parent PDF, because that is what PDFKit renders
    /// from. But the importer writes each page's `text_geometry` artifact on
    /// that page's own child document, so asking the parent for geometry
    /// found nothing on a normally-imported PDF — and where some whole-doc run
    /// HAD left an artifact on the parent, one page's boxes were painted over
    /// every page. Both read to a user as "the boxes are wrong".
    ///
    /// `= nil` is load-bearing: call sites that have no page document omit it
    /// and fall back to the rendered document, which is correct for a
    /// single-page PDF and for the image surfaces.
    var geometryDocumentId: String? = nil // swiftlint:disable:this implicit_optional_initialization

    // `zoom`/`pageNav` promoted private -> internal (2026-08-29): read from
    // PDFPageWithToolbar+HeadChrome.swift, and `private` is FILE-scoped.
    @State var zoom = PDFZoomController()
    @State var pageNav = PDFPageController()

    // Each split-pane instance gets its own loupe state so toggling loupe
    // in one pane doesn't affect sibling panes. (@AppStorage would be shared
    // across all instances in the same window.)
    // Internal (not private): the +HeadChrome zoom cluster binds it.
    @State var loupeEnabled = false
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
    // #4418: recognised text regions for this page. OPTIONAL on purpose — a
    // non-optional @Environment(ArtifactService.self) traps when the host does
    // not inject it, which is the #4448 crash class; the image preview declares
    // it optional for the same reason.
    // Promoted `private` -> internal: read from PDFPageView+OCRBoxes.swift
    // after the #4418 split, and `private` in Swift is FILE-scoped, not
    // type-scoped — an extension in another file cannot see it.
    @Environment(ArtifactService.self) var artifactService: ArtifactService?
    /// The pane head's chrome seam (Daniel, 2026-08-29): this pane publishes
    /// its page nav so the head's ‹ › cluster drives PDF pages. Optional —
    /// hosts outside the preview pane publish nowhere.
    @Environment(PreviewPaneChrome.self) var paneChrome: PreviewPaneChrome?
    /// Sticky markup tool seam (Daniel, 2026-08-30); optional for headless hosts.
    @Environment(WindowState.self) private var pdfWindowState: WindowState?
    /// ON by default (#4418) — same reasoning as the image surface: geometry
    /// that exists but is never drawn is geometry nobody can check a
    /// transcription against.
    @AppStorage("pdfPreview.ocrBoxesEnabled") var ocrBoxesEnabled = true
    /// Annotation overlays show/hide (what-to-show menu, 2026-08-30).
    @AppStorage("preview.annotationsEnabled") var annotationsEnabled = true
    @State var ocrGeometry: OCRGeometry?
    @State private var isDrawingRegion = false
    @State private var pendingTool: ReaderAnnotationTool = .highlight

    /// Document ID to actually render — pinned value when locked, live prop otherwise.
    var effectiveDocumentId: String {
        isPinned ? (pinnedDocumentId ?? documentId) : documentId
    }

    /// Is this pane showing the page the HOST thinks it is?
    ///
    /// A secondary split pane and a pinned pane track their own
    /// `localPageIndex` and never tell the host, so the host's idea of the
    /// current page — and therefore the page document it hands down — can
    /// describe a different page than this pane is rendering.
    private var isShowingHostPage: Bool {
        !(isSecondarySplitPane || isPinned) || localPageIndex == pageIndex
    }

    /// The page document this pane's geometry may come from, or `nil`.
    ///
    /// `nil` in a secondary or pinned pane that has flipped away from the
    /// host's page: the host's page document does not describe what this pane
    /// is showing, and the whole point of this change is that one page's boxes
    /// must not be drawn on another. Deliberately NOT resolved per-pane here —
    /// that would put a second page→document lookup in the view, and two paths
    /// resolving the same question are how the answers drift apart.
    private var paneGeometryDocumentId: String? {
        isShowingHostPage ? geometryDocumentId : nil
    }

    /// Which document the overlay asks for geometry. The page child when this
    /// pane is showing the host's page, otherwise the rendered document —
    /// whose whole-document geometry is then filtered down to this pane's
    /// page by `boxesForDisplayedPage`.
    var effectiveGeometryDocumentId: String {
        paneGeometryDocumentId ?? effectiveDocumentId
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
        case .highlight, .note, .line:
            pendingTool = tool
            isDrawingRegion = true
        case .bookmark:
            isDrawingRegion = false
            persistRegion(nil, tool: .bookmark)
        }
    }

    /// Saved annotations for the page on screen, as per-kind marks (Daniel,
    /// 2026-08-30: markup should LOOK like what it is). Region-less bookmarks
    /// ride along as whole-page stars.
    private var pageRegionMarks: [AnnotationMark] {
        annotationStore.annotations
            .filter {
                $0.documentId == effectiveDocumentId
                    && $0.pageIndex == effectivePageIndex
                    && ($0.hasRegion || $0.kind == .bookmark)
            }
            .map(AnnotationMark.init)
    }

    /// Regions to draw: words when the pass produced them, lines otherwise —
    /// never both, the same reduction `OCRGeometryOverlay` makes for images,
    /// via the same `wordBoxes`/`lineBoxes` helpers so the level strings live
    /// in one place (#4418). Empty whenever the toggle is off.
    private var drawableOCRBoxes: [OCRGeometryBox] {
        guard ocrBoxesEnabled, let ocrGeometry else { return [] }
        let words = ocrGeometry.wordBoxes
        let level = words.isEmpty ? ocrGeometry.lineBoxes : words
        return Self.boxesForDisplayedPage(
            level,
            pageIndex: effectivePageIndex,
            isPageScoped: paneGeometryDocumentId != nil
        )
    }

    /// Keep one page's boxes off every other page.
    ///
    /// When the geometry came from the PAGE CHILD it is already this page's,
    /// and every box is drawn — a page-scoped producer is free to leave
    /// `pageIndex` unset or to number it from its own origin, and second-
    /// guessing it here would blank a correct overlay. Only geometry read from
    /// the WHOLE PDF needs filtering, and there a box that names a different
    /// page is the exact defect this guards: it belongs to a page the reader
    /// is not looking at. A box with no page index is kept either way —
    /// absence of the field is not evidence of the wrong page.
    static func boxesForDisplayedPage(
        _ boxes: [OCRGeometryBox],
        pageIndex: Int,
        isPageScoped: Bool
    ) -> [OCRGeometryBox] {
        if isPageScoped { return boxes }
        return boxes.filter { $0.pageIndex == nil || $0.pageIndex == pageIndex }
    }

    private func persistRegion(_ box: [Double]?, tool: ReaderAnnotationTool) {
        let kind: AnnotationKind = {
            switch tool {
            case .highlight:
                // Same split-button mode mapping as the image canvas
                // (Daniel, 2026-08-30): underline/strikethrough persist as
                // their own kinds.
                switch PreviewHighlightStyle(
                    rawValue: UserDefaults.standard.string(
                        forKey: PreviewHighlightStyle.storageKey) ?? ""
                ) {
                case .underline: return .underline
                case .strikethrough: return .strikethrough
                default: return .highlight
                }
            case .note: return .note
            case .bookmark: return .bookmark
            case .line: return .line
            }
        }()
        let documentId = effectiveDocumentId
        let pageIndex = effectivePageIndex
        // Sticky tool (Daniel, 2026-08-30): while the bar keeps the tool
        // armed, the draw layer stays armed for the next box.
        let sticky = pdfWindowState?.activeMarkupTool
        isDrawingRegion = sticky == .highlight || sticky == .note || sticky == .line
        // The chosen color rides a saved highlight (parity with the image
        // canvas, 2026-08-30); other kinds stay uncolored.
        let color: String? = kind == .highlight
            ? PreviewHighlightStyle(
                rawValue: UserDefaults.standard.string(
                    forKey: PreviewHighlightStyle.storageKey) ?? ""
            )?.persistedColor
            : nil
        // Word-boundary snap — same rule as the image canvas (2026-08-30).
        let snapKinds: Set<AnnotationKind> = [.highlight, .underline, .strikethrough]
        let rects: [[Double]?]
        if let box, snapKinds.contains(kind), let geometry = ocrGeometry {
            rects = AnnotationWordSnap.snappedRects(
                drag: box, words: geometry.wordBoxes, lines: geometry.lineBoxes
            )
        } else {
            rects = [box]
        }
        // Coding v1 (Daniel, 2026-08-30, ruling 4): pending tags ride the
        // next highlight-family save — every strip of this ONE gesture.
        let tagKinds: Set<AnnotationKind> = [.highlight, .underline, .strikethrough]
        let tags = tagKinds.contains(kind) ? (pdfWindowState?.takePendingMarkupTags() ?? []) : []
        Task {
            for rect in rects {
                _ = await annotationStore.addNote(
                    scope: .document(documentId),
                    text: "",
                    bbox: rect,
                    pageIndex: pageIndex,
                    kind: kind,
                    color: color,
                    tags: tags
                )
            }
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
                // The #3579 active-surface hairline is GONE here too (Daniel,
                // 2026-09-01: "no focus or active rings anywhere") — the same
                // 2pt accent rectangle the reader pane drew, removed in the
                // same pass so the rule holds on every surface rather than on
                // the one that got reported. Active-surface TRACKING stays.
                //
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
        // Head chrome (Daniel, 2026-08-29): keep the head's ‹ › cluster fed
        // with this pane's live page position.
        .onAppear { publishHeadChrome() }
        .onChange(of: pageNav.pageIndex) { _, _ in publishHeadChrome() }
        .onChange(of: pageNav.pageCount) { _, _ in publishHeadChrome() }
        // The head's markup row: highlight/note arm the same region-draw path
        // the bottom bar's annotation buttons used to (Daniel, 2026-08-29).
        .onReceive(NotificationCenter.default.publisher(for: .previewAnnotateTool)) { note in
            guard let raw = note.object as? String,
                  let tool = PreviewMarkupTool(rawValue: raw) else { return }
            switch tool {
            case .highlight: requestAnnotation(.highlight)
            case .note: requestAnnotation(.note)
            case .star: requestAnnotation(.bookmark)
            case .line: requestAnnotation(.line)
            case .textSelect, .select, .wordSelect, .drawRegion, .check:
                break  // preview-regions lane / future drawing kinds
            }
        }
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
        // #4418: re-probe when the geometry document or the toggle changes.
        //
        // Keying on the PAGE INDEX was rejected in 2026-08-08 ("changing page
        // in PDF feels slow") and that was right at the time: the loader's
        // only input was the parent PDF's id, so a flip re-ran identical
        // round-trips and threw the identical answer away. The premise has
        // changed — geometry lives on the PAGE CHILD, so each page has a
        // DIFFERENT answer and a flip must fetch it. This keys on the page
        // document rather than the index, so the reload happens exactly when
        // the answer can differ and not once per flip within a page.
        // `effectivePageIndex` is in the id for the panes the host cannot see:
        // a secondary or pinned pane flips locally, so its geometry document
        // falls back to the whole PDF and the reload must follow ITS page.
        // For the primary pane the page document already changes on a flip, so
        // this adds no extra fetch there.
        .task(id: "\(effectiveGeometryDocumentId)|\(effectivePageIndex)|\(ocrBoxesEnabled)") {
            // AppKit only: the PDF box renderer draws PDFAnnotations through
            // PDFPageView+OCRBoxes, which is itself #if canImport(AppKit). iOS
            // has no PDF overlay yet (#4418 shipped the Mac half), so there is
            // nothing to load for.
            #if canImport(AppKit)
            await loadOCRGeometry()
            #endif
        }
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
                regionMarks: annotationsEnabled ? pageRegionMarks : [],
                ocrBoxes: drawableOCRBoxes,
                isDrawingRegion: isDrawingRegion,
                onCreateRegion: { box in persistRegion(box, tool: pendingTool) },
                displayMode: pageLayout.pdfDisplayMode ?? .singlePage,
                displayDirection: pageLayout.pdfDisplayDirection
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
            .onChange(of: pdfWindowState?.activeMarkupTool) { _, tool in
                switch tool {
                case .highlight: pendingTool = .highlight; isDrawingRegion = true
                case .note: pendingTool = .note; isDrawingRegion = true
                case .line: pendingTool = .line; isDrawingRegion = true
                default: isDrawingRegion = false
                }
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
        // The magnification family, bottom-right (Daniel, 2026-08-29): the
        // zoom pill + loupe toggle — see +HeadChrome.swift.
        // Top-right (Daniel, 2026-08-30 — moved up from the bottom corner).
        .overlay(alignment: .topTrailing) { zoomClusterOverlay }
    }

    /// × close handler — only present when there is something to close (an
    /// onClose callback or an active split). Computed explicitly so the body
    /// isn't a ternary mixing a method reference with `nil`.
    private var closeHandler: (() -> Void)? {
        guard onClose != nil || isInSplit else { return nil }
        return closePane
    }

    // pdfPageNav / publishHeadChrome / zoomClusterOverlay live in
    // PDFPageWithToolbar+HeadChrome.swift (2026-08-29, file/type length).

    // loupeLockedBinding removed with the quiet bar (Daniel, 2026-08-29): the
    // loupe follows the cursor; the lock affordance left with the old loupe
    // section. `loupeLocked` state remains for effectiveLoupePosition.

    // QUIET bottom bar (Daniel, 2026-08-29): page-nav moved to the pane head,
    // zoom + loupe to the floating cluster, annotation to the head's
    // slide-out markup row. The bar keeps chrome (close/title), the
    // page-layout menu, the regions toggle, and the pin — the ⓘ went
    // (2026-08-30: it only toggled the inspector).
    private var readerToolbar: some View {
        ReaderToolbar(
            style: .quiet,
            onShowInfo: {
                NotificationCenter.default.post(name: .previewShowInfo, object: nil)
            },
            title: documentTitle,
            onClose: closeHandler,
            isInSplit: isInSplit,
            pageLayout: pageLayoutBinding,
            scalePercent: Int(zoom.scale * 100),
            zoomIn: { zoom.zoomIn() },
            zoomOut: { zoom.zoomOut() },
            fitToWindow: { zoom.fitToWindow() },
            actualSize: { zoom.actualSize() },
            textBoxesEnabled: $ocrBoxesEnabled,
            annotationsEnabled: $annotationsEnabled,
            isPinned: $isPinned,
            onTogglePin: togglePin
        )
    }
}
