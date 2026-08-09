import SwiftUI

// MARK: - Finder-style stacked multi-selection preview (Daniel, 2026-08-09,
// screenshot #95: "if two pages are selected why not make preview like in
// finder?"). When the library selection holds MORE than one document, the
// preview pane shows a fanned stack of their thumbnails and the count —
// instead of silently previewing only the primary.

/// The documents a multi-selection stack previews: the selected documents in
/// DOCUMENT order (the same order every shell resolver uses — never Set
/// iteration order), empty unless the selection is genuinely multiple.
/// File scope so Swift Testing can call it off-main (View statics inherit
/// MainActor under the macOS 26 SDK).
func previewStackDocuments(selection: Set<String>, in documents: [Document]) -> [Document] {
    guard selection.count > 1 else { return [] }
    let matched = documents.filter { selection.contains($0.id) }
    return matched.count > 1 ? matched : []
}

/// Back cards rotate alternately off-axis, front card sits straight — the
/// Finder fan. Index 0 is the FRONT card (the primary selection). FILE SCOPE:
/// a static on a View inherits MainActor under the macOS 26 SDK and SIGTRAPs
/// Swift Testing off-main.
func stackRotationDegrees(forCardAt index: Int) -> Double {
    switch index {
    case 1: -6
    case 2: 5
    default: 0
    }
}

struct MultiSelectionPreviewStack: View {
    let documents: [Document]

    /// Finder fans at most a few cards; the count line carries the rest.
    private static let maxCards = 3
    // Larger cards (Daniel, 2026-08-09, #112: "The preview icon can be
    // larger as well") — the fan is the pane's whole content, let it read.
    private static let cardWidth: CGFloat = 240
    private static let cardHeight: CGFloat = 300

    var body: some View {
        VStack(spacing: 20) {
            ZStack {
                // Reverse so the FIRST document (the document-order primary)
                // draws last — on top of the fan, like Finder.
                ForEach(
                    Array(documents.prefix(Self.maxCards).enumerated()).reversed(),
                    id: \.element.id
                ) { card in
                    stackCard(for: card.element)
                        .rotationEffect(.degrees(stackRotationDegrees(forCardAt: card.offset)))
                        .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
                }
            }
            .frame(height: Self.cardHeight + 40)

            Text("\(documents.count) Items")
                .font(.title3)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(documents.count) items selected")
        .accessibilityIdentifier("multiSelectionPreviewStack")
    }

    /// One card of the fan. Image-bearing documents render the PAGE itself —
    /// white sheet + hairline hugging the fitted image's shape (Daniel
    /// #121-123: "the shape of the paper around the paper is not the same
    /// shape as the icon… render it on a page") — while folders/mirrors keep
    /// the symbol well.
    @ViewBuilder
    private func stackCard(for document: Document) -> some View {
        if DocumentThumbnailKind.forDocument(document).fetchesStorageThumbnail {
            LibraryImageView(documentId: document.id, imageType: .thumbnail)
                .aspectRatio(contentMode: .fit)
                .background(Color(.textBackgroundColor))
                .overlay(
                    RoundedRectangle(cornerRadius: 2)
                        .strokeBorder(Color.primary.opacity(0.15), lineWidth: 0.5)
                )
                .frame(maxWidth: Self.cardWidth, maxHeight: Self.cardHeight)
        } else {
            DocumentThumbnail(
                document: document,
                width: Self.cardWidth,
                height: Self.cardHeight,
                contentMode: .fit,
                folderSymbolSize: 64
            )
        }
    }
}

#Preview("Stack of three") {
    LibraryPreviewFixtures.environment(
        MultiSelectionPreviewStack(documents: Array(LibraryPreviewFixtures.documents.prefix(3)))
    )
    .frame(width: 420, height: 420)
}
