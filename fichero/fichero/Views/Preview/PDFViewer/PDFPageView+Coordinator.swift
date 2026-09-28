#if canImport(AppKit)
import PDFKit
import SwiftUI

// The macOS coordinator, split out of PDFPageView.swift to keep that file under file_length.
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
        /// One page turn per gesture (2026-08-11, Daniel: "it moves the page
        /// to the next, and then it still moves the next page … as my swipe is
        /// still going"): the threshold used to re-arm mid-gesture, so a long
        /// swipe flipped repeatedly. Set on the first flip, cleared when the
        /// gesture ends.
        private var panDidTurnPage = false
        /// Start point (in view coords) of an in-progress region-draw drag (#2458).
        private var regionDragStartView: CGPoint?
        /// A Reshape in progress in Edit Segments (`reshapePan`).
        var reshapeSession: PDFReshapeSession?

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

        /// Render saved annotations as native PDFKit annotations on the
        /// current page, PER KIND (#2458; Daniel, 2026-08-30) — a highlight
        /// is a wash in its color, an underline a bar, a check a margin ✓.
        /// PDFKit positions page-coordinate annotations correctly at any
        /// zoom, so no live view math is needed.
        func applyRegions(to view: PDFView) {
            guard let page = view.currentPage else { return }
            for existing in page.annotations where existing.userName == Self.regionAnnotationName {
                page.removeAnnotation(existing)
            }
            let pageSize = page.bounds(for: .mediaBox).size
            for mark in owner.regionMarks {
                for annotation in PDFAnnotationMarkRendering.annotations(for: mark, pageSize: pageSize) {
                    annotation.userName = Self.regionAnnotationName
                    page.addAnnotation(annotation)
                }
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
            if owner.segmentEditing.isEditing, reshapePan(recognizer, in: view) { return }

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
#endif
