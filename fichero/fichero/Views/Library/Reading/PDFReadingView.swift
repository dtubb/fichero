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

// MARK: - Document Page List View (#1189)

/// Vertical thumbnail strip showing all pages of a multi-page PDF document.
struct DocumentPageListView: View {
    let pdfDocumentId: String
    let pages: [Document]
    let selectedPageIndex: Int
    let onPageSelect: (Int) -> Void

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 6) {
                    ForEach(Array(pages.enumerated()), id: \.element.id) { idx, page in
                        PageThumbnailStripCell(
                            pdfDocumentId: pdfDocumentId,
                            pageIndex: idx,
                            pageNumber: page.sequence ?? (idx + 1),
                            isSelected: selectedPageIndex == idx
                        ) {
                            onPageSelect(idx)
                        }
                        .id(idx)
                    }
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 4)
            }
            .onChange(of: selectedPageIndex) { _, newIdx in
                withAnimation(.easeInOut(duration: 0.2)) {
                    proxy.scrollTo(newIdx, anchor: .center)
                }
            }
            .onAppear {
                proxy.scrollTo(selectedPageIndex, anchor: .center)
            }
        }
        .background(Color(.controlBackgroundColor))
    }
}

private struct PageThumbnailStripCell: View {
    let pdfDocumentId: String
    let pageIndex: Int
    let pageNumber: Int
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            VStack(spacing: 3) {
                PDFThumbnailView(
                    documentId: pdfDocumentId,
                    size: CGSize(width: 88, height: 114),
                    pageIndex: pageIndex
                )
                .frame(width: 88, height: 114)
                .background(Color.white)
                .cornerRadius(3)
                .overlay(
                    RoundedRectangle(cornerRadius: 3)
                        .strokeBorder(
                            isSelected ? Color.accentColor : Color(platformColor: .separatorColor),
                            lineWidth: isSelected ? 2 : 0.5
                        )
                )
                .shadow(color: .black.opacity(0.06), radius: 2, x: 0, y: 1)

                Text("\(pageNumber)")
                    .font(.system(size: 9, weight: isSelected ? .semibold : .regular))
                    .foregroundStyle(isSelected ? Color.accentColor : .secondary)
            }
        }
        .buttonStyle(.plain)
    }
}
