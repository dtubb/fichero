// swiftlint:disable file_length
#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import OSLog
import SwiftUI

#if os(macOS)

// MARK: - Zoomable Image Preview (with controls and magnifier)

// swiftlint:disable:next type_body_length
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
            await annotationStore.loadAnnotations(for: .document(documentId), force: true)
        }
    }

    /// Saved region boxes (normalized `[x,y,w,h]`) for the shown image.
    private var regionBoxes: [[Double]] {
        guard let documentId else { return [] }
        return annotationStore.annotations
            .filter { ($0.documentId == documentId || $0.pageId == documentId) && $0.hasRegion }
            .compactMap(\.bbox)
    }

    private func loadAnnotations() {
        guard let documentId else { return }
        Task { await annotationStore.loadAnnotations(for: .document(documentId), force: true) }
    }

    private static let logger = Logger(subsystem: "app.fichero.fichero", category: "ZoomableImagePreview")

    /// Document ids in the +/-`radius` window around `currentId`, excluding `currentId` itself.
    /// Static so it can be called in unit tests without a live view (#2469).
    static func preloadIds(from docs: [Document], currentId: String, radius: Int = 3) -> [String] {
        guard let index = docs.firstIndex(where: { $0.id == currentId }) else { return [] }
        let start = max(0, index - radius)
        let end = min(docs.count - 1, index + radius)
        guard start <= end else { return [] }
        return (start...end).compactMap { idx in idx == index ? nil : docs[idx].id }
    }

    private var scaleKey: String? {
        documentId.map { "imageZoom_\($0)" }
    }

    @SceneStorage("imagePreview.zoomScalesByDocument") private var zoomScalesByDocumentJSON: String = "{}"

    // These settings persist across image changes using AppStorage
    @AppStorage("imagePreview.magnifierEnabled") private var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("imagePreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") private var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") private var panelHeight: Double = 120.0
    @AppStorage("imagePreview.magnifierLocked") private var magnifierLocked = false
    @AppStorage("imagePreview.loupeLocked") private var loupeLocked = false

    @EnvironmentObject private var storageService: StorageServiceGenerated
    @Environment(AnnotationStore.self) private var annotationStore: AnnotationStore

    // Bounding-box annotation state (#2458). `isDrawingRegion` arms the overlay
    // drag; `pendingAnnotationTool` carries the tool kind into the saved box.
    @State private var isDrawingRegion = false
    @State private var pendingAnnotationTool: ReaderAnnotationTool = .highlight

    @State private var scale: CGFloat = 1.0
    @State private var minScale: CGFloat = 0.01
    @State private var maxScale: CGFloat = 10.0
    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Current cursor position over image
    @State private var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Position when locked
    @State private var imageSize: CGSize = .zero
    @State private var image: NSImage?
    @State private var visibleRect: CGRect = .zero  // Normalized 0-1
    @State private var imageCoordinator: ImageWithCursorTracking.Coordinator?
    // Full-resolution source image fetched lazily when zoom exceeds 1.5× (#2427).
    @State private var highResImage: NSImage?
    @State private var isLoadingHighRes = false

    private func loadSavedScale(for key: String) -> CGFloat? {
        guard let data = zoomScalesByDocumentJSON.data(using: .utf8),
              let values = try? JSONDecoder().decode([String: Double].self, from: data),
              let saved = values[key],
              saved > 0 else {
            return nil
        }
        return CGFloat(saved)
    }

    private func saveScale(_ newScale: CGFloat, for key: String) {
        var values: [String: Double] = [:]
        if let data = zoomScalesByDocumentJSON.data(using: .utf8),
           let decoded = try? JSONDecoder().decode([String: Double].self, from: data) {
            values = decoded
        }
        values[key] = Double(newScale)
        if let encoded = try? JSONEncoder().encode(values),
           let json = String(data: encoded, encoding: .utf8) {
            zoomScalesByDocumentJSON = json
        }
    }

    /// The position to use for magnifier (locked or cursor)
    private var magnifierPosition: CGPoint {
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
                                    visible: visibleRect == .zero ? CGRect(x: 0, y: 0, width: 1, height: 1) : visibleRect,
                                    isDrawing: isDrawingRegion,
                                    onCreate: { box in createAnnotation(box: box, tool: pendingAnnotationTool) }
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
        .onAppear {
            image = renderedImage ?? url.flatMap { NSImage(contentsOf: $0) }
            if let img = image {
                imageSize = img.size
            } else if renderedImage == nil {
                Self.logger.error("Failed to load NSImage from: \(url?.path ?? "<no url>")")
            }
            if let key = scaleKey {
                if let saved = loadSavedScale(for: key) {
                    scale = saved
                }
            }
            loadAnnotations()
        }
        .onChange(of: documentId) { _, _ in
            isDrawingRegion = false
            loadAnnotations()
        }
        .onChange(of: annotationStore.changeToken) { _, _ in
            loadAnnotations()
        }
        .onChange(of: url) { _, newURL in
            image = renderedImage ?? newURL.flatMap { NSImage(contentsOf: $0) }
            if let img = image {
                imageSize = img.size
            } else if renderedImage == nil {
                Self.logger.error("Failed to load NSImage from: \(newURL?.path ?? "<no url>")")
            }
            // Restore saved zoom for this scaleKey if present. Otherwise
            // leave scale untouched — the NSViewRepresentable's
            // updateNSView handles fit-to-window in the same frame as the
            // new image is set, so we don't go through a 1.0 intermediate
            // that would flash at 100%. (#773)
            if let key = scaleKey, let saved = loadSavedScale(for: key) {
                scale = saved
            }
        }
        .onChange(of: renderedImage) { _, newImg in
            // Editor mode: backend delivered a new preview frame (#1402).
            if let img = newImg {
                image = img
                imageSize = img.size
            }
        }
        .onChange(of: scale) { _, newScale in
            if let key = scaleKey {
                saveScale(newScale, for: key)
            }
            // Fetch full-res source on first zoom past 1.5× (#2427). The display
            // image is JPEG-compressed for fast loading; once zoomed the source file
            // provides the real pixel detail. Only fires once per document.
            if newScale > 1.5, highResImage == nil, !isLoadingHighRes, let docId = documentId {
                isLoadingHighRes = true
                Task {
                    if let data = try? await storageService.getSourceData(docId),
                       let img = NSImage(data: data) {
                        highResImage = img
                        image = img
                        imageSize = img.size
                    }
                    isLoadingHighRes = false
                }
            }
        }
        .onChange(of: documentId) { _, _ in
            highResImage = nil
            isLoadingHighRes = false
        }
        .onKeyPress(.init("+"), phases: .down) { _ in
            zoomIn()
            return .handled
        }
        .onKeyPress(.init("="), phases: .down) { _ in
            // Also handle = key (same as + without shift)
            zoomIn()
            return .handled
        }
        .onKeyPress(.init("-"), phases: .down) { _ in
            zoomOut()
            return .handled
        }
        .onKeyPress(.init("0"), phases: .down) { _ in
            actualSize()
            return .handled
        }
        .onChange(of: magnifierLocked) { wasLocked, isLocked in
            if isLocked && !wasLocked {
                // Locking via menu command - save current position
                lockedPosition = cursorPosition
            }
        }
        .onKeyPress(.init("9"), phases: .down) { _ in
            fitToWindow()
            return .handled
        }
        .onKeyPress(.leftArrow, phases: .down) { _ in
            panLeft()
            return .handled
        }
        .onKeyPress(.rightArrow, phases: .down) { _ in
            panRight()
            return .handled
        }
        .onKeyPress(.upArrow, phases: .down) { _ in
            panUp()
            return .handled
        }
        .onKeyPress(.downArrow, phases: .down) { _ in
            panDown()
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

    // Unified, persistent reader toolbar (#2423 / #2421) — bottom-anchored.
    // Image capabilities: zoom + magnifier-panel + loupe + image-edit +
    // annotation enabled; page-navigation renders greyed (a single image has no
    // pages). Split buttons are injected by MiniToolbar. Extracted from the body
    // so the (large) image-preview body stays under the type-checker's limit.
    private var readerToolbar: some View {
        ReaderToolbar(
            pageNav: nil,
            scalePercent: Int(scale * 100),
            zoomIn: zoomIn,
            zoomOut: zoomOut,
            fitToWindow: fitToWindow,
            actualSize: actualSize,
            magnifierEnabled: $magnifierEnabled,
            loupeEnabled: $loupeEnabled,
            loupeLocked: $loupeLocked,
            loupeMagnification: $loupeMagnification,
            isEditing: isEditing,
            onAnnotate: requestAnnotation
        )
    }

    // MARK: - Zoom Actions

    private func zoomIn() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = min(scale * 1.25, maxScale)
        }
    }

    private func zoomOut() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = max(scale / 1.25, minScale)
        }
    }

    private func fitToWindow() {
        if let fitScale = imageCoordinator?.calculateFitScale() {
            scale = fitScale
            // Defer center to next run loop so magnification has applied
            DispatchQueue.main.async {
                imageCoordinator?.centerContent()
            }
        }
    }

    private func actualSize() {
        // #599: pixel 1:1 — one image pixel per display point. Setting
        // `scale = 1.0` (NSScrollView.magnification = 1.0) shows the image
        // at NSImage.size, which on TIFF files with DPI metadata is
        // *smaller* than the actual pixel dimensions — a 300 DPI TIFF at
        // 1200×900 pixels reports `size == 288×216 points`, so
        // magnification=1.0 shrinks the image to DPI-logical size, not
        // actual pixels. The ratio of pixelsWide to size.width gives the
        // magnification that maps one image pixel to one display point,
        // matching Preview.app's Actual Size / ⌘⌥0 behaviour on macOS.
        // Falls back to 1.0 if the image has no representations (vector
        // or corrupt TIFF) or if pixel ratio exceeds the current clamp
        // — maxScale=10 is a reasonable ceiling for a UI affordance.
        let pixelRatio: CGFloat
        if let image,
           let rep = image.representations.first,
           image.size.width > 0 {
            pixelRatio = CGFloat(rep.pixelsWide) / image.size.width
        } else {
            pixelRatio = 1.0
        }
        scale = min(max(pixelRatio, minScale), maxScale)
        DispatchQueue.main.async {
            imageCoordinator?.centerContent()
        }
    }

    private func panLeft() {
        panBy(deltaX: -80, deltaY: 0)
    }

    private func panRight() {
        panBy(deltaX: 80, deltaY: 0)
    }

    private func panUp() {
        panBy(deltaX: 0, deltaY: 80)
    }

    private func panDown() {
        panBy(deltaX: 0, deltaY: -80)
    }

    private func panBy(deltaX: CGFloat, deltaY: CGFloat) {
        imageCoordinator?.panBy(
            x: deltaX / max(scale, 0.01),
            y: deltaY / max(scale, 0.01)
        )
    }
}

