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
