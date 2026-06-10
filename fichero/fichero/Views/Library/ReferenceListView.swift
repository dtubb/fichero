import FicheroAPIClient
import SwiftUI

/// A native `List(selection:)` of a document's bibliography (#2005, EPIC #2002).
///
/// Replaces the stacked `DocumentBibliographyPanel` rows: each row is a
/// *lightweight* summary (title + authors/year), NOT the full reference with
/// its BibTeX block. Selecting a row drives the shared `FocusedReference`, which
/// the detail view (inline and detached window) observes.
///
/// Conventions honoured (same as `ArtifactListView`):
/// - Native `List(selection:)`, not a hand-rolled tappable `VStack`.
/// - Semantic system fonts only.
/// - Rows key off the stable `ReferenceItem.id`.
struct ReferenceListView: View {
    /// The reactive data source — the document-scoped store (#1999).
    let store: ReferenceStore

    /// Shared selection holder the rows write to.
    @Bindable var focused: FocusedReference

    /// Open the selected reference in a separate, draggable window. `nil` hides
    /// the affordance.
    var onOpenInWindow: (() -> Void)?

    /// Self-reference first, then the cited references in store order.
    private var items: [ReferenceItem] {
        let selfItems = store.selfRef.map { [ReferenceItem(reference: $0, isSelf: true)] } ?? []
        return selfItems + store.references.map { ReferenceItem(reference: $0, isSelf: false) }
    }

    var body: some View {
        List(selection: $focused.id) {
            ForEach(items) { item in
                row(for: item)
            }
        }
        .listStyle(.inset)
        .overlay {
            if items.isEmpty {
                emptyState
            }
        }
        .onChange(of: focused.id) { _, _ in
            focused.resolve(in: items)
        }
        .onChange(of: store.references) { _, _ in focused.resolve(in: items) }
        .onChange(of: store.selfRef) { _, _ in focused.resolve(in: items) }
    }

    @ViewBuilder
    private func row(for item: ReferenceItem) -> some View {
        ReferenceRow(item: item)
            .tag(item.id)
            .contextMenu {
                if let onOpenInWindow {
                    Button("Open in Window") {
                        focused.select(item.id, in: items)
                        onOpenInWindow()
                    }
                }
            }
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "books.vertical")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No bibliography extracted yet")
                .font(.callout)
            Text("Run a workflow that includes citation extraction to populate this list.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 16)
    }
}

/// One lightweight reference row — title, plus an authors / year subtitle.
/// Renders no BibTeX block (that's the detail's job).
private struct ReferenceRow: View {
    let item: ReferenceItem

    private var reference: Components.Schemas.Reference { item.reference }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: item.isSelf ? "doc.text" : "book.closed")
                .foregroundStyle(.secondary)
                .frame(width: 18)
                .help(item.isSelf ? "This document" : "Cited reference")
            VStack(alignment: .leading, spacing: 1) {
                Text(item.title)
                    .font(.body)
                    .lineLimit(2)
                if let subtitle {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            Spacer(minLength: 4)
            if let year = reference.year {
                Text(String(year))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
    }

    private var subtitle: String? {
        var parts: [String] = []
        if let authors = reference.authors, !authors.isEmpty {
            parts.append(authors.prefix(2).joined(separator: ", "))
        }
        if let journal = reference.journalOrBook, !journal.isEmpty {
            parts.append(journal)
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}
