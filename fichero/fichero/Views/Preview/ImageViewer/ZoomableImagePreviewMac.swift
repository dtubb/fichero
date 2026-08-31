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
    /// The rendition `renderedImage`'s pixels already ARE (preferred-first
    /// canvas path, 2026-08-24) — loadRenditions lands here without a fetch.
    var renderedRenditionId: String?
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
        renderedRenditionId: String? = nil,
        onNavigateToDocument: ((String) -> Void)? = nil,
        isEditing: Binding<Bool>? = nil,
        highlightBoxes: [[Double]] = [],
        focusRegion: [Double]? = nil,
        onContainmentStep: ((Int) -> Bool)? = nil
    ) {
        self.url = url
        self.documentId = documentId
        self.renderedImage = renderedImage
        self.renderedRenditionId = renderedRenditionId
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
    /// Optional: geometry reloads when a run finishes (2026-08-25 — a fresh
    /// Detect Regions run wrote 52 good boxes and the overlay kept showing
    /// the stale ones until the document was switched). Artifact change
    /// events don't reach the client stream yet; run completion is the
    /// signal the app already observes.
    @Environment(WorkflowExecutionObserver.self) var executionObserver: WorkflowExecutionObserver?
    /// Optional: per-window ephemeral marquee seam (2026-08-29). Previews and
    /// hosts without a WindowState simply have no marquee surface.
    @Environment(WindowState.self) var windowState: WindowState?

    // Bounding-box annotation state (#2458). `isDrawingRegion` arms the overlay
    // drag; `pendingAnnotationTool` carries the tool kind into the saved box.
    @State var isDrawingRegion = false
    @State var pendingAnnotationTool: ReaderAnnotationTool = .highlight

    /// The pane head's chrome seam (Daniel, 2026-08-29): paging + renditions
    /// publish here so the head renders them. Optional — headless hosts skip.
    @Environment(PreviewPaneChrome.self) var paneChrome: PreviewPaneChrome?

    /// ⌥ summons the loupe temporarily while it is toggled off (Daniel,
    /// 2026-08-29); releasing ⌥ lets it go.
    @State var loupeTransient = false
    /// Cursor feedback for the armed markup tool (Daniel, 2026-08-30).
    @State var hoveringCanvas = false
    @State private var optionMonitor: Any?

    /// The loupe the tracking view actually shows: the toggle, or ⌥ held.
    var loupeIsOn: Bool { loupeEnabled || loupeTransient }

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
    /// Annotation overlays show/hide (what-to-show menu, 2026-08-30). ON by
    /// default (Daniel, 2026-08-31): his container had this key stuck at 0,
    /// so every mark the markup row drew saved correctly and then rendered
    /// invisible — indistinguishable from markup that doesn't work. The
    /// dead-simple-UX rule settles it: the feature is on.
    @AppStorage("preview.annotationsEnabled") var annotationsEnabled = true
    /// Saved region marks show/hide (2026-08-31) — the untyped/legacy boxes
    /// in the mark layer, as distinct from the typed markup kinds. Separate
    /// from `annotationsEnabled` because "hide my highlights" and "hide the
    /// region grid" are different questions.
    @AppStorage("preview.regionsEnabled") var regionsEnabled = true
    /// Draw each recognised word's text inside its box (2026-08-31). The
    /// display lives in `OCRGeometryOverlay`, which reads the same key.
    @AppStorage("imagePreview.inlineTextEnabled") var inlineTextEnabled = false
    @State var ocrGeometry: OCRGeometry?
    /// WHICH artifact the displayed geometry came from (2026-08-29, regions
    /// as first-class): the curation verbs — move / delete / add / combine —
    /// must address the artifact whose boxes are on screen, so the id rides
    /// with the boxes instead of being re-guessed at commit time.
    @State var ocrGeometryArtifactId: String?
    /// Rubber-band add mode: drags draw EPHEMERAL marquees (per-window seam
    /// `WindowState.previewMarquees`) — nothing persists until the user
    /// promotes them to regions or runs a workflow scoped to the crops.
    @State var isAddingRegion = false

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
    /// S6 (Daniel, 2026-08-23): a sibling step resets to FIT-ALL — a tall
    /// item must not arrive overflowing at the previous item's scale. Armed
    /// on document change, consumed when the new image lands.
    @State var pendingFitOnNextImage = false
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

    // Zoom actions: +ZoomActions.swift; opening-zoom rule:
    // PreviewInitialZoomPolicy.swift (extracted for the type-body budget).

    /// Split into bounded layer properties: two lanes' merged modifier chain
    /// blew the type-checker budget — the same pathology the library window
    /// hit — and each layer keeps its chain small enough to check.
    var body: some View {
        keyboardLayer
            .focusedSceneValue(\.imageZoomActions, ImageZoomActions(
                zoomIn: zoomIn,
                zoomOut: zoomOut,
                actualSize: actualSize,
                zoomToFit: fitToWindow,
                canZoomIn: scale < maxScale,
                canZoomOut: scale > minScale
            ))
            // ⌘A over the preview (Daniel, 2026-08-31): the armed tool decides
            // — text tool selects every WORD, select tool every displayed box.
            // Published, not key-handled: `SelectAllButton` owns the chord.
            .focusedSceneValue(
                \.previewSelectAll,
                FocusedLibraryAction(
                    isEnabled: ocrGeometry?.boxes.isEmpty == false,
                    run: { selectAllGeometryForArmedTool() }
                )
            )
    }

    /// Layer 1: content + lifecycle (tasks, appear/disappear, chrome publish).
    private var lifecycleLayer: some View {
        VStack(spacing: 0) {
            // Canvas (image + overlays + magnification cluster + magnifier
            // strip) — extracted to +Overlays.swift 2026-08-29 (length budget).
            canvasArea

            Divider()

            readerToolbar
        }
        .task(id: url) { await handleImageURLChanged() }
        .task(
            // FocusedArtifact.shared.id is part of the task identity so
            // selecting an artifact in the inspector re-runs the geometry
            // load — the selection now drives which artifact's boxes render.
            id: "\(documentId ?? "")|\(ocrBoxesEnabled)"
                + "|\(executionObserver?.activeExecutions.count ?? 0)"
                + "|\(FocusedArtifact.shared.id ?? "")"
        ) { await loadOCRGeometry() }
        .task(id: documentId) {
            await loadRenditions()
            publishHeadChrome()
        }
        .onAppear {
            handleViewAppeared()
            publishHeadChrome()
            installOptionLoupeMonitor()
        }
        .onDisappear { removeOptionLoupeMonitor() }
        .onChange(of: renditionIndex) { _, _ in publishHeadChrome() }
    }

    /// Layer 2: notification + change observation.
    private var observationLayer: some View {
        lifecycleLayer
            // The head's markup row (Daniel, 2026-08-29): highlight and note
            // arm the same region-draw path the bottom bar's buttons used to.
            .onReceive(NotificationCenter.default.publisher(for: .previewAnnotateTool)) { note in
                guard let raw = note.object as? String,
                      let tool = PreviewMarkupTool(rawValue: raw) else { return }
                switch tool {
                case .highlight: requestAnnotation(.highlight)
                case .note: requestAnnotation(.note)
                case .star: requestAnnotation(.bookmark)
                case .line: requestAnnotation(.line)
                case .textSelect, .select, .wordSelect, .drawRegion, .check:
                    break  // preview-regions interactions / reader-only
                }
            }
            .onChange(of: documentId) { _, _ in handleDocumentIDChanged() }
            .onReceive(NotificationCenter.default.publisher(for: .readerTextSelection)) { note in
                handleReaderTextSelection(note)
            }
            .onChange(of: annotationStore.changeToken) { _, _ in loadAnnotations() }
            .onChange(of: renderedImage) { _, newImg in handleRenderedImageChanged(newImg) }
            .onChange(of: scale) { _, newScale in handleScaleChanged(newScale) }
            .onChange(of: documentId) { _, _ in handleDocumentIDChangedForHighRes() }
            .onChange(of: magnifierLocked) { wasLocked, isLocked in
                handleMagnifierLockChanged(wasLocked, isLocked)
            }
            // Sticky markup tool (Daniel, 2026-08-30): arming highlight/note
            // in the bar arms the draw layer; disarming (or switching to a
            // non-drawing tool) stands it down. Cursor follows.
            .onChange(of: windowState?.activeMarkupTool) { _, tool in
                switch tool {
                case .highlight: pendingAnnotationTool = .highlight; isDrawingRegion = true
                case .note: pendingAnnotationTool = .note; isDrawingRegion = true
                case .line: pendingAnnotationTool = .line; isDrawingRegion = true
                case .star: pendingAnnotationTool = .bookmark; isDrawingRegion = true
                // The bar's Draw Region arms the SAME rubber-band add mode
                // the context menu's "Add Region…" uses (Daniel, 2026-08-31:
                // "draw region doesn't do anything") — drawn marquees are the
                // existing ephemeral-region flow, ▶ crops them into nodes.
                case .drawRegion:
                    isDrawingRegion = false
                    isAddingRegion = true
                default: isDrawingRegion = false
                }
                if tool != .drawRegion { isAddingRegion = false }
                applyMarkupCursor()
            }
            // ↑/↓ = the RENDITION axis when this page has more than one
            // (Daniel's ruling: up/down flips renditions, ←/→ walks pages).
            .onReceive(NotificationCenter.default.publisher(for: .previewRenditionSwipe)) { note in
                guard let step = note.object as? Int else { return }
                verticalStep(step)
            }
    }

    /// Layer 3: keyboard grammar (zoom keys, region verbs, arrow navigation).
    private var keyboardLayer: some View {
        observationLayer
            // Esc dismisses the loupe (Daniel, 2026-08-29).
            .onKeyPress(.escape, phases: .down) { _ in
                guard loupeEnabled || loupeTransient else { return .ignored }
                loupeEnabled = false; loupeTransient = false
                return .handled
            }
            .onKeyPress(.init("+"), phases: .down) { _ in zoomIn(); return .handled }
            .onKeyPress(.init("="), phases: .down) { _ in zoomIn(); return .handled }
            .onKeyPress(.init("-"), phases: .down) { _ in zoomOut(); return .handled }
            .onKeyPress(.init("0"), phases: .down) { _ in actualSize(); return .handled }
            .onKeyPress(.init("9"), phases: .down) { _ in fitToWindow(); return .handled }
            // Regions as first-class (2026-08-29): Delete removes the picked
            // marquee first (most recent, most ephemeral), else the selected
            // persisted regions; Esc clears every ephemeral region state.
            .onDeleteCommand { handleRegionDeleteKey() }
            .onExitCommand { clearEphemeralRegionState() }
            // Daniel's ruling (2026-08-10, audit 3c): left/right mean
            // PREVIOUS/NEXT item, up/down pan the current image. ←/→ pan
            // only when the zoomed image can actually travel horizontally;
            // otherwise they step siblings via the trackpad-swipe seam.
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
    }
}

