#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import OSLog
import SwiftUI

#if os(macOS)

// MARK: - Zoomable Image Preview (with controls and magnifier)

struct ZoomableImagePreview: View {
    /// Local file URL. Required for the plain-preview path; ignored when
    /// `renderedImage` is provided (editor / backend-rendered preview mode).
    var url: URL?
    var documentId: String?
    /// Backend-rendered NSImage (editor mode). When non-nil, takes precedence
    /// over `url` for display — the URL is still used as a stable identity key
    /// but image data comes from this override (#1402).
    var renderedImage: NSImage?
    /// Optional callback fired when the user steps to a sibling image. macOS
    /// relies on the window-level sibling navigation (#593); the parameter is
    /// kept for API parity with the iOS overlay buttons (#2420).
    var onNavigateToDocument: ((String) -> Void)?
    /// Drives the host's view↔edit toggle from the unified reader toolbar's edit
    /// button. `nil` greys the edit tool out (e.g. a context without an editor).
    /// Threading it here removes the floating edit toggle that used to overlap
    /// the split control (#2421).
    var isEditing: Binding<Bool>?
    /// Entry-source highlight: normalized `[x,y,w,h]` boxes drawn with the
    /// saved-region layer (preview-layers M1, #27). Display-only.
    var highlightBoxes: [[Double]] = []
    /// Entry ladder (2026-08-23, "we should only show the bounding box"):
    /// when set, the image OPENS zoomed to this normalized rect instead of
    /// fit-to-window.
    var focusRegion: [Double]?
    /// Entry ladder: the host's containment step (region → page → spread).
    /// Vertical swipes/arrows call this FIRST; a `true` return consumes the
    /// step, `false` falls through to the rendition flip — so on an entry the
    /// vertical axis walks the containment ladder, on a plain page it keeps
    /// flipping renditions.
    var onContainmentStep: ((Int) -> Bool)?

    init(
        url: URL? = nil,
        documentId: String? = nil,
        renderedImage: NSImage? = nil,
        onNavigateToDocument: ((String) -> Void)? = nil,
        isEditing: Binding<Bool>? = nil,
        highlightBoxes: [[Double]] = [],
        focusRegion: [Double]? = nil,
        onContainmentStep: ((Int) -> Bool)? = nil
    ) {
        self.url = url
        self.documentId = documentId
        self.renderedImage = renderedImage
        self.onNavigateToDocument = onNavigateToDocument
        self.isEditing = isEditing
        self.highlightBoxes = highlightBoxes
        self.focusRegion = focusRegion
        self.onContainmentStep = onContainmentStep
    }

    /// One vertical step: the containment ladder when the host provides one,
    /// the rendition flip otherwise.
    private func verticalStep(_ step: Int) {
        if let onContainmentStep, onContainmentStep(step) { return }
        flipRendition(to: renditionIndex + step)
    }

    /// Annotation tools from the reader toolbar (#2458). Highlight/Note arm a
    /// region draw over the image; the resulting normalized box is persisted as
    /// a bounding-box annotation. Bookmark is a whole-image marker (no region).
    /// internal: the reader toolbar moved to +Overlays.swift (2026-08-23
    /// file-length) and Swift's `private` is FILE-scoped.
    func requestAnnotation(_ tool: ReaderAnnotationTool) {
        switch tool {
        case .highlight, .note:
            pendingAnnotationTool = tool
            isDrawingRegion = true
        case .bookmark:
            isDrawingRegion = false
            createAnnotation(box: nil, tool: .bookmark)
        }
    }

    /// Persist a region (or whole-image bookmark) via the typed AnnotationStore.
    ///
    /// `internal` (not `private`) so `boxOverlays` in
    /// ZoomableImagePreviewMac+Overlays.swift can call it — a `private` member
    /// is invisible to an extension in another file, the same reason
    /// `sectionDivider` on ReaderToolbar is internal.
    func createAnnotation(box: [Double]?, tool: ReaderAnnotationTool) {
        guard let documentId else { return }
        let kind: AnnotationKind = {
            switch tool {
            case .highlight: return .highlight
            case .note: return .note
            case .bookmark: return .bookmark
            }
        }()
        isDrawingRegion = false
        Task {
            _ = await annotationStore.addNote(
                scope: .document(documentId),
                text: "",
                bbox: box,
                kind: kind
            )
        }
    }

