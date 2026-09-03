import SwiftUI

// MARK: - Why THIS row matched (Daniel, 2026-09-02)
//
// The percentage on the right says how well a row matched. It never said
// HOW, so a row that matched on the literal words and a row that is merely a
// near neighbour in vector space looked identical — which is exactly the
// confusion the honesty surface exists to end.
//
// The engine now rides `metadata.match_sources` on every hit. Two of the
// three legs earn a chip:
//
//   * "exact"  — the literal words are in this document (`fulltext`)
//   * "graph"  — a knowledge-graph entity connected it (`kg`)
//
// Semantic gets NO chip on purpose: it is the leg the % badge already
// describes, and a chip on every row is a chip that says nothing.

/// One leg of the retrieval that claimed a row.
enum SearchMatchSource: String, CaseIterable, Sendable {
    case semantic
    case fulltext
    case kg

    /// The chip's word, or `nil` for the leg the badge already covers.
    var chipLabel: String? {
        switch self {
        case .semantic: return nil
        case .fulltext: return "exact"
        case .kg: return "graph"
        }
    }

    var chipHelp: String {
        switch self {
        case .semantic: return "Matched by meaning"
        case .fulltext: return "Contains the words you typed"
        case .kg: return "Reached through the knowledge graph"
        }
    }

    /// Parse the engine's `match_sources` list, dropping anything unknown
    /// rather than inventing a chip for it.
    static func parse(_ raw: [String]) -> [SearchMatchSource] {
        raw.compactMap { SearchMatchSource(rawValue: $0) }
    }
}

/// The chips for one row, in leg order. Renders nothing when the only leg is
/// semantic — the common case, and the case the badge already explains.
struct SearchMatchSourceChips: View {
    let sources: [SearchMatchSource]

    var body: some View {
        // Ordered by the ladder, not by whatever order the engine listed, so
        // two rows with the same legs always draw the same chips.
        let labels = SearchMatchSource.allCases
            .filter { sources.contains($0) }
            .compactMap { source in source.chipLabel.map { ($0, source.chipHelp) } }
        if !labels.isEmpty {
            HStack(spacing: 4) {
                ForEach(labels, id: \.0) { label, help in
                    Text(label)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(
                            Capsule().fill(.quaternary)
                        )
                        .help(help)
                        .accessibilityLabel(help)
                }
            }
        }
    }
}
