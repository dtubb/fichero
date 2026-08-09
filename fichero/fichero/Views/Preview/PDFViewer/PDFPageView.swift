import PDFKit
import SwiftUI

#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif

// PDFZoomController + PDFPageController moved to PDFPageControllers.swift (#3041).

// MARK: - PDFPageView

#if canImport(AppKit)

/// PDFView that switches autoScales off the moment a pinch BEGINS (#4125):
/// with autoScales still on at gesture start, PDFKit re-fit the document
/// mid-first-pinch — the visible snap-back-to-fit — before the scale-change
/// observer could flip it off. Disabling at the gesture boundary preserves
/// #588's initial-fit-through-layout-passes while making the first pinch
/// behave like every later one.
final class PinchOwningPDFView: PDFView {
    /// Set by `PDFPageView` so a pinch is recorded as the user taking over the
    /// zoom, which stops the automatic re-fit on pane resize (#4279).
    var onUserMagnify: (@MainActor () -> Void)?

    override func magnify(with event: NSEvent) {
        onUserMagnify?()
        if autoScales {
            autoScales = false
        }
        super.magnify(with: event)
    }
}

/// Interactive PDF preview using PDFKit's `PDFView`.
///
/// Where `PDFThumbnailView` renders a flat `NSImage` (cheap, cacheable, fine
/// for grid/sidebar thumbnails), `PDFPageView` uses the full AppKit `PDFView`
/// so users get **selectable text, copy, find, and links** — everything a real
/// PDF reader provides. Used in the main preview pane for `.page` documents
/// (#578) and for top-level `.file`+`.pdf` documents.
///
/// Always uses `.singlePage` mode (#595): the page is the canonical unit.
/// Horizontal trackpad swipe navigates to the next/previous page when the
/// document is at fit-scale; when zoomed in, swipe pans normally.
struct PDFPageView: NSViewRepresentable {
    let documentId: String
    let pageIndex: Int
    /// Fires when the user swipes to a different page.
    /// The index is 0-based into the PDF document.
    var onPageIndexChange: ((Int) -> Void)?
    /// Optional zoom controller — set by PDFPageWithToolbar to sync the toolbar.
    var zoomController: PDFZoomController?
    /// Optional page controller — set by PDFPageWithToolbar so the document
    /// toolbar's ◀ N/M ▶ cluster can drive and reflect the current page. (#1531)
    var pageController: PDFPageController?
    var onCursorMoved: ((CGPoint) -> Void)?
    /// Saved bounding-box regions for the current page, normalized `[x,y,w,h]`
    /// (top-left origin). Rendered as native PDFKit square annotations (#2458).
    var regionBoxes: [[Double]] = []
    /// Recognised text regions for the current page (#4418). Rendered as
    /// outline annotations by `applyOCRBoxes`; empty means draw none.
    var ocrBoxes: [OCRGeometryBox] = []
    /// When true, a drag draws a new region instead of turning the page.
    var isDrawingRegion = false
    /// Fires with a normalized `[x,y,w,h]` when a region drag completes.
    var onCreateRegion: (([Double]) -> Void)?
    /// PDF page-arrangement mode (#2090). Default preserves the single-page
    /// behavior for callers that don't opt into layout switching.
    var displayMode: PDFDisplayMode = .singlePage
    /// Page-turn axis (2026-08-09): horizontal for paged spreads (book),
    /// vertical only for continuous modes. See PageLayoutMode.pdfDisplayDirection.
    var displayDirection: PDFDisplayDirection = .horizontal

    // MARK: - Loupe State

