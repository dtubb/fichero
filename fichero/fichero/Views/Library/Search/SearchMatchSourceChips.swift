import SwiftUI

// MARK: - Why THIS row matched (Daniel, 2026-09-02)
//
// The percentage on the right says how well a row matched. It never said
// HOW, so a row that matched on the literal words and a row that is merely a
// near neighbour in vector space looked identical — which is exactly the
// confusion the honesty surface exists to end.
//
// The engine rides `metadata.match_sources` on every hit. The legs that add
// something the % badge does not already say earn a chip:
//
//   * "exact"  — the literal words are in this document (`fulltext`)
//   * "entity" — an entity record's name matched (`entity`)
//   * "claim"  — a recorded claim matched (`claim`)
//   * "graph"  — the knowledge-graph fusion leg connected it (`kg`)
//
// Semantic gets NO chip on purpose: it is the leg the % badge already
// describes, and a chip on every row is a chip that says nothing.
//
// `entity` and `claim` are DISTINCT from `graph` (Daniel, 2026-09-03: rows
// were badged "graph" in a library with essentially no graph, while the graph
// tier was off). The entity and claim legs are semantic searches over the
// entity/claim tables — `include: [.entities, .claims]`, which the shell sends
// on every search. The graph leg is the opt-in `hybrid_graph` RRF fusion leg,
// and it is the ONLY thing entitled to the word "graph". Labelling an entity
// name hit as a graph traversal claimed a capability the library had not been
// given, which is the opposite of the honesty surface's job.

/// One leg of the retrieval that claimed a row.
enum SearchMatchSource: String, CaseIterable, Sendable {
    case semantic
    case fulltext
    case entity
    case claim
    case kg

    /// The chip's word, or `nil` for the leg the badge already covers.
    var chipLabel: String? {
        switch self {
        case .semantic: return nil
        case .fulltext: return "exact"
        case .entity: return "entity"
        case .claim: return "claim"
        case .kg: return "graph"
        }
    }

    var chipHelp: String {
        switch self {
        case .semantic: return "Matched by meaning"
        case .fulltext: return "Contains the words you typed"
        case .entity: return "Matched the name of an entity in this library"
        case .claim: return "Matched a claim recorded about this document"
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