    /// Saved region boxes (normalized `[x,y,w,h]`) for the shown image.
    var regionBoxes: [[Double]] {
        guard let documentId else { return [] }
        return annotationStore.annotations
            .filter { ($0.documentId == documentId || $0.pageId == documentId) && $0.hasRegion }
            .compactMap(\.regionRect)
    }

    func loadAnnotations() {
        guard let documentId else { return }
        Task { await annotationStore.loadAnnotations(for: .document(documentId), force: true) }
    }

    static let logger = Logger(subsystem: "app.fichero.fichero", category: "ZoomableImagePreview")

    /// Document ids in the +/-`radius` window around `currentId`, excluding `currentId` itself.
    /// Static so it can be called in unit tests without a live view (#2469).
    static func preloadIds(from docs: [Document], currentId: String, radius: Int = 3) -> [String] {
        guard let index = docs.firstIndex(where: { $0.id == currentId }) else { return [] }
        let start = max(0, index - radius)
        let end = min(docs.count - 1, index + radius)
        guard start <= end else { return [] }
        return (start...end).compactMap { idx in idx == index ? nil : docs[idx].id }
    }

    // These settings persist across image changes using AppStorage
    @AppStorage("imagePreview.magnifierEnabled") var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") var loupeEnabled = false
    @AppStorage("imagePreview.loupeMagnification") var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") var panelHeight: Double = 120.0
    @AppStorage("imagePreview.magnifierLocked") var magnifierLocked = false
    @AppStorage("imagePreview.loupeLocked") var loupeLocked = false

    @Environment(StorageService.self) var storageService
    @Environment(AnnotationStore.self) var annotationStore: AnnotationStore
    /// Optional so previews / hosts without the service stay safe; the text-box
    /// toggle simply loads nothing without it.
    @Environment(ArtifactService.self) var artifactService: ArtifactService?
    /// Optional so previews / hosts without the service stay safe; the
    /// rendition control simply stays hidden without it.
    @Environment(RenditionService.self) var renditionService: RenditionService?
    /// Optional for the same reason; without it the page arrows hide and
    /// sibling stepping stays swipe-only.
    @Environment(DocumentStore.self) var documentStore: DocumentStore?

    // Bounding-box annotation state (#2458). `isDrawingRegion` arms the overlay
    // drag; `pendingAnnotationTool` carries the tool kind into the saved box.
    @State var isDrawingRegion = false
    @State var pendingAnnotationTool: ReaderAnnotationTool = .highlight

    // OCR text-box overlay (#4309): the transcription pass's word/line boxes
    // rendered over the page image, fetched from the artifact API on demand.
    // The loader lives in OCRGeometryOverlay.swift to keep this body lean.
    /// ON by default (#4418). Apple Vision is wrong on roughly two characters
    /// in five of this material and cannot be tuned better (#4497), so the
    /// boxes are how a reader sees WHICH two — a page with no boxes over half
    /// its text is a page the transcription never read. Shipping that
    /// default-off left a switch nobody would find, which the standing rule
    /// calls worse than absent.
    @AppStorage("imagePreview.ocrBoxesEnabled") var ocrBoxesEnabled = true
    @State var ocrGeometry: OCRGeometry?

    // Renditions of the current page (2026-08-20 bbox review). `renditions`
    // arrives in ENGINE order — primary first, then role preference — so this
    // view never re-sorts; doing so would recreate the disagreement about
    // what "next" means that ordering server-side exists to prevent.
    @State var renditions: [DocumentRendition] = []
    @State var renditionIndex: Int = 0
    /// The flipped-to rendition's pixels. MUST outrank `renderedImage` in the
    /// override chain: the flip used to write `image`, which rendered-mode
    /// ignores — the engine served each rendition's distinct bytes (200s in
    /// the log) and the view kept showing the display JPEG, reading as "no
    /// difference between original, enhanced, and background removed"
    /// (Daniel, 2026-08-21). Cleared on document change.
    @State var renditionOverrideImage: NSImage?