    @AppStorage("pdfPreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("pdfPreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("pdfPreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("pdfPreview.loupeLocked") private var loupeLocked = false

    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @State private var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @Environment(StorageService.self) private var storageService

    // PinchOwningPDFView lives at file scope (above) so this struct stays
    // within the type-body-length budget.

    func makeCoordinator() -> Coordinator {
        Coordinator(
            owner: self,
            loupeEnabled: $loupeEnabled,
            cursorPosition: $cursorPosition,
            lockedPosition: $lockedPosition
        )
    }

    func makeNSView(context: Context) -> PDFView {
        let view = PinchOwningPDFView()
        view.setAccessibilityIdentifier("pdfPreview")  // XCUITest hook (#1230)
        view.displayMode = displayMode
        view.displayDirection = displayDirection
        view.displaysPageBreaks = false
        // autoScales re-fits the document to the pane on every layout pass.
        // That is exactly what we want until the user zooms — it is how a PDF
        // opens fitted and stays fitted as the pane resizes (#4279, the vector
        // branch of PreviewInitialZoomPolicy). #588's concern — autoScales
        // silently undoing a pinch — is handled by the scale observer below,
        // which flips it off once `userHasZoomedManually` is set.
        view.autoScales = true
        view.backgroundColor = NSColor(red: 253/255, green: 253/255, blue: 253/255, alpha: 1)
        view.delegate = context.coordinator
        context.coordinator.pdfView = view
        context.coordinator.zoomController = zoomController
        context.coordinator.pageController = pageController
        zoomController?.pdfView = view
        pageController?.pdfView = view
        wireZoomOwnership(context.coordinator, on: view)
        registerObservers(context.coordinator, on: view)
        // Horizontal pan at fit-scale = page turn (#595).
        let pan = NSPanGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handlePan(_:))
        )
        pan.delegate = context.coordinator
        view.addGestureRecognizer(pan)
        // Register for tracking area updates
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.updateTrackingAreas(_:)),
            name: NSView.frameDidChangeNotification,
            object: view
        )
        context.coordinator.updateTrackingAreas(
            Notification(name: NSView.frameDidChangeNotification, object: view)
        )
        context.coordinator.loadAndNavigate(
            view,
            documentId: documentId,
            storageService: storageService
        )
        return view
    }

    func updateNSView(_ view: PDFView, context: Context) {
        context.coordinator.owner = self
        // Apply the page-layout mode (#2090); idempotent-guarded so switching
        // modes updates the live view without churning PDFKit every pass.
        if view.displayMode != displayMode { view.displayMode = displayMode }
        if view.displayDirection != displayDirection { view.displayDirection = displayDirection }
        context.coordinator.zoomController = zoomController
        context.coordinator.pageController = pageController
        zoomController?.pdfView = view
        pageController?.pdfView = view
        wireZoomOwnership(context.coordinator, on: view)
        context.coordinator.loadAndNavigate(
            view,
            documentId: documentId,
            storageService: storageService
        )
        context.coordinator.applyRegions(to: view)
        context.coordinator.applyOCRBoxes(to: view)
    }

    static func dismantleNSView(_ view: PDFView, coordinator: Coordinator) {
        NotificationCenter.default.removeObserver(coordinator)
        view.trackingAreas.forEach { view.removeTrackingArea($0) }
    }
}

extension PDFPageView {
    /// Bridges AppKit notifications / delegate into the SwiftUI callback.
    /// All PDFKit notification and gesture callbacks fire on the main thread,
    /// so @MainActor is correct and avoids nonisolated-context concurrency warnings.
    @MainActor
    final class Coordinator: NSObject, PDFViewDelegate, NSGestureRecognizerDelegate {
        var owner: PDFPageView
        weak var pdfView: PDFView?
        var zoomController: PDFZoomController?
        var pageController: PDFPageController?
        /// True once the user has taken manual control of the zoom — a pinch or
        /// a toolbar zoom command. While it is false PDFKit's `autoScales` stays
        /// on, so the page keeps fitting the pane as the pane resizes; a manual
        /// zoom freezes the scale until a different document loads (#4279).
        var userHasZoomedManually = false
        private var loadedDocumentId: String?
        private var requestedDocumentId: String?
        private var loadTask: Task<Void, Never>?
        // Accumulated horizontal translation for the current pan gesture.
        private var panAccumulated: CGFloat = 0
        /// Start point (in view coords) of an in-progress region-draw drag (#2458).
        private var regionDragStartView: CGPoint?

        // MARK: - Loupe Bindings

        var loupeEnabled: Binding<Bool>
        var cursorPosition: Binding<CGPoint>
        var lockedPosition: Binding<CGPoint>

        init(
            owner: PDFPageView,
            loupeEnabled: Binding<Bool>,
            cursorPosition: Binding<CGPoint>,
            lockedPosition: Binding<CGPoint>
        ) {
            self.owner = owner
            self.loupeEnabled = loupeEnabled
            self.cursorPosition = cursorPosition
            self.lockedPosition = lockedPosition
        }

        deinit {
            loadTask?.cancel()
        }

