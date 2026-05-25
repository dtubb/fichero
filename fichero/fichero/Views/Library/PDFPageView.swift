import PDFKit
import SwiftUI

// MARK: - PDF Zoom Controller

/// Bridges the SwiftUI zoom toolbar with PDFKit's AppKit PDFView.
@MainActor
final class PDFZoomController: ObservableObject {
    @Published var scale: CGFloat = 1.0
    weak var pdfView: PDFView?

    func zoomIn() { pdfView?.zoomIn(nil) }
    func zoomOut() { pdfView?.zoomOut(nil) }
    func fitToWindow() {
        guard let view = pdfView else { return }
        // Avoid re-enabling autoScales (#588) — compute fit scale directly.
        view.autoScales = false
        view.scaleFactor = view.scaleFactorForSizeToFit
    }
    func actualSize() {
        guard let view = pdfView else { return }
        view.autoScales = false
        view.scaleFactor = 1.0
    }
}

// MARK: - PDFPageView

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
    let path: String
    let pageIndex: Int
    /// Fires when the user swipes to a different page.
    /// The index is 0-based into the PDF document.
    var onPageIndexChange: ((Int) -> Void)?
    /// Optional zoom controller — set by PDFPageWithToolbar to sync the toolbar.
    var zoomController: PDFZoomController?
    var onCursorMoved: ((CGPoint) -> Void)?

    // MARK: - Loupe State

    @AppStorage("pdfPreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("pdfPreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("pdfPreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("pdfPreview.loupeLocked") private var loupeLocked = false

    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @State private var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)

    func makeCoordinator() -> Coordinator {
        Coordinator(
            owner: self,
            loupeEnabled: $loupeEnabled,
            cursorPosition: $cursorPosition,
            lockedPosition: $lockedPosition
        )
    }

    func makeNSView(context: Context) -> PDFView {
        let view = PDFView()
        view.displayMode = .singlePage
        view.displaysPageBreaks = false
        // #588: autoScales re-fits the document to the pane on every layout
        // pass, which silently undoes user pinch-zoom. We keep autoScales=true
        // only long enough for PDFKit to compute the initial fit; the scale
        // observer below flips it off the first time scaleFactor changes.
        view.autoScales = true
        view.backgroundColor = NSColor(red: 253/255, green: 253/255, blue: 253/255, alpha: 1)
        view.delegate = context.coordinator
        context.coordinator.pdfView = view
        context.coordinator.zoomController = zoomController
        zoomController?.pdfView = view
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
        // Listen for claim-card source navigations forwarded by
        // ContentView. We don't filter by `object:` because the
        // userInfo carries the documentId that should match the
        // currently-loaded PDF; the coordinator double-checks that
        // before scrolling. (#978/#979/#982 Phase 2)
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.handleNavigateToPage(_:)),
            name: .ficheroNavigateToPage,
            object: nil
        )
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
        loadAndNavigate(view)
        return view
    }

    func updateNSView(_ view: PDFView, context: Context) {
        context.coordinator.owner = self
        context.coordinator.zoomController = zoomController
        zoomController?.pdfView = view
        loadAndNavigate(view)
    }

    static func dismantleNSView(_ view: PDFView, coordinator: Coordinator) {
        NotificationCenter.default.removeObserver(coordinator)
        view.trackingAreas.forEach { view.removeTrackingArea($0) }
    }

    /// Load the PDF document (if not already loaded) and navigate to the
    /// requested page. Only replaces `document` when the path actually changes
    /// — re-assigning the same document resets the user's zoom/selection state.
    private func loadAndNavigate(_ view: PDFView) {
        let fileURL = URL(fileURLWithPath: path)
        if view.document?.documentURL != fileURL {
            // #588: re-engage autoScales for the new document's initial fit.
            view.autoScales = true
            view.document = PDFDocument(url: fileURL)
        }
        guard let doc = view.document,
              pageIndex >= 0, pageIndex < doc.pageCount,
              let page = doc.page(at: pageIndex) else {
            return
        }
        if view.currentPage != page {
            view.go(to: page)
        }
    }

    /// Bridges AppKit notifications / delegate into the SwiftUI callback.
    /// All PDFKit notification and gesture callbacks fire on the main thread,
    /// so @MainActor is correct and avoids nonisolated-context concurrency warnings.
    @MainActor
    final class Coordinator: NSObject, PDFViewDelegate, NSGestureRecognizerDelegate {
        var owner: PDFPageView
        weak var pdfView: PDFView?
        var zoomController: PDFZoomController?
        // Accumulated horizontal translation for the current pan gesture.
        private var panAccumulated: CGFloat = 0

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

        @objc func mouseMoved(with event: NSEvent) {
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
            guard index != owner.pageIndex else { return }
            // PDFKit can post PDFViewPageChanged while SwiftUI is updating
            // the representable. Defer the callback so ContentView updates
            // selection after the current view pass commits (#1164).
            notifyPageIndexChanged(index)
        }

        /// #588: PDFKit's `autoScales` keeps re-fitting the document to the
        /// pane on every layout pass, which undoes user pinch-zoom. The first
        /// scale change disables autoScales so the current `scaleFactor`
        /// sticks through subsequent resizes and layout passes.
        @objc
        func scaleDidChange(_ notification: Notification) {
            guard let view = notification.object as? PDFView else { return }
            view.autoScales = false
            // PDFViewScaleChanged can fire synchronously inside PDFView's
            // setDocument: → during a SwiftUI view-update pass. Publishing
            // to the @ObservedObject zoomController in that window trips
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
        annotation.color = NSColor.systemYellow.withAlphaComponent(0.35)
        annotation.userName = "fichero.claim-source"
        page.addAnnotation(annotation)
    }

    view.go(to: sel)
}