    @State var scale: CGFloat = 1.0
    @State var minScale: CGFloat = 0.01
    @State var maxScale: CGFloat = 10.0
    @State var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Current cursor position over image
    @State var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Position when locked
    @State var imageSize: CGSize = .zero
    @State var image: NSImage?
    /// Visible window + drawn image rect, measured together by the scroll
    /// coordinator (2026-08-20 bbox review, D3). Overlays frame to
    /// `drawnFrame`, never the whole pane — at fit-with-letterbox a
    /// pane-spanning overlay drew normalized boxes into the gray margins
    /// below the image (2026-08-12 bbox repro) — and map through `visible`.
    /// One value because the two are only correct together.
    @State var geometry: PreviewImageGeometry = .unmeasured
    @State var imageCoordinator: ImageWithCursorTracking.Coordinator?
    // Full-resolution source image fetched lazily when zoom exceeds 1.5× (#2427).
    @State var highResImage: NSImage?
    @State var isLoadingHighRes = false
    /// Word boxes lit by the READER's text selection (2026-08-23 linking) —
    /// transient, cleared when the selection clears or the item changes.
    @State var linkedSelectionBoxes: [[Double]] = []

    // Zoom actions live in ZoomableImagePreviewMac+ZoomActions.swift and the
    // opening-zoom rule in PreviewInitialZoomPolicy.swift (moved/extracted to
    // keep this body under the type-body-length budget).