        func loadAndNavigate(
            _ view: PDFView,
            documentId: String,
            storageService: StorageService
        ) {
            if loadedDocumentId == documentId, view.document != nil {
                navigateCurrentDocument(in: view)
                return
            }
            if requestedDocumentId == documentId {
                return
            }

            requestedDocumentId = documentId
            loadedDocumentId = nil
            loadTask?.cancel()
            view.document = nil
            view.autoScales = true
            // A different document — the automatic fit owns the zoom again (#4279).
            userHasZoomedManually = false

            loadTask = Task { [weak self, weak view] in
                guard let self else { return }
                do {
                    // Shared per-document decode (#3209): one PDFDocument, reused
                    // across the viewer's split panes instead of decoding per view.
                    let pdfDocument = try await storageService.pdfCache.document(for: documentId)
                    guard !Task.isCancelled,
                          let pdfDocument,
                          let view else { return }
                    self.loadedDocumentId = documentId
                    self.requestedDocumentId = nil
                    view.document = pdfDocument
                    self.navigateCurrentDocument(in: view)
                } catch {
                    guard !Task.isCancelled else { return }
                    self.requestedDocumentId = nil
                }
            }
        }

        private func navigateCurrentDocument(in view: PDFView) {
            guard let doc = view.document,
                  owner.pageIndex >= 0, owner.pageIndex < doc.pageCount,
                  let page = doc.page(at: owner.pageIndex) else {
                return
            }
            if view.currentPage != page {
                view.go(to: page)
            }
            if let pageController {
                let total = doc.pageCount
                Task { @MainActor in
                    pageController.pageCount = total
                    pageController.pageIndex = owner.pageIndex
                }
            }
            applyRegions(to: view)
        }

        /// Render saved bounding-box regions as native PDFKit square annotations
        /// on the current page (#2458). PDFKit positions page-coordinate
        /// annotations correctly at any zoom, so no live view math is needed.
        func applyRegions(to view: PDFView) {
            guard let page = view.currentPage else { return }
            for existing in page.annotations where existing.userName == Self.regionAnnotationName {
                page.removeAnnotation(existing)
            }
            let pageSize = page.bounds(for: .mediaBox).size
            for box in owner.regionBoxes {
                guard let rect = PDFRegionGeometry.pageRect(normalized: box, pageSize: pageSize) else { continue }
                let annotation = PDFAnnotation(bounds: rect, forType: .square, withProperties: nil)
                annotation.color = NSColor.controlAccentColor
                annotation.interiorColor = NSColor.controlAccentColor.withAlphaComponent(0.12)
                annotation.userName = Self.regionAnnotationName
                page.addAnnotation(annotation)
            }
        }

        static let regionAnnotationName = "fichero.region"

        @objc
        func updateTrackingAreas(_ notification: Notification) {
            guard let pdfView = pdfView else { return }

            // Remove old tracking areas
            pdfView.trackingAreas.forEach { pdfView.removeTrackingArea($0) }

            // Add new tracking area that covers the entire PDFView
            let tracking = NSTrackingArea(
                rect: pdfView.bounds,
                options: [.activeInKeyWindow, .mouseMoved, .inVisibleRect],
                owner: self,
                userInfo: nil
            )
            pdfView.addTrackingArea(tracking)
        }

        // NSTrackingArea sends the `mouseMoved:` selector to its owner. The
        // `with event:` label would map to `mouseMovedWith:` (Coordinator is a
        // plain NSObject, not an NSResponder that normalizes it), so AppKit
        // would throw "unrecognized selector mouseMoved:" on every hover.
        // `@objc(mouseMoved:)` pins the exposed selector to what the tracking
        // area actually calls. (#1228)
        @objc(mouseMoved:)
        func mouseMoved(with event: NSEvent) {
            guard loupeEnabled.wrappedValue else { return }
            guard let pdfView = pdfView, pdfView.bounds.width > 0, pdfView.bounds.height > 0 else { return }

            let locationInView = pdfView.convert(event.locationInWindow, from: nil)

            // Normalize to 0-1 range (PDFView coordinates: origin bottom-left)
            let normalized = CGPoint(
                x: locationInView.x / pdfView.bounds.width,
                y: locationInView.y / pdfView.bounds.height
            )

            cursorPosition.wrappedValue = normalized
            owner.onCursorMoved?(normalized)
        }

