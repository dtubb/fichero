import FicheroAPIClient
import SwiftUI

/// The shared renderer for ONE reference (#2005, EPIC #2002).
///
/// Shown both **inline** in the inspector (below `ReferenceListView`) and in the
/// **detached window** torn off from it. Read-only: references are extracted
/// data, so there is no edit/delete path. Surfaces the reference's full fields
/// plus a copyable BibTeX block (the affordance the old
/// `DocumentBibliographyPanel` row offered, now in a roomy detail).
struct ReferenceDetailView: View {
    /// The reference to render. `nil` shows the empty state.
    let item: ReferenceItem?

    @State private var copied = false

    var body: some View {
        Group {
            if let item {
                ScrollView {
                    content(for: item)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            } else {
                emptyState
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    @ViewBuilder
    private func content(for item: ReferenceItem) -> some View {
        let reference = item.reference
        VStack(alignment: .leading, spacing: 12) {
            if item.isSelf {
                Label("This document", systemImage: "doc.text")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
            }

            Text(item.title)
                .font(.headline)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)

            metadataGrid(for: reference)

            if let bibtex = reference.bibtex, !bibtex.isEmpty {
                Divider()
                HStack {
                    Text("BibTeX")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button {
                        PlatformPasteboard.writeString(bibtex)
                        copied = true
                    } label: {
                        Label(copied ? "Copied!" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                            .font(.caption2)
                    }
                    .buttonStyle(.borderless)
                    .onChange(of: copied) { _, newValue in
                        if newValue {
                            Task {
                                try? await Task.sleep(for: .seconds(1.5))
                                copied = false
                            }
                        }
                    }
                }
                Text(bibtex)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                    .background(Color(.textBackgroundColor).opacity(0.6))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
            }
        }
        // Reset the copy state when the shown reference changes.
        .id(item.id)
    }

    @ViewBuilder
    private func metadataGrid(for reference: Components.Schemas.Reference) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let authors = reference.authors, !authors.isEmpty {
                LabeledContent("Authors", value: authors.joined(separator: ", "))
            }
            if let year = reference.year {
                LabeledContent("Year", value: String(year))
            }
            if let journal = reference.journalOrBook, !journal.isEmpty {
                LabeledContent("Published in", value: journal)
            }
            if let publisher = reference.publisher, !publisher.isEmpty {
                LabeledContent("Publisher", value: publisher)
            }
            if let doi = reference.doi, !doi.isEmpty {
                LabeledContent("DOI", value: doi)
            }
            if let isbn = reference.isbn, !isbn.isEmpty {
                LabeledContent("ISBN", value: isbn)
            }
            if let pages = reference.pages, !pages.isEmpty {
                LabeledContent("Pages", value: pages)
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "books.vertical")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No reference selected")
                .font(.callout)
            Text("Pick a reference from the list to see its details.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.vertical, 32)
    }
}
