import FicheroAPIClient
import Foundation
import Observation

/// A node in the expandable library outline (#2258).
///
/// The library Table is an OUTLINE: each document row can disclose its
/// children. Those children are NOT `Document`s — they are the typed
/// knowledge objects attached to the document (artifacts, entities,
/// notes, claims), assembled from the per-library observable stores and
/// the cheap `GET /documents/{id}/rollup` counts. This value type is the
/// uniform row model the `DisclosureTableRow` hierarchy renders.
///
/// A `.document` node carries the underlying `Document` so the name /
/// status / output columns render exactly as the flat table did. A
/// `.childGroup` node is a leaf summarising one type ("12 entities");
/// expanding the document fetches the rollup and materialises one
/// child-group node per non-empty type.
struct LibraryOutlineNode: Identifiable, Hashable {
    enum Kind: Hashable {
        case document
        case childGroup(ChildType)
    }

    /// The typed child collections a document can disclose. Order here is
    /// the display order under an expanded document row.
    enum ChildType: String, CaseIterable, Hashable {
        case pages
        case artifacts
        case entities
        case notes
        case claims

        /// Human label shown in the outline (singular/plural handled by
        /// `groupLabel(count:)`).
        var noun: String {
            switch self {
            case .pages: return "page"
            case .artifacts: return "artifact"
            case .entities: return "entity"
            case .notes: return "note"
            case .claims: return "claim"
            }
        }

        /// SF Symbol for the group row. Native, no emoji.
        var systemImage: String {
            switch self {
            case .pages: return "doc.on.doc"
            case .artifacts: return "shippingbox"
            case .entities: return "person.2"
            case .notes: return "note.text"
            case .claims: return "quote.bubble"
            }
        }

        func groupLabel(count: Int) -> String {
            let plural = noun == "entity" ? "entities" : "\(noun)s"
            return "\(count) \(count == 1 ? noun : plural)"
        }
    }

    let kind: Kind
    /// The owning document. Present on both `.document` nodes and the
    /// `.childGroup` nodes beneath them (so a child row knows its parent
    /// document for selection / drill-down).
    let document: Document
    /// For `.childGroup` nodes: how many children of that type exist.
    let count: Int
    /// Child rows. `nil` until the document's rollup has loaded (so the
    /// disclosure triangle shows but the children stream in); an empty
    /// array means "loaded, no children". On `.childGroup` nodes this is
    /// always `nil` (leaf).
    var children: [LibraryOutlineNode]?

    /// Stable identity. Document nodes key on the document id; child-group
    /// nodes namespace the type so they never collide with the document.
    var id: String {
        switch kind {
        case .document:
            return document.id
        case .childGroup(let type):
            return "\(document.id):\(type.rawValue)"
        }
    }

    static func document(_ document: Document, children: [LibraryOutlineNode]?) -> LibraryOutlineNode {
        LibraryOutlineNode(kind: .document, document: document, count: 0, children: children)
    }

    static func childGroup(_ type: ChildType, document: Document, count: Int) -> LibraryOutlineNode {
        LibraryOutlineNode(kind: .childGroup(type), document: document, count: count, children: nil)
    }
}

extension LibraryOutlineNode.ChildType {
    /// Extract this type's count from a rollup response.
    func count(in rollup: Components.Schemas.DocumentRollupResponse) -> Int {
        switch self {
        case .pages: return rollup.pages
        case .artifacts: return rollup.artifacts
        case .entities: return rollup.entities
        case .notes: return rollup.notes
        case .claims: return rollup.claims
        }
    }
}

/// Lazily fetches and caches per-document rollup counts so the outline
/// Table can show child-group rows under an expanded document without
/// pre-fetching every document's children (#2258).
///
/// Build the child-group nodes for a document from its cached rollup;
/// a document with no cached rollup yet returns `nil` children (the
/// disclosure stays empty until `loadRollup` resolves), keeping the
/// collapsed-by-default Table cheap.
@MainActor
@Observable
final class LibraryOutlineModel {
    /// document id -> rollup counts. Bumping this dictionary re-renders
    /// only the affected rows (value identity is per-document).
    private(set) var rollups: [String: Components.Schemas.DocumentRollupResponse] = [:]
    /// In-flight / failed ids so we never double-fetch or hammer a
    /// 404'd document on every disclosure toggle.
    private var requested: Set<String> = []

    private let service: EntityServiceGenerated

    init(service: EntityServiceGenerated) {
        self.service = service
    }

    /// Fetch the rollup for a document once. Idempotent: repeat calls
    /// for the same id (already loaded or in flight) are no-ops.
    func loadRollup(for documentId: String) async {
        guard rollups[documentId] == nil, !requested.contains(documentId) else { return }
        requested.insert(documentId)
        do {
            rollups[documentId] = try await service.documentRollup(documentId: documentId)
        } catch {
            // A missing/failed rollup must not break the table — the row
            // simply shows no disclosed children. `requested` keeps the
            // failure sticky so we don't retry on every toggle.
        }
    }

    /// Build the typed child-group nodes for one document from its cached
    /// rollup. Returns `nil` if the rollup has not loaded yet (disclosure
    /// shows but is empty); an empty array means the document genuinely
    /// has no children of any type.
    func childNodes(for document: Document) -> [LibraryOutlineNode]? {
        guard let rollup = rollups[document.id] else { return nil }
        return LibraryOutlineNode.ChildType.allCases.compactMap { type in
            let count = type.count(in: rollup)
            guard count > 0 else { return nil }
            return LibraryOutlineNode.childGroup(type, document: document, count: count)
        }
    }

    /// Assemble the top-level outline nodes for the visible documents.
    /// Each document node carries whatever child nodes are already known;
    /// expanding a row triggers `loadRollup` to fill them in.
    func nodes(for documents: [Document]) -> [LibraryOutlineNode] {
        documents.map { document in
            LibraryOutlineNode.document(document, children: childNodes(for: document))
        }
    }
}