        @objc
        func pageDidChange(_ notification: Notification) {
            guard let view = notification.object as? PDFView,
                  let page = view.currentPage,
                  let doc = view.document else { return }
            let index = doc.index(for: page)
            // Keep the document toolbar's page cluster in sync on every flip,
            // including pan/swipe turns the parent's pageIndex doesn't drive. (#1531)
            if let pageController {
                let total = doc.pageCount
                Task { @MainActor in
                    pageController.pageCount = total
                    pageController.pageIndex = index
                }
            }
            guard index != owner.pageIndex else { return }
            // PDFKit can post PDFViewPageChanged while SwiftUI is updating
            // the representable. Defer the callback so ContentView updates
            // selection after the current view pass commits (#1164).
            notifyPageIndexChanged(index)
        }

        /// #588: PDFKit's `autoScales` keeps re-fitting the document to the
        /// pane on every layout pass, which undoes user pinch-zoom. A scale
        /// change made *by the user* disables autoScales so the current
        /// `scaleFactor` sticks through subsequent resizes and layout passes.
        @objc
        func scaleDidChange(_ notification: Notification) {
            guard let view = notification.object as? PDFView else { return }
            // #4279: only a *user* zoom takes the document off autoScales.
            // Disabling it on any scale change — including PDFKit's own initial
            // fit — froze the page at whatever scale the pane happened to have
            // when the document loaded, which is why previews opened too small
            // and never re-fitted when the pane grew.
            if userHasZoomedManually {
                view.autoScales = false
            }
            // PDFViewScaleChanged can fire synchronously inside PDFView's
            // setDocument: → during a SwiftUI view-update pass. Publishing
            // to the @State zoomController in that window trips
            // "Publishing changes from within view updates is not allowed".
            // Hop to the next runloop tick so the publish happens after
            // the current update commits. PDFViewScaleChanged is on the
            // main thread already, so Task { @MainActor in … } is fine.
            let newScale = view.scaleFactor
            Task { @MainActor [weak self] in
                self?.zoomController?.scale = newScale
            }
        }

        /// Scroll to a specific page on a `ficheroNavigateToPage`
        /// notification. userInfo carries the page label (extractor
        /// emits the same `source_page_label` string the PDF uses for
        /// its labels — Roman numerals, prefixed numbers, etc.). When
        /// the label is numeric we fall back to numeric page-index
        /// matching. (#978/#979/#982)
        @objc
        func handleNavigateToPage(_ notification: Notification) {
            guard let view = pdfView,
                  let doc = view.document,
                  let info = notification.userInfo else { return }
            // Optional doc-id filter — when present, only respond if
            // this PDF view is showing the doc the caller asked for.
            // owner.path doesn't have an id directly; we rely on
            // ContentView having already selected the target doc, so
            // this listener fires across PDF views but only the
            // currently-visible one has anything to scroll. Cheap.
            let pageLabel = info["pageLabel"] as? String
            guard let pageLabel,
                  !pageLabel.isEmpty else { return }
            // PDFKit page labels — first try exact label match
            // (handles "iv", "12", "A-3", etc).
            var matchedPage: PDFPage?
            var matchedIndex: Int?
            for idx in 0..<doc.pageCount {
                if let page = doc.page(at: idx),
                   page.label == pageLabel {
                    matchedPage = page
                    matchedIndex = idx
                    break
                }
            }
            // Fallback: numeric page index, 1-based to match
            // human-readable labels.
            if matchedPage == nil,
               let numeric = Int(pageLabel),
               numeric >= 1, numeric <= doc.pageCount {
                matchedPage = doc.page(at: numeric - 1)
                matchedIndex = numeric - 1
            }
            guard let page = matchedPage, let pageIdx = matchedIndex else { return }
            view.go(to: page)
            notifyPageIndexChanged(pageIdx)

            // Highlight overlay: if the caller passed sourceExcerpt
            // (the verbatim quote) or charStart/charEnd, drop a yellow
            // highlight on that span so the user immediately sees what
            // the claim is anchored to. (#995 wireframe Phase 4)
            applyHighlightSpan(on: page, in: view, info: info)
        }

        func notifyPageIndexChanged(_ index: Int) {
            Task { @MainActor [weak self] in
                self?.owner.onPageIndexChange?(index)
            }
        }