#else

struct ZoomableImagePreview: View {
    var url: URL?
    var documentId: String?
    var renderedImage: PlatformImage?
    /// Fired when the user steps to a sibling image in the folder image viewer.
    var onNavigateToDocument: ((String) -> Void)?
    /// API parity with the macOS variant so the shared `DocumentCanvas` call
    /// site compiles on every platform. The image editor is macOS-only, so this
    /// is unused here. (#2421)
    var isEditing: Binding<Bool>?

    init(
        url: URL? = nil,
        documentId: String? = nil,
        renderedImage: PlatformImage? = nil,
        onNavigateToDocument: ((String) -> Void)? = nil,
        isEditing: Binding<Bool>? = nil
    ) {
        self.url = url
        self.documentId = documentId
        self.renderedImage = renderedImage
        self.onNavigateToDocument = onNavigateToDocument
        self.isEditing = isEditing
    }

    @Environment(DocumentStore.self) private var documentStore
    @EnvironmentObject private var storageService: StorageServiceGenerated
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    @State private var scale: CGFloat = 1.0
    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @State private var imageSize: CGSize = .zero
    @State private var visibleRect: CGRect = .zero
    @State private var loupeMagnification: CGFloat = 3.0
    @State private var loupeSize: CGFloat = 150.0
    @State private var loupeEnabled: Bool = false
    @State private var loupeLocked: Bool = false
    @State private var imageCoordinator: ImageWithCursorTracking.Coordinator?

