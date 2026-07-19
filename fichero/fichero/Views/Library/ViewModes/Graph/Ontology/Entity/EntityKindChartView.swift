import Charts
import FicheroAPIClient
import SwiftUI

// MARK: - EntityKindChartView (#902 Charts overlay)

/// At-a-glance entity-type distribution. Renders a bar chart of the
/// filteredEntities passed in from OntologyBrowser so toggling the kind
/// filter in the toolbar updates the chart live. Pairs with the same
/// color palette used in `ForceDirectedGraphView` so a glance across
/// modes stays consistent.
struct EntityKindChartView: View {
    let entities: [Components.Schemas.KnowledgeEntity]

    /// One bar per kind. Keeps the canonical order (person → place →
    /// organization → event → concept → other) so the chart's reading
    /// order matches the filter menu and the legend.
    private static let kindOrder: [Components.Schemas.EntityTypeOutput] = [
        .person, .location, .organization, .event, .concept, .other
    ]

    private struct KindCount: Identifiable {
        let kind: Components.Schemas.EntityTypeOutput
        let label: String
        let count: Int
        var id: String { label }
    }

    private var counts: [KindCount] {
        var bucket: [Components.Schemas.EntityTypeOutput: Int] = [:]
        for entity in entities {
            let key = entity.entityType ?? .other
            bucket[key, default: 0] += 1
        }
        return Self.kindOrder.map { kind in
            KindCount(kind: kind, label: Self.label(for: kind), count: bucket[kind] ?? 0)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Entities by kind")
                .font(.headline)
                .foregroundStyle(.primary)
            Text("\(entities.count) entities total")
                .font(.caption)
                .foregroundStyle(.secondary)
            Chart(counts) { row in
                BarMark(
                    x: .value("Count", row.count),
                    y: .value("Kind", row.label)
                )
                .foregroundStyle(color(for: row.kind))
                .annotation(position: .trailing, alignment: .leading) {
                    // `row.count` is an Int (entity count), not a collection
                    // size — empty_count's isEmpty suggestion doesn't apply.
                    // swiftlint:disable:next empty_count
                    if row.count > 0 {
                        Text("\(row.count)")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis {
                AxisMarks(preset: .aligned, position: .leading) { _ in
                    AxisValueLabel().font(.caption2)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color(.controlBackgroundColor))
    }

    private static func label(for kind: Components.Schemas.EntityTypeOutput) -> String {
        switch kind {
        case .person: return "People"
        case .location: return "Places"
        case .organization: return "Organizations"
        case .event: return "Events"
        case .concept: return "Concepts"
        case .citation: return "Citations"
        case .other: return "Other"
        }
    }

    // Mirrors the palette in ForceDirectedGraphView.color(for:) so the
    // colors line up across modes.
    private func color(for kind: Components.Schemas.EntityTypeOutput) -> Color {
        switch kind {
        case .person: return .blue
        case .organization: return .purple
        case .location: return .green
        case .event: return .orange
        case .concept: return .yellow
        case .citation: return .brown
        case .other: return .gray
        }
    }
}
