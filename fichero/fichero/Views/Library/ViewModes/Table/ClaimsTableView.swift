import FicheroAPIClient
import SwiftUI

// MARK: - Claims table view (the node-model build: a claim flows through the library table)

/// Renders the folder's (or library's) CLAIMS as a native, sortable table —
/// subject · verb · object · date · source page · confidence · provenance — the
/// claim half of "a claim and an entity are nodes that flow through the same
/// library view as a document."
///
/// Reuse, not a parallel surface: rows carry the SAME `LibraryOutlineNode.claimItem`
/// identity the document outline already mints (`"<doc>:claim:<id>"`), write the
/// SAME `selection` set the rest of the library uses, and a row click opens the
/// source page through the SAME `ClaimSourceNavigationState` cursor as every other
/// claim surface. Only the COLUMNS differ from the document table — SwiftUI cannot
/// swap one `Table`'s columns at runtime, so the claim columns live here while
/// everything else is shared. Column values come from the pure `ClaimTableRow`
/// mapper, so what a claim shows is testable off-main and identical everywhere.
struct ClaimsTableView: View {
    /// One claim row: the node (identity + selection), its mapped column values,
    /// and the resolved human name of its source document.
    struct Item: Identifiable {
        let node: LibraryOutlineNode
        let claim: Components.Schemas.KnowledgeClaim
        let values: ClaimTableRow
        let sourceName: String
        var id: String { node.id }
    }

    let items: [Item]
    @Binding var selection: Set<String>
    let isLoading: Bool
    let emptyMessage: String
    /// Open a claim's source page with its passage lit — the host wires this to
    /// `ClaimSourceRequest.request(for:)` on the shared cursor.
    let onOpenSource: (Components.Schemas.KnowledgeClaim) -> Void

    @State private var sortOrder: [KeyPathComparator<Item>] = [
        KeyPathComparator(\Item.values.subject, order: .forward)
    ]

    private var sortedItems: [Item] {
        items.sorted(using: sortOrder)
    }

    var body: some View {
        Group {
            if isLoading && items.isEmpty {
                loadingState
            } else if items.isEmpty {
                emptyState
            } else {
                table
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var table: some View {
        Table(sortedItems, selection: $selection, sortOrder: $sortOrder) {
            TableColumn("Subject", value: \.values.subject) { item in
                Text(item.values.subject).font(.body).lineLimit(1)
            }
            .width(min: 120, ideal: 180)

            TableColumn("Verb", value: \.values.verb) { item in
                // The predicate is the claim-specific part — emphasise it lightly,
                // as the claim card does, so the S-V-O structure reads at a glance.
                Text(item.values.verb).font(.body.weight(.medium)).lineLimit(1)
            }
            .width(min: 80, ideal: 120)

            TableColumn("Object", value: \.values.object) { item in
                Text(item.values.object).font(.body).lineLimit(1)
            }
            .width(min: 120, ideal: 220)

            TableColumn("Date", value: \.values.date) { item in
                Text(item.values.date).font(.callout).foregroundStyle(.secondary).lineLimit(1)
            }
            .width(min: 80, ideal: 110)

            TableColumn("Source", value: \.sourceName) { item in
                // The source page is a door: a row click opens it, but the label
                // itself reads as the page name, never a raw id.
                Label(item.sourceName, systemImage: "doc.text")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            .width(min: 120, ideal: 180)

            TableColumn("Confidence", value: \.values.confidence) { item in
                // Absence renders as nothing (ConfidenceBand honesty), never a
                // substituted midpoint.
                Text(item.values.confidence).font(.callout).foregroundStyle(.secondary)
            }
            .width(min: 80, ideal: 100)

            TableColumn("Provenance", value: \.values.provenance.rawValue) { item in
                ClaimProvenanceBadge(provenance: item.values.provenance)
            }
            .width(min: 90, ideal: 120)
        }
        .tableStyle(.inset)
        #if os(macOS)
        .alternatingRowBackgrounds()
        #endif
        .onChange(of: selection) { _, newSelection in
            // A single-claim selection opens its source page + highlight through
            // the shared cursor — the same "a statement leads to its source"
            // contract as the claim card and the entity biography. A multi-select
            // leaves the reader where it is (no one claim to open).
            //
            // RE-ENTRANCY GUARD: open only a NEW single selection. Navigating to
            // the source can write state that re-enters this handler; without the
            // lastOpenedId latch that fed open→render→open every cycle, part of
            // the Touch Bar layout-loop crash. A cleared/multi selection resets
            // the latch so re-selecting the same row later still opens.
            guard newSelection.count == 1, let id = newSelection.first else {
                lastOpenedId = nil
                return
            }
            guard id != lastOpenedId, let item = items.first(where: { $0.id == id }) else { return }
            lastOpenedId = id
            onOpenSource(item.claim)
        }
    }

    /// The last id auto-opened, so a re-render can't re-open it in a loop.
    @State private var lastOpenedId: String?

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading claims…").font(.callout).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "quote.bubble").font(.largeTitle).foregroundStyle(.secondary)
            Text(emptyMessage)
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}

/// The provenance lozenge — where a claim's number came from / how far it's been
/// curated. Colours mirror the curation badge (green = blessed, red = rejected),
/// with the extractor origins muted so a machine claim never dresses up as review.
struct ClaimProvenanceBadge: View {
    let provenance: ClaimTableRow.Provenance

    var body: some View {
        Text(provenance.rawValue)
            .font(.caption2)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.16), in: Capsule())
            .foregroundStyle(color)
    }

    private var color: Color {
        switch provenance {
        case .blessed: return .green
        case .human: return .blue
        case .llm: return .purple
        case .heuristic: return .orange
        case .rejected: return .red
        case .unknown: return .gray
        }
    }
}