    /// Drives the iPhone true-full-screen presentation (#2607). Compact only.
    @State private var showingFullScreen = false

    private let minScale: CGFloat = 0.01
    private let maxScale: CGFloat = 10.0

    private var isCompact: Bool {
        horizontalSizeClass == .compact
    }

    private var hasImage: Bool {
        renderedImage != nil || url != nil
    }

    /// Image/page siblings in the current folder, in display order.
    private var siblingImageDocs: [Document] {
        guard documentId != nil else { return [] }
        return documentStore.currentDocuments.filter { $0.fileType == .image || $0.docType == .page }
    }

    private var currentImageIndex: Int? {
        guard let documentId else { return nil }
        return siblingImageDocs.firstIndex(where: { $0.id == documentId })
    }

    private var previousAction: (() -> Void)? {
        guard let onNavigateToDocument,
              let index = currentImageIndex,
              index > 0 else { return nil }
        let target = siblingImageDocs[index - 1]
        return { onNavigateToDocument(target.id) }
    }

    private var nextAction: (() -> Void)? {
        guard let onNavigateToDocument,
              let index = currentImageIndex,
              index < siblingImageDocs.count - 1 else { return nil }
        let target = siblingImageDocs[index + 1]
        return { onNavigateToDocument(target.id) }
    }

