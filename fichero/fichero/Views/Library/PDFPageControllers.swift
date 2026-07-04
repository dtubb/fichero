import PDFKit

// PDF toolbar controllers, extracted from PDFPageView.swift (#3041) — standalone
// @MainActor ObservableObject bridges between the SwiftUI canvas toolbars and
// PDFKit's PDFView. Moved to their own file to trim PDFPageView.swift; no logic
// or signature change (pure mechanical split).

// MARK: - PDF Zoom Controller

/// Bridges the SwiftUI zoom toolbar with PDFKit's PDFView.
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

// MARK: - PDF Page Controller

/// Bridges the SwiftUI document toolbar's page-navigation cluster (◀ N / M ▶)
/// with PDFKit's PDFView, mirroring `PDFZoomController` for zoom. The
/// page indicator is document-scoped, so it belongs on the canvas toolbar
/// rather than the window toolbar. (#1531)
@MainActor
final class PDFPageController: ObservableObject {
    /// 0-based index of the page PDFKit is currently showing.
    @Published var pageIndex: Int = 0
    /// Total page count of the loaded document (0 until a document loads).
    @Published var pageCount: Int = 0
    weak var pdfView: PDFView?

    var canGoPrevious: Bool { pageIndex > 0 }
    var canGoNext: Bool { pageIndex < pageCount - 1 }

    func goToPrevious() { pdfView?.goToPreviousPage(nil) }
    func goToNext() { pdfView?.goToNextPage(nil) }
}