        /// Horizontal pan at fit-scale turns pages; at zoom-in PDFKit pans normally.
        /// A 60pt horizontal threshold prevents accidental flips on small swipes.
        @objc
        func handlePan(_ recognizer: NSPanGestureRecognizer) {
            guard let view = pdfView else { return }

            // Region-draw mode: a drag defines a bounding box on the current
            // page instead of turning the page (#2458).
            if owner.isDrawingRegion {
                performRegionDraw(recognizer, in: view)
                return
            }

            let fitScale = view.scaleFactorForSizeToFit
            // Only intercept when not meaningfully zoomed in (within 10%).
            guard view.scaleFactor <= fitScale * 1.1 else { return }

            let translation = recognizer.translation(in: view)
            switch recognizer.state {
            case .began:
                panAccumulated = 0
            case .changed:
                panAccumulated += translation.x
                recognizer.setTranslation(.zero, in: view)
                if panAccumulated < -60 {
                    panAccumulated = 0
                    view.goToNextPage(nil)
                } else if panAccumulated > 60 {
                    panAccumulated = 0
                    view.goToPreviousPage(nil)
                }
            default:
                panAccumulated = 0
            }
        }

        /// Capture a region-draw drag and emit a normalized box on release (#2458).
        private func performRegionDraw(_ recognizer: NSPanGestureRecognizer, in view: PDFView) {
            switch recognizer.state {
            case .began:
                regionDragStartView = recognizer.location(in: view)
            case .ended:
                defer { regionDragStartView = nil }
                guard let startView = regionDragStartView, let page = view.currentPage else { return }
                let startPage = view.convert(startView, to: page)
                let endPage = view.convert(recognizer.location(in: view), to: page)
                let pageSize = page.bounds(for: .mediaBox).size
                if let box = PDFRegionGeometry.normalizedBox(
                    fromPagePoint: startPage, toPagePoint: endPage, pageSize: pageSize
                ) {
                    owner.onCreateRegion?(box)
                }
            default:
                break
            }
        }

        /// Allow the pan recognizer to coexist with PDFKit's built-in gestures
        /// so pinch-zoom and text selection still work.
        func gestureRecognizer(
            _ gestureRecognizer: NSGestureRecognizer,
            shouldRecognizeSimultaneouslyWith other: NSGestureRecognizer
        ) -> Bool {
            true
        }
    }
}

// MARK: - View wiring

/// Zoom ownership and KVO/notification registration, lifted out of the
/// `PDFPageView` body (#4353).
///
/// The struct sat at 345 of the 350-line type-body ERROR — five lines. That
/// violation was INVISIBLE while the file was at 986/1000: the file-length
/// warning was the reported problem, and this one only surfaced once the
/// `applyHighlightSpan` collapse cleared it. Risk that moves as other risk is
/// removed is the argument for measuring headroom continuously.
///
/// A same-file `extension` costs no access change, no import and no new file —
/// these are `private` and stay `private`, reachable because the extension is
/// in the same file.
private extension PDFPageView {
    /// Route manual-zoom signals — a trackpad pinch and the toolbar's zoom
    /// commands — into the coordinator, so the automatic fit knows when to stop
    /// re-fitting the page to the pane (#4279).
    func wireZoomOwnership(_ coordinator: Coordinator, on view: PDFView) {
        (view as? PinchOwningPDFView)?.onUserMagnify = { [weak coordinator] in
            coordinator?.userHasZoomedManually = true
        }
        zoomController?.onManualZoomChanged = { [weak coordinator] isManual in
            coordinator?.userHasZoomedManually = isManual
        }
    }

    /// PDFKit page/scale + claim-source navigation observers. Extracted from
    /// makeNSView to keep that builder within the function-length budget.
    func registerObservers(_ coordinator: Coordinator, on view: PDFView) {
        NotificationCenter.default.addObserver(
            coordinator,
            selector: #selector(Coordinator.pageDidChange(_:)),
            name: .PDFViewPageChanged,
            object: view
        )
        NotificationCenter.default.addObserver(
            coordinator,
            selector: #selector(Coordinator.scaleDidChange(_:)),
            name: .PDFViewScaleChanged,
            object: view
        )
        // Claim-card source navigations forwarded by ContentView. Not filtered
        // by `object:` — the userInfo carries the documentId the coordinator
        // double-checks before scrolling (#978/#979/#982).
        NotificationCenter.default.addObserver(
            coordinator,
            selector: #selector(Coordinator.handleNavigateToPage(_:)),
            name: .ficheroNavigateToPage,
            object: nil
        )
    }
}

#elseif canImport(UIKit)

