import SwiftUI

/// A page's agreement between its readers in the Inspector (#5665, `source.disagree.inspector`): the page's figure
/// and each line's, labelled agreement, never accuracy. Shown only for a page two readers or more have read; read
/// from the project's `ReadingDisagreementStore`, the same answer the Reader's lens shows.
struct ReadingAgreementInspectorSection: View {
    let document: Document

    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    @Environment(DocumentStore.self) private var documentStore: DocumentStore?

    private var store: ReadingDisagreementStore? {
        documentStore.flatMap { libraryManager?.library(owningService: $0)?.disagreementStore }
    }

    var body: some View {
        if document.docType == .page, let store {
            let pageId = document.id
            ReadingAgreementFigures(disagreement: store.disagreement(of: pageId))
                .task(id: pageId) { await store.load(pageId: pageId) }
        }
    }
}

/// The figures, given the page's disagreement: nothing unless it was read by two readers or more.
struct ReadingAgreementFigures: View {
    let disagreement: ReadingDisagreement?

    /// "Line 3" and its figure, for each line.
    static func lineRows(_ disagreement: ReadingDisagreement) -> [(title: String, figure: String)] {
        disagreement.lines.enumerated().map { index, line in
            ("Line \(index + 1)", ReadingDisagreement.percent(line.agreement))
        }
    }

    var body: some View {
        if let disagreement, disagreement.isComparable {
            VStack(alignment: .leading, spacing: 4) {
                Text("Readers' Agreement").font(.headline)
                if let page = disagreement.pageAgreement {
                    Text("\(ReadingDisagreement.percent(page)) across \(disagreement.readers.count) readers")
                        .font(.callout)
                }
                ForEach(Array(Self.lineRows(disagreement).enumerated()), id: \.offset) { _, row in
                    HStack {
                        Text(row.title).font(.caption)
                        Spacer()
                        Text(row.figure).font(.caption).monospacedDigit().foregroundStyle(.secondary)
                    }
                }
            }
            .accessibilityIdentifier("inspector.readingAgreement")
        }
    }
}

#Preview("Readers' agreement") {
    ReadingAgreementFigures(disagreement: DisagreementPreview.page)
        .padding()
        .frame(width: 280)
}
