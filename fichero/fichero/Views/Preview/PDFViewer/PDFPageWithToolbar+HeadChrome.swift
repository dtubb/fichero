import SwiftUI

// MARK: - Head chrome + zoom cluster (Daniel, 2026-08-29)
// Split from PDFPageWithToolbar.swift for the file/type-length budget. The
// members it reads (`zoom`, `pageNav`, `loupeEnabled`, `paneChrome`) were
// promoted private -> internal there: `private` is FILE-scoped.

extension PDFPageWithToolbar {
    var pdfPageNav: ReaderPageNav {
        ReaderPageNav(
            pageIndex: pageNav.pageIndex,
            pageCount: pageNav.pageCount,
            canGoPrevious: pageNav.canGoPrevious,
            canGoNext: pageNav.canGoNext,
            goPrevious: { pageNav.goToPrevious() },
            goNext: { pageNav.goToNext() }
        )
    }

    /// Publish this pane's page nav to the head's chrome seam (Daniel,
    /// 2026-08-29: pages ‹ › sit left of the breadcrumb). A PDF page has no
    /// renditions, so those clear.
    func publishHeadChrome() {
        guard let paneChrome else { return }
        paneChrome.pageNav = pdfPageNav
        paneChrome.renditionNames = []
        paneChrome.renditionIndex = 0
        paneChrome.selectRendition = nil
    }

    /// The magnification family, bottom-right (Daniel, 2026-08-29): the zoom
    /// pill + loupe toggle. No mini-map or magnifier bar on a PDF page, so
    /// the cluster collapses to the pill + toggle. macOS only — iOS pinch-
    /// zooms and has no loupe overlay yet.
    @ViewBuilder
    var zoomClusterOverlay: some View {
        #if os(macOS)
        PreviewZoomMapCluster(
            scalePercent: Int(zoom.scale * 100),
            zoomIn: { zoom.zoomIn() },
            zoomOut: { zoom.zoomOut() },
            fitToWindow: { zoom.fitToWindow() },
            actualSize: { zoom.actualSize() },
            loupeEnabled: $loupeEnabled,
            magnifierEnabled: nil,
            map: { EmptyView() }
        )
        #endif
    }
}