/// Interactive PDF preview using PDFKit's `PDFView` on iOS.
/// Mirrors the macOS implementation where possible; loupe and cursor
/// tracking are not wired on iOS in this pass.
struct PDFPageView: UIViewRepresentable {
    let documentId: String
    let pageIndex: Int
    var onPageIndexChange: ((Int) -> Void)?
    var zoomController: PDFZoomController?
    var pageController: PDFPageController?
    var onCursorMoved: ((CGPoint) -> Void)?
    // API parity with macOS so the shared PDFPageWithToolbar call site compiles.
    // Region annotation rendering/creation is the macOS reader surface for
    // #2458; the iOS remote client renders text + page-scoped notes only.
    var regionBoxes: [[Double]] = []
    /// API parity for the shared call site (#4418); the iOS remote client does
    /// not render text-region annotations.
    var ocrBoxes: [OCRGeometryBox] = []
    var isDrawingRegion = false
    var onCreateRegion: (([Double]) -> Void)?
    /// PDF page-arrangement mode (#2090). Default preserves the single-page
    /// behavior for callers that don't opt into layout switching.
    var displayMode: PDFDisplayMode = .singlePage
    /// Page-turn axis (2026-08-09): horizontal for paged spreads (book),
    /// vertical only for continuous modes. See PageLayoutMode.pdfDisplayDirection.
    var displayDirection: PDFDisplayDirection = .horizontal

