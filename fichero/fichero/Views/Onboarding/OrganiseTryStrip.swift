import SwiftUI

/// Organise tried on a run of consecutive pages (`finddocs.review.setup-page`, #5668): the run as a strip of
/// thumbnails, each proposed document a dashed group over its pages (name, kind, how sure; its reasons on hover),
/// and the entries found listed under the pages they open on.
struct OrganiseTryStrip: View {
    let pages: [String]
    let documents: [SetupStageProposedDocument]
    let entries: [SetupStageEntry]
    /// A page's name, for its caption and for VoiceOver.
    let name: (String) -> String

    var body: some View {
        let byPage = OrganiseTryLayout.entries(entries)
        ScrollView(.horizontal) {
            HStack(alignment: .top, spacing: 10) {
                ForEach(Array(OrganiseTryLayout.segments(pages: pages, documents: documents).enumerated()),
                        id: \.offset) { _, segment in
                    switch segment {
                    case .document(let document, let held):
                        VStack(alignment: .leading, spacing: 4) {
                            Text(OrganiseTryLayout.caption(document))
                                .font(.caption)
                                .lineLimit(1)
                            HStack(alignment: .top, spacing: 6) {
                                ForEach(held, id: \.self) { pageCell($0, entries: byPage[$0] ?? []) }
                            }
                        }
                        .padding(6)
                        .overlay(RoundedRectangle(cornerRadius: 6)
                            .strokeBorder(.secondary, style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
                        .help((document.reasons ?? []).joined(separator: "; "))
                        .accessibilityElement(children: .contain)
                        .accessibilityLabel("Proposed document: \(OrganiseTryLayout.caption(document))")
                    case .page(let pageId):
                        pageCell(pageId, entries: byPage[pageId] ?? [])
                            .padding(.top, 22)
                    }
                }
            }
            .padding(.vertical, 4)
        }
        .accessibilityIdentifier("setup.organise.tryStrip")
    }

    private func pageCell(_ pageId: String, entries: [SetupStageEntry]) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            LibraryImageView(documentId: pageId, imageType: .thumbnail)
                .aspectRatio(contentMode: .fit)
                .frame(width: 56, height: 72)
                .clipShape(RoundedRectangle(cornerRadius: 3))
                .accessibilityLabel(name(pageId))
            Text(name(pageId)).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                Text(entry.name).font(.caption2).lineLimit(1)
                    .help(entry.opening ?? "")
            }
        }
        .frame(width: 64, alignment: .leading)
    }
}

#Preview("Organise on a run of pages") {
    OrganiseTryStrip(
        pages: ["a", "b", "c", "d", "e"],
        documents: [
            .init(name: "Sentencia", pageIds: ["a", "b", "c"], kind: "Sentencia", confidence: 0.82,
                  reasons: ["VISTOS at the head of page 1"]),
            .init(name: "Carta", pageIds: ["d"], kind: "Carta", confidence: 0.64, reasons: nil)
        ],
        entries: [.init(pageId: "e", name: "12 March 1924", opening: "Today the rain")],
        name: { "Page \($0)" }
    )
    .padding()
    .frame(width: 520)
}
