import FicheroAPIClient
import SwiftUI

/// A native `List(selection:)` of a document's citations (#2004, EPIC #2002).
///
/// Replaces the stacked `CitationGraphPanel` rows: each row is a *lightweight*
/// summary (direction icon + citation text + page badge), NOT the full citation
/// with its supported claims. Selecting a row drives the shared
/// `FocusedCitation`, which the detail view (inline and detached window)
/// observes.
///
/// Conventions honoured (same as `ArtifactListView`):
/// - Native `List(selection:)`, not a hand-rolled tappable `VStack`.
/// - Semantic system fonts only, so rows scale with system text size.
/// - Rows key off the stable `CitationItem.id`, so one citation's update
///   re-renders that row in place rather than reloading the whole list.
struct CitationListView: View {
    /// The reactive data source — the document-scoped store (#1998).
    let store: CitationStore

    /// Shared selection holder the rows write to.
    @Bindable var focused: FocusedCitation

    /// Open the selected citation in a separate, draggable window. `nil` hides
    /// the affordance.
    var onOpenInWindow: (() -> Void)?

    /// Outbound (cites) first, then inbound (cited by); newest text grouping is
    /// not meaningful here, so within a direction we keep the store's order.
    private var items: [CitationItem] {
        store.outbound.map { CitationItem(citation: $0, direction: .outbound) }
            + store.inbound.map { CitationItem(citation: $0, direction: .inbound) }
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
        // Keep the snapshot current when the store reloads (workflow re-run,
        // change-stream echo) without the selection id itself changing.
        .onChange(of: store.outbound) { _, _ in focused.resolve(in: items) }
        .onChange(of: store.inbound) { _, _ in focused.resolve(in: items) }
    }

    @ViewBuilder
    private func row(for item: CitationItem) -> some View {
        CitationRow(item: item)
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

    private var emptyState: some View {
        // Standardized on ContentUnavailableView (#3039).
        ContentUnavailableView(
            "No citations recorded",
            systemImage: "text.quote",
            description: Text("Run a workflow that includes citation extraction to populate this list.")
        )
    }
}

/// One lightweight citation row — direction icon, citation text, and small
/// page / confidence badges. Renders no claims body (that's the detail's job).
private struct CitationRow: View {
    let item: CitationItem

    private var citation: Components.Schemas.DocumentCitation { item.citation }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: item.direction.icon)
                .foregroundStyle(.secondary)
                .frame(width: 18)
                .help(item.direction.label)
            VStack(alignment: .leading, spacing: 1) {
                Text(citation.targetCitationText)
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
            if let confidence = citation.confidence {
                Text(String(format: "%.2f", confidence))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
    }

    private var subtitle: String? {
        var parts: [String] = []
        if let page = citation.pageLabel, !page.isEmpty { parts.append("p. \(page)") }
        if let detector = citation.detector, !detector.isEmpty { parts.append(detector) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}
