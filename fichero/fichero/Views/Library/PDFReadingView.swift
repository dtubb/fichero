import SwiftUI

// MARK: - PDF Reading View (#1188)

/// Combines a PDF page viewer and its corresponding content pane with a resizable divider.
struct PDFReadingView: View {
    let document: Document?
    let pdfPath: String
    let pageIndex: Int
    @Binding var contentWidth: Double
    var onPageIndexChange: ((Int) -> Void)?

    var body: some View {
        HStack(spacing: 0) {
            PDFPageWithToolbar(
                path: pdfPath,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange
            )
            .frame(maxWidth: .infinity)

            ResizableDivider(
                width: $contentWidth,
                minWidth: 160,
                maxWidth: 600,
                edge: .trailing
            )

            PageContentPane(document: document)
                .frame(width: CGFloat(contentWidth))
        }
    }
}

// MARK: - Document Page List View (#1189)

/// Vertical thumbnail strip showing all pages of a multi-page PDF document.
struct DocumentPageListView: View {
    let pdfPath: String
    let pages: [Document]
    let selectedPageIndex: Int
    let onPageSelect: (Int) -> Void

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 6) {
                    ForEach(Array(pages.enumerated()), id: \.element.id) { idx, page in
                        PageThumbnailStripCell(
                            pdfPath: pdfPath,
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
    let pdfPath: String
    let pageIndex: Int
    let pageNumber: Int
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            VStack(spacing: 3) {
                PDFThumbnailView(
                    path: pdfPath,
                    size: CGSize(width: 88, height: 114),
                    pageIndex: pageIndex
                )
                .frame(width: 88, height: 114)
                .background(Color.white)
                .cornerRadius(3)
                .overlay(
                    RoundedRectangle(cornerRadius: 3)
                        .strokeBorder(
                            isSelected ? Color.accentColor : Color(nsColor: .separatorColor),
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
