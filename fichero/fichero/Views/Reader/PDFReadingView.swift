import SwiftUI

// MARK: - PDF Reading View (#1188)

/// Combines a PDF page viewer and its corresponding content pane with a resizable divider.
struct PDFReadingView: View {
    private static let minContentWidth: Double = 160
    private static let maxContentWidth: Double = 600

    let document: Document?
    let pdfDocumentId: String
    let pageIndex: Int
    @Binding var contentWidth: Double
    var onPageIndexChange: ((Int) -> Void)?

    /// Compact width (iPhone / narrow iPad) drops the side-by-side content pane
    /// so the page + divider + fixed-min-width pane never clamp off-screen (the
    /// #2368 iPad reading-surface crash class). (#3013)
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    var body: some View {
        if ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
            // Compact PDF: just the page, full width, touch paging. No fixed
            // min-width frames, no divider, no side content pane (#3013).
            PDFPageWithToolbar(
                documentId: pdfDocumentId,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            HStack(spacing: 0) {
                PDFPageWithToolbar(
                    documentId: pdfDocumentId,
                    pageIndex: pageIndex,
                    onPageIndexChange: onPageIndexChange
                )
                .frame(maxWidth: .infinity)

                ResizableDivider(
                    width: $contentWidth,
                    minWidth: Self.minContentWidth,
                    maxWidth: Self.maxContentWidth,
                    edge: .trailing
                )

                PageContentPane(document: document)
                    .frame(width: CGFloat(contentWidth))
                    .frame(minWidth: Self.minContentWidth)
            }
            .onAppear {
                contentWidth = max(Self.minContentWidth, min(Self.maxContentWidth, contentWidth))
            }
        }
    }
}
