import SwiftUI

/// WHAT kind of node the library is browsing — documents, or the knowledge-graph
/// nodes (claims / entities) that also live in a folder.
///
/// Orthogonal to `ViewDisplayMode` (HOW they're laid out): the north-star is that
/// a claim and an entity are NODES that flow through the same library views and
/// the same sidebar as a document. Phase 1 lands `.claims` in the table; `.entities`
/// (Phase 2) and the library-wide sidebar scoping (Phase 3) reuse this same axis.
enum LibraryContentKind: String, CaseIterable, Identifiable {
    case documents
    case claims
    case entities

    var id: String { rawValue }

    var label: String {
        switch self {
        case .documents: return "Documents"
        case .claims: return "Claims"
        case .entities: return "Entities"
        }
    }

    var systemImage: String {
        switch self {
        case .documents: return "doc.text"
        case .claims: return "quote.bubble"
        case .entities: return "person.2"
        }
    }
}
