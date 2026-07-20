import SwiftUI

// MARK: - ContentView Breadcrumb Extension
// Agent: ViewBuilderAgent
// Responsibility: Clickable Finder/Xcode-style location breadcrumb for the
// content header. Split out of ContentView+ViewBuilders.swift to keep each
// file under the file_length limit.

extension ContentView {
    // MARK: - Breadcrumb

    /// Clickable Finder/Xcode-style breadcrumb for the content header (#1928):
    /// Library ▸ folder ▸ … ▸ document ▸ page. Hidden unless there's a path
    /// beyond the Library root (so it never shows an empty "Library" strip).
    @ViewBuilder
    var breadcrumbBar: some View {
        let segments = breadcrumbSegments
        if segments.count > 1 {
            HStack(spacing: 4) {
                ForEach(Array(segments.enumerated()), id: \.element.id) { index, segment in
                    if index > 0 {
                        Image(systemName: "chevron.right")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    breadcrumbSegmentLabel(segment, isLast: index == segments.count - 1)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12)
            .frame(height: 24)
            .background(.bar)
            .accessibilityIdentifier("contentBreadcrumbBar")
        }
    }

    @ViewBuilder
    private func breadcrumbSegmentLabel(_ segment: BreadcrumbBuilder.Segment, isLast: Bool) -> some View {
        // The current (last) segment is where you already are — plain text, not a
        // button. Ancestors + the Library root are clickable and navigate up.
        if segment.isNavigable && !isLast {
            Button(segment.name) { navigateToBreadcrumb(segment) }
                .buttonStyle(.plain)
                .font(.caption)
                .foregroundStyle(.secondary)
        } else {
            Text(segment.name)
                .font(.caption)
                .foregroundStyle(isLast ? .primary : .secondary)
                .lineLimit(1)
        }
    }

    /// Library ▸ folder ▸ … ▸ document ▸ page segments for the current library
    /// selection. Reuses the same parent-lookup as `breadcrumbSubtitle`.
    var breadcrumbSegments: [BreadcrumbBuilder.Segment] {
        guard case .library(let document) = viewMode else {
            return [BreadcrumbBuilder.Segment(name: "Library", documentId: nil, isRoot: true)]
        }
        let parentLookup: BreadcrumbBuilder.DocumentLookup = { parentId in
            documentStore.currentDocuments.first { $0.id == parentId }
                ?? documentStore.collections.first { $0.id == parentId }
        }
        let pageLabel: String? = if let page = activeLocationDocument, page.docType == .page {
            page.pageThumbnailLabel
        } else {
            nil
        }
        return BreadcrumbBuilder.buildSegments(
            from: document,
            parentLookup: parentLookup,
            pageLabel: pageLabel
        )
    }

    private func navigateToBreadcrumb(_ segment: BreadcrumbBuilder.Segment) {
        if segment.isRoot {
            viewMode = .library(nil)
            sidebarSelectionState.selectedItemId = nil
            detailDocument = nil
            browserSelection = []
            return
        }
        guard let documentId = segment.documentId,
              let doc = documentStore.currentDocuments.first(where: { $0.id == documentId })
                  ?? documentStore.collections.first(where: { $0.id == documentId }) else { return }
        viewMode = .library(doc)
        sidebarSelectionState.selectedItemId = "doc:\(documentId)"
        detailDocument = nil
        browserSelection = []
    }
}