    @AppStorage("pdfPreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("pdfPreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("pdfPreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("pdfPreview.loupeLocked") private var loupeLocked = false

    @Environment(StorageService.self) private var storageService

    func makeCoordinator() -> Coordinator {
        Coordinator(owner: self)
    }

    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.displayMode = displayMode
        view.displayDirection = displayDirection
        view.displaysPageBreaks = false
        view.autoScales = true
        view.backgroundColor = UIColor(red: 253/255, green: 253/255, blue: 253/255, alpha: 1)
        view.delegate = context.coordinator
        context.coordinator.pdfView = view
        context.coordinator.zoomController = zoomController
        context.coordinator.pageController = pageController
        zoomController?.pdfView = view
        pageController?.pdfView = view

        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.pageDidChange(_:)),
            name: .PDFViewPageChanged,
            object: view
        )
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.scaleDidChange(_:)),
            name: .PDFViewScaleChanged,
            object: view
        )
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.handleNavigateToPage(_:)),
            name: .ficheroNavigateToPage,
            object: nil
        )

        let pan = UIPanGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handlePan(_:))
        )
        pan.delegate = context.coordinator
        pan.maximumNumberOfTouches = 1
        view.addGestureRecognizer(pan)

        // Observe-only pinch: records that the user took over the zoom so the
        // automatic fit stops re-fitting on rotation (#4279). PDFKit's own
        // pinch still does the zooming.
        let pinch = UIPinchGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handlePinch(_:))
        )
        pinch.delegate = context.coordinator
        view.addGestureRecognizer(pinch)

        wireZoomOwnership(context.coordinator)

        context.coordinator.loadAndNavigate(
            view,
            documentId: documentId,
            storageService: storageService
        )
        return view
    }

    func updateUIView(_ view: PDFView, context: Context) {
        context.coordinator.owner = self
        // Apply the page-layout mode (#2090); idempotent-guarded so switching
        // modes updates the live view without churning PDFKit every pass.
        if view.displayMode != displayMode { view.displayMode = displayMode }
        if view.displayDirection != displayDirection { view.displayDirection = displayDirection }
        context.coordinator.zoomController = zoomController
        context.coordinator.pageController = pageController
        zoomController?.pdfView = view
        pageController?.pdfView = view
        wireZoomOwnership(context.coordinator)
        context.coordinator.loadAndNavigate(
            view,
            documentId: documentId,
            storageService: storageService
        )
    }

    /// Route the toolbar's zoom commands into the coordinator so the automatic
    /// fit knows when to stop re-fitting the page to the pane (#4279).
    private func wireZoomOwnership(_ coordinator: Coordinator) {
        zoomController?.onManualZoomChanged = { [weak coordinator] isManual in
            coordinator?.userHasZoomedManually = isManual
        }
    }

    static func dismantleUIView(_ view: PDFView, coordinator: Coordinator) {
        NotificationCenter.default.removeObserver(coordinator)
    }

    @MainActor
    final class Coordinator: NSObject, PDFViewDelegate, UIGestureRecognizerDelegate {
        var owner: PDFPageView
        weak var pdfView: PDFView?
        var zoomController: PDFZoomController?
        var pageController: PDFPageController?
        /// True once the user has taken manual control of the zoom — a pinch or
        /// a toolbar zoom command. While it is false PDFKit's `autoScales` stays
        /// on, so the page keeps fitting the pane as the pane resizes; a manual
        /// zoom freezes the scale until a different document loads (#4279).
        var userHasZoomedManually = false
        private var loadedDocumentId: String?
        private var requestedDocumentId: String?
        private var loadTask: Task<Void, Never>?
        private var panAccumulated: CGFloat = 0

        init(owner: PDFPageView) {
            self.owner = owner
        }

        deinit {
            loadTask?.cancel()
        }

        func loadAndNavigate(
            _ view: PDFView,
            documentId: String,
            storageService: StorageService
        ) {
            if loadedDocumentId == documentId, view.document != nil {
                navigateCurrentDocument(in: view)
                return
            }
            if requestedDocumentId == documentId {
                return
            }

            requestedDocumentId = documentId
            loadedDocumentId = nil
            loadTask?.cancel()
            view.document = nil
            view.autoScales = true
            // A different document — the automatic fit owns the zoom again (#4279).
            userHasZoomedManually = false

            loadTask = Task { [weak self, weak view] in
                guard let self else { return }
                do {
                    // Shared per-document decode (#3209): one PDFDocument, reused
                    // across the viewer's split panes instead of decoding per view.
                    let pdfDocument = try await storageService.pdfCache.document(for: documentId)
                    guard !Task.isCancelled,
                          let pdfDocument,
                          let view else { return }
                    self.loadedDocumentId = documentId
                    self.requestedDocumentId = nil
                    view.document = pdfDocument
                    self.navigateCurrentDocument(in: view)
                } catch {
                    guard !Task.isCancelled else { return }
                    self.requestedDocumentId = nil
                }
            }
        }

        private func navigateCurrentDocument(in view: PDFView) {
            guard let doc = view.document,
                  owner.pageIndex >= 0, owner.pageIndex < doc.pageCount,
                  let page = doc.page(at: owner.pageIndex) else { return }
            if view.currentPage != page {
                view.go(to: page)
            }
            if let pageController {
                let total = doc.pageCount
                Task { @MainActor in
                    pageController.pageCount = total
                    pageController.pageIndex = owner.pageIndex
                }
            }
        }

        @objc
        func pageDidChange(_ notification: Notification) {
            guard let view = notification.object as? PDFView,
                  let page = view.currentPage,
                  let doc = view.document else { return }
            let index = doc.index(for: page)
            if let pageController {
                let total = doc.pageCount
                Task { @MainActor in
                    pageController.pageCount = total
                    pageController.pageIndex = index
                }
            }
            guard index != owner.pageIndex else { return }
            notifyPageIndexChanged(index)
        }

        @objc
        func scaleDidChange(_ notification: Notification) {
            guard let view = notification.object as? PDFView else { return }
            // #4279: only a *user* zoom takes the document off autoScales, so a
            // programmatic fit (initial load, rotation) keeps re-fitting.
            if userHasZoomedManually {
                view.autoScales = false
            }
            let newScale = view.scaleFactor
            Task { @MainActor [weak self] in
                self?.zoomController?.scale = newScale
            }
        }

        /// Observes PDFKit's own pinch so a user zoom is recorded without
        /// interfering with it (#4279). Recognition is simultaneous — see
        /// `gestureRecognizer(_:shouldRecognizeSimultaneouslyWith:)`.
        @objc
        func handlePinch(_ recognizer: UIPinchGestureRecognizer) {
            if recognizer.state == .began {
                userHasZoomedManually = true
            }
        }

        @objc
        func handleNavigateToPage(_ notification: Notification) {
            guard let view = pdfView,
                  let doc = view.document,
                  let info = notification.userInfo else { return }
            let pageLabel = info["pageLabel"] as? String
            guard let pageLabel, !pageLabel.isEmpty else { return }
            var matchedPage: PDFPage?
            var matchedIndex: Int?
            for idx in 0..<doc.pageCount {
                if let page = doc.page(at: idx),
                   page.label == pageLabel {
                    matchedPage = page
                    matchedIndex = idx
                    break
                }
            }
            if matchedPage == nil,
               let numeric = Int(pageLabel),
               numeric >= 1, numeric <= doc.pageCount {
                matchedPage = doc.page(at: numeric - 1)
                matchedIndex = numeric - 1
            }
            guard let page = matchedPage, let pageIdx = matchedIndex else { return }
            view.go(to: page)
            notifyPageIndexChanged(pageIdx)
            applyHighlightSpan(on: page, in: view, info: info)
        }

        func notifyPageIndexChanged(_ index: Int) {
            Task { @MainActor [weak self] in
                self?.owner.onPageIndexChange?(index)
            }
        }

        @objc
        func handlePan(_ recognizer: UIPanGestureRecognizer) {
            guard let view = pdfView else { return }
            let fitScale = view.scaleFactorForSizeToFit
            guard view.scaleFactor <= fitScale * 1.1 else { return }

            let translation = recognizer.translation(in: view)
            switch recognizer.state {
            case .began:
                panAccumulated = 0
            case .changed:
                panAccumulated += translation.x
                recognizer.setTranslation(.zero, in: view)
                if panAccumulated < -60 {
                    panAccumulated = 0
                    view.goToNextPage(nil)
                } else if panAccumulated > 60 {
                    panAccumulated = 0
                    view.goToPreviousPage(nil)
                }
            default:
                panAccumulated = 0
            }
        }

        func gestureRecognizer(
            _ gestureRecognizer: UIGestureRecognizer,
            shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool {
            true
        }
    }
}

