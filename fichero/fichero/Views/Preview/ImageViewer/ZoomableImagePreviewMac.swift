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

    init(
        url: URL? = nil,
        documentId: String? = nil,
        renderedImage: NSImage? = nil,
        onNavigateToDocument: ((String) -> Void)? = nil,
        isEditing: Binding<Bool>? = nil
    ) {
        self.url = url
        self.documentId = documentId
        self.renderedImage = renderedImage
        self.onNavigateToDocument = onNavigateToDocument
        self.isEditing = isEditing
    }

    /// Annotation tools from the reader toolbar (#2458). Highlight/Note arm a
    /// region draw over the image; the resulting normalized box is persisted as
    /// a bounding-box annotation. Bookmark is a whole-image marker (no region).
    private func requestAnnotation(_ tool: ReaderAnnotationTool) {
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
    private func createAnnotation(box: [Double]?, tool: ReaderAnnotationTool) {
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
            .compactMap(\.bbox)
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

    // Bounding-box annotation state (#2458). `isDrawingRegion` arms the overlay
    // drag; `pendingAnnotationTool` carries the tool kind into the saved box.
    @State var isDrawingRegion = false
    @State var pendingAnnotationTool: ReaderAnnotationTool = .highlight

    // OCR text-box overlay (#4309): the transcription pass's word/line boxes
    // rendered over the page image, fetched from the artifact API on demand.
    // The loader lives in OCRGeometryOverlay.swift to keep this body lean.
    @AppStorage("imagePreview.ocrBoxesEnabled") var ocrBoxesEnabled = false
    @State var ocrGeometry: OCRGeometry?

    @State var scale: CGFloat = 1.0
    @State var minScale: CGFloat = 0.01
    @State var maxScale: CGFloat = 10.0
    @State var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Current cursor position over image
    @State var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Position when locked
    @State var imageSize: CGSize = .zero
    @State var image: NSImage?
    @State var visibleRect: CGRect = .zero  // Normalized 0-1
    @State var imageCoordinator: ImageWithCursorTracking.Coordinator?
    // Full-resolution source image fetched lazily when zoom exceeds 1.5× (#2427).
    @State var highResImage: NSImage?
    @State var isLoadingHighRes = false

    // Zoom actions live in ZoomableImagePreviewMac+ZoomActions.swift and the
    // opening-zoom rule in PreviewInitialZoomPolicy.swift (moved/extracted to
    // keep this body under the type-body-length budget).

    /// The position to use for magnifier (locked or cursor)
    var magnifierPosition: CGPoint {
        magnifierLocked ? lockedPosition : cursorPosition
    }

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
                            overrideImage: highResImage ?? renderedImage,
                            scale: $scale,
                            cursorPosition: $cursorPosition,
                            imageSize: $imageSize,
                            visibleRect: $visibleRect,
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
                        .overlay {
                            // Saved bounding boxes + the region-draw layer (#2458).
                            // Shown whenever there are boxes or the tool is armed.
                            if !regionBoxes.isEmpty || isDrawingRegion {
                                BoundingBoxOverlay(
                                    boxes: regionBoxes,
                                    visible: visibleRect == .zero
                                        ? CGRect(x: 0, y: 0, width: 1, height: 1)
                                        : visibleRect,
                                    isDrawing: isDrawingRegion,
                                    onCreate: { box in createAnnotation(box: box, tool: pendingAnnotationTool) }
                                )
                            }
                            // OCR text boxes from the transcription pass (#4309),
                            // toggled from the reader toolbar.
                            if ocrBoxesEnabled, let ocrGeometry {
                                OCRGeometryOverlay(
                                    geometry: ocrGeometry,
                                    visible: visibleRect == .zero
                                        ? CGRect(x: 0, y: 0, width: 1, height: 1)
                                        : visibleRect
                                )
                            }
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
                .background(Color(white: 0.88, opacity: 1.0))

                // Mini-map navigator (top right) - show when zoomed in (visible rect < full) or loupe active.
                // visibleRect starts at (0,0,0,0) before layout completes, which would
                // pass the "< 0.99" zoom check and flash the minimap on every image
                // load (#771). Require positive area so the predicate only fires once
                // the viewport has actually measured the image.
                let visibleRectIsMeasured = visibleRect.width > 0 && visibleRect.height > 0
                let isActuallyZoomed = visibleRectIsMeasured
                    && (visibleRect.width < 0.99 || visibleRect.height < 0.99)
                if let img = image, isActuallyZoomed || loupeEnabled {
                    NavigatorMiniMap(
                        image: img,
                        visibleRect: visibleRect,
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
        .onAppear { handleViewAppeared() }
        .onChange(of: documentId) { _, _ in handleDocumentIDChanged() }
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
        .onKeyPress(.leftArrow, phases: .down) { _ in panLeft(); return .handled }
        .onKeyPress(.rightArrow, phases: .down) { _ in panRight(); return .handled }
        .onKeyPress(.upArrow, phases: .down) { _ in panUp(); return .handled }
        .onKeyPress(.downArrow, phases: .down) { _ in panDown(); return .handled }
        .focusedSceneValue(\.imageZoomActions, ImageZoomActions(
            zoomIn: zoomIn,
            zoomOut: zoomOut,
            actualSize: actualSize,
            zoomToFit: fitToWindow,
            canZoomIn: scale < maxScale,
            canZoomOut: scale > minScale
        ))
    }

    // Unified, persistent reader toolbar (#2423 / #2421) — bottom-anchored.
    // Image capabilities: zoom + magnifier-panel + loupe + image-edit +
    // annotation enabled; page-navigation renders greyed (a single image has no
    // pages). Split buttons are injected by MiniToolbar. Extracted from the body
    // so the (large) image-preview body stays under the type-checker's limit.
    var readerToolbar: some View {
        ReaderToolbar(
            pageNav: nil,
            scalePercent: Int(scale * 100),
            zoomIn: zoomIn,
            zoomOut: zoomOut,
            fitToWindow: fitToWindow,
            actualSize: actualSize,
            magnifierEnabled: $magnifierEnabled,
            textBoxesEnabled: $ocrBoxesEnabled,
            loupeEnabled: $loupeEnabled,
            loupeLocked: $loupeLocked,
            loupeMagnification: $loupeMagnification,
            isEditing: isEditing,
            onAnnotate: requestAnnotation
        )
    }
}

#endif