    /// Document ids in the +/-`radius` window around `currentId`, excluding `currentId` itself.
    /// Static so it can be called in unit tests without a live view (#2469).
    static func preloadIds(from docs: [Document], currentId: String, radius: Int = 3) -> [String] {
        guard let index = docs.firstIndex(where: { $0.id == currentId }) else { return [] }
        let start = max(0, index - radius)
        let end = min(docs.count - 1, index + radius)
        guard start <= end else { return [] }
        return (start...end).compactMap { idx in idx == index ? nil : docs[idx].id }
    }

    var body: some View {
        VStack(spacing: 0) {
            MiniToolbar {
                Spacer(minLength: 0)
                if isCompact {
                    Text("\(Int(scale * 100))%")
                        .font(.caption)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)

                    if hasImage {
                        Button {
                            showingFullScreen = true
                        } label: {
                            Image(systemName: "arrow.up.left.and.arrow.down.right")
                        }
                        .buttonStyle(.plain)
                        .padding(.leading, 8)
                        .accessibilityIdentifier("enterFullScreenImage")
                        .accessibilityLabel("View Full Screen")
                    }
                } else {
                    Button(action: zoomOut) {
                        Image(systemName: "minus.magnifyingglass")
                    }
                    .buttonStyle(.plain)
                    .help("Zoom Out")

                    Text("\(Int(scale * 100))%")
                        .font(.caption)
                        .monospacedDigit()
                        .frame(width: 50)

                    Button(action: zoomIn) {
                        Image(systemName: "plus.magnifyingglass")
                    }
                    .buttonStyle(.plain)
                    .help("Zoom In")

                    Divider()
                        .frame(height: 16)

                    Button(action: fitToWindow) {
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                    }
                    .buttonStyle(.plain)
                    .help("Fit to Window")

                    Button(action: actualSize) {
                        Image(systemName: "1.square")
                    }
                    .buttonStyle(.plain)
                    .help("Actual Size (100%)")

                    // Immersive full-screen entry on iPad regular width too, not
                    // just iPhone-compact. Reuses the #2607 FullScreenImagePreview
                    // cover (black background, page-only, zoom) — no parallel
                    // viewer (#2520; #2487 is a duplicate of this).
                    if hasImage {
                        Divider()
                            .frame(height: 16)

                        Button {
                            showingFullScreen = true
                        } label: {
                            Image(systemName: "viewfinder")
                        }
                        .buttonStyle(.plain)
                        .help("View Full Screen")
                        .accessibilityIdentifier("enterFullScreenImageRegular")
                        .accessibilityLabel("View Full Screen")
                    }
                }

                Spacer()
            }

            Divider()

            ZStack(alignment: .bottom) {
                Group {
                    if renderedImage != nil || url != nil {
                        ImageWithCursorTracking(
                            url: url,
                            overrideImage: renderedImage,
                            scale: $scale,
                            cursorPosition: $cursorPosition,
                            imageSize: $imageSize,
                            visibleRect: $visibleRect,
                            minScale: minScale,
                            maxScale: maxScale,
                            loupeEnabled: loupeEnabled,
                            loupeLocked: loupeLocked,
                            loupeMagnification: $loupeMagnification,
                            loupeSize: $loupeSize,
                            coordinator: $imageCoordinator
                        )
                    } else {
                        ContentUnavailableView(
                            "Image Preview",
                            systemImage: "photo",
                            description: Text("The image could not be loaded.")
                        )
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(white: 0.88, opacity: 1.0))
                // Tap the image to go true full-screen on iPhone and iPad
                // (#2607; extended to iPad regular width for #2520).
                .contentShape(Rectangle())
                .onTapGesture {
                    if hasImage {
                        showingFullScreen = true
                    }
                }

                // iOS touch prev/next overlay for folder image siblings (#2420).
                if previousAction != nil || nextAction != nil {
                    HStack(spacing: 16) {
                        Button {
                            previousAction?()
                        } label: {
                            Image(systemName: "chevron.left")
                                .font(.title3.weight(.semibold))
                                .frame(width: 40, height: 40)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(previousAction == nil)
                        .help("Show the previous image in this folder")
                        .accessibilityIdentifier("folderImagePrev")

                        Button {
                            nextAction?()
                        } label: {
                            Image(systemName: "chevron.right")
                                .font(.title3.weight(.semibold))
                                .frame(width: 40, height: 40)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(nextAction == nil)
                        .help("Show the next image in this folder")
                        .accessibilityIdentifier("folderImageNext")
                    }
                    .padding(.bottom, 16)
                    .padding(.horizontal, 24)
                }
            }
        }
        .task(id: documentId) {
            guard let docId = documentId else { return }
            let neighbors = Self.preloadIds(from: siblingImageDocs, currentId: docId)
            guard !neighbors.isEmpty else { return }
            await storageService.prefetchDisplayImages(neighbors)
        }
        // True full-screen image/page viewer for iPhone (#2607): edge-to-edge,
        // black background, no title/back/chrome, swipe-down or close to exit.
        .fullScreenCover(isPresented: $showingFullScreen) {
            FullScreenImagePreview(url: url, renderedImage: renderedImage)
        }
    }

    // MARK: - Zoom Actions

    private func zoomIn() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = min(scale * 1.25, maxScale)
        }
    }