#endif

// MARK: - Highlight span (shared)

/// ONE implementation for both platforms (#4353).
///
/// This existed twice — 64 lines each, in the mutually exclusive AppKit and
/// UIKit branches, identical apart from one colour reference. Each copy even
/// carried its OWN `#if` for that colour, which was already redundant inside a
/// branch that had decided the platform.
///
/// `PlatformColor` (PlatformAliases.swift) covers the whole difference, so the
/// conditional disappears rather than wrapping the same body twice. That takes
/// this file from 986 to well under the 1000-line error, so it no longer needs
/// the split that was being planned for it.
///
/// `@MainActor` is load-bearing: this touches `PDFView.go(to:)` and mutates the
/// page's annotations, both main-actor-isolated. Each platform copy sat inside a
/// `@MainActor` context, so neither needed the attribute; the collapsed function
/// is a free function and inherits nothing, which is how the isolation was lost.
@MainActor
private func applyHighlightSpan(
    on page: PDFPage,
    in view: PDFView,
    info: [AnyHashable: Any]
) {
    guard let doc = view.document else { return }

    for existing in page.annotations where existing.userName == "fichero.claim-source" {
        page.removeAnnotation(existing)
    }

    // Most precise anchor: a normalized [x, y, w, h] bbox (engine convention,
    // top-left origin — the same array crop_pdf_page uses). Draw the region
    // highlight directly, flipping y into PDFKit's bottom-left page space so the
    // highlight lands exactly where the crop was taken (#2105/#3449).
    if let bbox = info["bbox"] as? [Double], bbox.count == 4 {
        let cropBounds = page.bounds(for: .cropBox)
        let rect = CGRect(
            x: cropBounds.minX + bbox[0] * cropBounds.width,
            y: cropBounds.minY + (1 - bbox[1] - bbox[3]) * cropBounds.height,
            width: bbox[2] * cropBounds.width,
            height: bbox[3] * cropBounds.height
        )
        let annotation = PDFAnnotation(bounds: rect, forType: .highlight, withProperties: nil)
        annotation.color = PlatformColor.systemYellow.withAlphaComponent(0.35)
        annotation.userName = "fichero.claim-source"
        page.addAnnotation(annotation)
        return
    }

    var selection: PDFSelection?

    if let excerpt = info["excerpt"] as? String, !excerpt.isEmpty {
        if let found = doc.findString(excerpt, withOptions: .caseInsensitive).first {
            selection = found
        }
    }

    if selection == nil,
       let start = info["charStart"] as? Int,
       let end = info["charEnd"] as? Int,
       end > start,
       let pageStr = page.string {
        let range = NSRange(location: start, length: end - start)
        if range.upperBound <= pageStr.utf16.count {
            selection = page.selection(for: range)
        }
    }

    guard let sel = selection else { return }

    for rect in sel.selectionsByLine().map({ $0.bounds(for: page) }) {
        let annotation = PDFAnnotation(bounds: rect, forType: .highlight, withProperties: nil)
        annotation.color = PlatformColor.systemYellow.withAlphaComponent(0.35)
        annotation.userName = "fichero.claim-source"
        page.addAnnotation(annotation)
    }

    view.go(to: sel)
}