    var body: some View {
        VStack(spacing: 0) {
            // Main content area. The reader toolbar (zoom / magnifier / loupe /
            // edit / annotation) now lives at the BOTTOM of the canvas via the
            // shared ReaderToolbar (#2423), so the image and PDF readers present
            // one identical, persistent bar.
            ZStack(alignment: .topTrailing) {
                VStack(spacing: 0) {
                    if renderedImage != nil || url != nil {
                        ImageWithCursorTracking(
                            url: url,
                            // A backend-rendered rendition WINS over the
                            // high-res source (2026-08-20 bbox review, D2).
                            // The old `highResImage ?? renderedImage` let the
                            // zoom-triggered source fetch replace the very
                            // rendition the user chose to look at — different
                            // pixels, and for a crop/rotate/deskew/split
                            // rendition a different FRAME, which moves every
                            // box on the page.
                            overrideImage: renditionOverrideImage ?? renderedImage ?? highResImage,
                            // Rendition index in the key: a flip counts as
                            // an ITEM change so the view refits — renditions
                            // have different pixel sizes, and preserving
                            // apparent width left one at 70% and the next at
                            // 26% (Daniel, 2026-08-22).
                            itemKey: "\(documentId ?? "")#r\(renditionIndex)",
                            focusRegion: focusRegion,
                            scale: $scale,
                            cursorPosition: $cursorPosition,
                            imageSize: $imageSize,
                            geometry: $geometry,
                            minScale: minScale,
                            maxScale: maxScale,
                            loupeEnabled: loupeEnabled,
                            loupeLocked: loupeLocked,
                            loupeMagnification: Binding(
                                get: { CGFloat(loupeMagnification) },
                                set: { loupeMagnification = Double($0) }
                            ),
                            loupeSize: Binding(
                                get: { CGFloat(loupeSize) },
                                set: { loupeSize = Double($0) }
                            ),
                            coordinator: $imageCoordinator
                        )
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                        .overlay(alignment: .topLeading) {
                            boxOverlays
                        }
                    } else {
                        ProgressView()
                            .controlSize(.small)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }

                    // Bottom magnifier panel
                    if magnifierEnabled, let img = image {
                        Divider()
                        MagnifierPanelView(
                            image: img,
                            cursorPosition: magnifierPosition,
                            imageSize: imageSize,
                            magnification: Binding(
                                get: { CGFloat(panelMagnification) },
                                set: { panelMagnification = Double($0) }
                            ),
                            panelHeight: Binding(
                                get: { CGFloat(panelHeight) },
                                set: { panelHeight = Double($0) }
                            ),
                            isLocked: $magnifierLocked,
                            onLockToggle: {
                                if !magnifierLocked {
                                    // Locking - save the current magnifier position
                                    lockedPosition = cursorPosition
                                }
                                magnifierLocked.toggle()
                            }
                        )
                        .frame(height: CGFloat(panelHeight))
                    }
                }
                .background(Color(nsColor: .windowBackgroundColor))

                // Mini-map navigator (top right) - show when zoomed in (visible rect < full) or loupe active.
                // The visible window starts at (0,0,0,0) before layout completes,
                // which would pass the "< 0.99" zoom check and flash the minimap on
                // every image load (#771). `isMeasured` is that same guard, now
                // expressed once on the geometry value instead of re-derived here.
                let isActuallyZoomed = geometry.isMeasured
                    && (geometry.visible.width < 0.99 || geometry.visible.height < 0.99)
                if let img = image, isActuallyZoomed || loupeEnabled {
                    NavigatorMiniMap(
                        image: img,
                        visibleRect: geometry.visible,
                        onRectangleDragged: { normalizedOrigin in
                            imageCoordinator?.scrollToNormalizedPosition(normalizedOrigin)
                        }
                    )
                    .frame(width: 150, height: 100)
                    .padding(8)
                }
            }

            Divider()

            readerToolbar
        }
        .task(id: url) { await handleImageURLChanged() }
        .task(id: "\(documentId ?? "")|\(ocrBoxesEnabled)") { await loadOCRGeometry() }
        .task(id: documentId) { await loadRenditions() }
        .onAppear { handleViewAppeared() }
        .onChange(of: documentId) { _, _ in handleDocumentIDChanged() }
        .onReceive(NotificationCenter.default.publisher(for: .readerTextSelection)) { note in
            handleReaderTextSelection(note)
        }
        .onChange(of: annotationStore.changeToken) { _, _ in loadAnnotations() }
        .onChange(of: renderedImage) { _, newImg in handleRenderedImageChanged(newImg) }
        .onChange(of: scale) { _, newScale in handleScaleChanged(newScale) }
        .onChange(of: documentId) { _, _ in handleDocumentIDChangedForHighRes() }
        .onKeyPress(.init("+"), phases: .down) { _ in zoomIn(); return .handled }
        .onKeyPress(.init("="), phases: .down) { _ in zoomIn(); return .handled }
        .onKeyPress(.init("-"), phases: .down) { _ in zoomOut(); return .handled }
        .onKeyPress(.init("0"), phases: .down) { _ in actualSize(); return .handled }
        .onChange(of: magnifierLocked) { wasLocked, isLocked in handleMagnifierLockChanged(wasLocked, isLocked) }
        .onKeyPress(.init("9"), phases: .down) { _ in fitToWindow(); return .handled }
        // Daniel's ruling (2026-08-10, audit 3c): left/right = PREVIOUS/NEXT
        // item, up/down = pan the current image. The old unconditional pan
        // claim inverted that — with the preview focused, ←/→ panned and the
        // sibling step never fired. Pan on ←/→ only while the zoomed image
        // can actually travel horizontally; otherwise step siblings via the
        // same seam the trackpad swipe uses.
        .onKeyPress(.leftArrow, phases: .down) { _ in
            if canPanHorizontally { panLeft() } else {
                NotificationCenter.default.post(name: .previewSiblingSwipe, object: -1)
            }
            return .handled
        }
        .onKeyPress(.rightArrow, phases: .down) { _ in
            if canPanHorizontally { panRight() } else {
                NotificationCenter.default.post(name: .previewSiblingSwipe, object: 1)
            }
            return .handled
        }
        // ↑/↓ = the RENDITION axis when this page has more than one (Daniel's
        // ruling: up/down flips renditions, ←/→ walks pages) — same
        // pan-first grammar as ←/→: a zoomed image that can travel
        // vertically still pans; otherwise the keys flip.
        .onReceive(NotificationCenter.default.publisher(for: .previewRenditionSwipe)) { note in
            guard let step = note.object as? Int else { return }
            verticalStep(step)
        }
        .onKeyPress(.upArrow, phases: .down) { _ in
            if canPanVertically { panUp() } else {
                verticalStep(-1)
            }
            return .handled
        }
        .onKeyPress(.downArrow, phases: .down) { _ in
            if canPanVertically { panDown() } else {
                verticalStep(1)
            }
            return .handled
        }
        .focusedSceneValue(\.imageZoomActions, ImageZoomActions(
            zoomIn: zoomIn,
            zoomOut: zoomOut,
            actualSize: actualSize,
            zoomToFit: fitToWindow,
            canZoomIn: scale < maxScale,
            canZoomOut: scale > minScale
        ))
    }
}

#endif