    private func zoomOut() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = max(scale / 1.25, minScale)
        }
    }

    private func fitToWindow() {
        if let fitScale = imageCoordinator?.calculateFitScale() {
            scale = fitScale
            DispatchQueue.main.async {
                imageCoordinator?.centerContent()
            }
        }
    }

    private func actualSize() {
        scale = 1.0
        DispatchQueue.main.async {
            imageCoordinator?.centerContent()
        }
    }
}

#if canImport(UIKit)
/// True full-screen image/page presentation for iPhone (#2607).
///
/// The inline `ZoomableImagePreview` lives inside a `NavigationStack` detail
/// on iPhone, so it carries a title bar, back button, and the mini-toolbar —
/// which waste most of a small screen when you just want to read the source.
/// This cover fills the entire screen edge-to-edge on a black background with
/// no chrome, reusing `ImageWithCursorTracking` so pinch-zoom/pan come for
/// free (no parallel image stack). A close button always dismisses; a
/// downward swipe does too when the image isn't being panned.
struct FullScreenImagePreview: View {
    let url: URL?
    let renderedImage: PlatformImage?

    @Environment(\.dismiss) private var dismiss

    @State private var scale: CGFloat = 1.0
    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @State private var imageSize: CGSize = .zero
    @State private var visibleRect: CGRect = .zero
    @State private var loupeMagnification: CGFloat = 3.0
    @State private var loupeSize: CGFloat = 150.0
    @State private var imageCoordinator: ImageWithCursorTracking.Coordinator?
    @State private var dragOffset: CGFloat = 0

    private let minScale: CGFloat = 0.01
    private let maxScale: CGFloat = 10.0

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()

            if renderedImage != nil || url != nil {
                ImageWithCursorTracking(
                    url: url,
                    overrideImage: renderedImage,
                    scale: $scale,
                    cursorPosition: $cursorPosition,
                    imageSize: $imageSize,
                    visibleRect: $visibleRect,
                    minScale: minScale,
                    maxScale: maxScale,
                    loupeEnabled: false,
                    loupeLocked: false,
                    loupeMagnification: $loupeMagnification,
                    loupeSize: $loupeSize,
                    coordinator: $imageCoordinator
                )
                .ignoresSafeArea()
            } else {
                ContentUnavailableView(
                    "Image Preview",
                    systemImage: "photo",
                    description: Text("The image could not be loaded.")
                )
                .foregroundStyle(.white)
            }

            // Close affordance — respects the safe area so it stays tappable
            // under the notch / Dynamic Island.
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(12)
                    .background(.ultraThinMaterial, in: Circle())
            }
            .padding(.top, 8)
            .padding(.trailing, 16)
            .help("Close full-screen image")
            .accessibilityIdentifier("fullScreenImageClose")
            .accessibilityLabel("Close Full Screen")
        }
        .offset(y: dragOffset)
        .gesture(
            DragGesture(minimumDistance: 20)
                .onChanged { value in
                    if value.translation.height > 0 {
                        dragOffset = value.translation.height
                    }
                }
                .onEnded { value in
                    if value.translation.height > 120 {
                        dismiss()
                    } else {
                        withAnimation(.spring(response: 0.3)) { dragOffset = 0 }
                    }
                }
        )
        #if os(iOS)
        .statusBarHidden(true)
        #endif
    }
}

#Preview("Compact Zoomable Image Preview") {
    ZoomableImagePreview(renderedImage: UIImage(systemName: "photo"))
        .environmentObject(StorageServiceGenerated(ficheroClient: FicheroClient(libraryPath: nil)))
        .frame(width: 280, height: 360)
}
#endif

#endif