// MARK: - Head chrome + ⌥-loupe (Daniel, 2026-08-29). Same-file extension:
// `private` stays visible; the struct body stays under its length budget.

extension ZoomableImagePreview {
    /// Publish paging + renditions to the head's chrome seam (mount and
    /// document/rendition change) — last-writer-wins across splits, same as
    /// the focused zoom actions.
    func publishHeadChrome() {
        guard let paneChrome else { return }
        paneChrome.pageNav = imagePageNav
        paneChrome.renditionNames = renditions.map(\.displayName)
        paneChrome.renditionIndex = renditionIndex
        paneChrome.selectRendition = { index in self.flipRendition(to: index) }
    }

    /// ⌥ held while the loupe is OFF summons it temporarily; release lets it
    /// go. A toggled-on loupe is untouched.
    private func installOptionLoupeMonitor() {
        guard optionMonitor == nil else { return }
        optionMonitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { event in
            MainActor.assumeIsolated {  // local monitors fire on main
                let optionHeld = event.modifierFlags.contains(.option)
                if loupeTransient != (optionHeld && !loupeEnabled) {
                    loupeTransient = optionHeld && !loupeEnabled
                }
            }
            return event
        }
    }

    private func removeOptionLoupeMonitor() {
        if let optionMonitor {
            NSEvent.removeMonitor(optionMonitor)
        }
        optionMonitor = nil
        loupeTransient = false
    }
}

#endif
