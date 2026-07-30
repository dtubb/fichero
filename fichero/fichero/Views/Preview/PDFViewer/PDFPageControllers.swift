import Observation
import PDFKit

// PDF toolbar controllers, extracted from PDFPageView.swift (#3041) — standalone
// @MainActor @Observable bridges between the SwiftUI canvas toolbars and
// PDFKit's PDFView. These hold pure view state (zoom scale / page index), not
// data-layer endpoints, so they migrate straight to @Observable (#2960).

// MARK: - PDF Zoom Controller

/// Bridges the SwiftUI zoom toolbar with PDFKit's PDFView.
@MainActor
@Observable
final class PDFZoomController {
    var scale: CGFloat = 1.0
    weak var pdfView: PDFView?
    /// Fired when a toolbar command hands zoom control to the user (`true`) or
    /// gives it back to the automatic fit (`false`). `PDFPageView`'s coordinator
    /// uses it to decide whether PDFKit may keep re-fitting on pane resize
    /// (#4279); without it, #588's "first scale change disables autoScales"
    /// rule can't tell a programmatic fit from a deliberate zoom.
    var onManualZoomChanged: (@MainActor (Bool) -> Void)?

    func zoomIn() {
        onManualZoomChanged?(true)
        pdfView?.zoomIn(nil)
    }

    func zoomOut() {
        onManualZoomChanged?(true)
        pdfView?.zoomOut(nil)
    }

    func fitToWindow() {
        guard let view = pdfView else { return }
        onManualZoomChanged?(false)
        // Vector content fits without a 100% cap (PreviewInitialZoomPolicy), and
        // `scaleFactorForSizeToFit` is PDFKit's own measure of that fit. Setting
        // scaleFactor first then re-arming autoScales keeps the page fitted
        // through later layout passes — safe now that a manual zoom is tracked
        // separately rather than inferred from any scale change (#588/#4279).
        view.scaleFactor = PreviewInitialZoomPolicy.clamped(view.scaleFactorForSizeToFit, kind: .vector)
        view.autoScales = true
    }

    func actualSize() {
        guard let view = pdfView else { return }
        onManualZoomChanged?(true)
        view.autoScales = false
        view.scaleFactor = 1.0
    }
}

// MARK: - PDF Page Controller

/// Bridges the SwiftUI document toolbar's page-navigation cluster (◀ N / M ▶)
/// with PDFKit's PDFView, mirroring `PDFZoomController` for zoom. The
/// page indicator is document-scoped, so it belongs on the canvas toolbar
/// rather than the window toolbar. (#1531)
@MainActor
@Observable
final class PDFPageController {
    /// 0-based index of the page PDFKit is currently showing.
    var pageIndex: Int = 0
    /// Total page count of the loaded document (0 until a document loads).
    var pageCount: Int = 0
    weak var pdfView: PDFView?

    var canGoPrevious: Bool { pageIndex > 0 }
    var canGoNext: Bool { pageIndex < pageCount - 1 }

    func goToPrevious() { pdfView?.goToPreviousPage(nil) }
    func goToNext() { pdfView?.goToNextPage(nil) }
}
