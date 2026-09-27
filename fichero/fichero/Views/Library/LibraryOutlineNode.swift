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
        /// An individual page document (PDF child) — shows as a navigable row (#2405).
        case pageItem(Document)
        /// An individual artifact belonging to a document (#2405).
        case artifactItem(Artifact)
        /// An individual entity belonging to a document's KG rollup.
        case entityItem(Components.Schemas.KnowledgeEntity)
        /// An individual claim belonging to a document's KG rollup.
        case claimItem(Components.Schemas.KnowledgeClaim)
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
    /// array means "loaded, no children". On `.childGroup` nodes a non-empty
    /// array means the aggregate row should disclose its typed children.
    var children: [LibraryOutlineNode]?

    /// Stable identity. Document nodes key on the document id; child-group
    /// nodes namespace the type so they never collide with the document.
    var id: String {
        switch kind {
        case .document:
            return document.id
        case .childGroup(let type):
            return "\(document.id):\(type.rawValue)"
        case .pageItem(let page):
            return "\(document.id):page:\(page.id)"
        case .artifactItem(let artifact):
            return "\(document.id):artifact:\(artifact.id)"
        case .entityItem(let entity):
            return "\(document.id):entity:\(entity.id ?? entity.stableInspectorId)"
        case .claimItem(let claim):
            return "\(document.id):claim:\(claim.id ?? claim.displayMergeName)"
        }
    }

    static func document(_ document: Document, children: [LibraryOutlineNode]?) -> LibraryOutlineNode {
        LibraryOutlineNode(kind: .document, document: document, count: 0, children: children)
    }

    static func childGroup(
        _ type: ChildType,
        document: Document,
        count: Int,
        children: [LibraryOutlineNode]? = nil
    ) -> LibraryOutlineNode {
        LibraryOutlineNode(kind: .childGroup(type), document: document, count: count, children: children)
    }

    static func pageItem(_ page: Document, parent: Document) -> LibraryOutlineNode {
        LibraryOutlineNode(kind: .pageItem(page), document: parent, count: 0, children: nil)
    }

    static func artifactItem(_ artifact: Artifact, parent: Document) -> LibraryOutlineNode {
        LibraryOutlineNode(kind: .artifactItem(artifact), document: parent, count: 0, children: nil)
    }

    static func entityItem(
        _ entity: Components.Schemas.KnowledgeEntity,
        parent: Document
    ) -> LibraryOutlineNode {
        LibraryOutlineNode(kind: .entityItem(entity), document: parent, count: 0, children: nil)
    }

    static func claimItem(
        _ claim: Components.Schemas.KnowledgeClaim,
        parent: Document
    ) -> LibraryOutlineNode {
        LibraryOutlineNode(kind: .claimItem(claim), document: parent, count: 0, children: nil)
    }

    /// Disclosure only with something to disclose (Daniel, 2026-08-09).
    /// ponytail: artifact-only rows chevron only once their rollup lands.
    var canExpand: Bool {
        switch kind {
        case .document:
            return !(children?.isEmpty ?? true) || document.childCount > 0
        case .childGroup:
            return !(children?.isEmpty ?? true)
        case .pageItem, .artifactItem, .entityItem, .claimItem:
            return false
        }
    }
}

extension LibraryOutlineNode {
    /// Depth-first flatten of the outline into the row ids the Table
    /// actually SHOWS (#4198): a node's children count only while that node
    /// is expanded. This is the Finder-style "visible rows" set — ⌘A and
    /// select-all span it, exactly like Finder's list view. No toggle: an
    /// expanded row is simply selectable.
    static func visibleIds(of nodes: [LibraryOutlineNode], expanded: Set<String>) -> [String] {
        var ids: [String] = []
        for node in nodes {
            ids.append(node.id)
            if node.canExpand, expanded.contains(node.id), let children = node.children {
                ids.append(contentsOf: visibleIds(of: children, expanded: expanded))
            }
        }
        return ids
    }

    /// The parsed shape of an outline node id (#4850). `id` mints three
    /// shapes: a document row (`"<documentId>"`), a group row
    /// (`"<documentId>:<pluralType>"`), or an item row
    /// (`"<documentId>:<singularType>:<itemId>"`). `itemId` is non-nil ONLY
    /// for an item row — a group row's `childType` is set with `itemId` nil.
    struct ParsedNodeId: Equatable {
        let documentId: String
        let childType: ChildType?
        let itemId: String?
    }

    /// Item-row markers, singular, each with its trailing colon so the
    /// itemId after it is found by searching the WHOLE string from the
    /// RIGHT — never the first colon. A document id may itself contain
    /// colons (default-workflow subfolders are "container:<name>"), so the
    /// marker actually minted by `id` (the LAST one in the string) is the
    /// only reliable split point. This is the same class of bug #4850
    /// found: a composite id like "<doc>:entity:<id>" reaching code that
    /// expected a bare entity id.
    private static let itemMarkers: [(marker: String, type: ChildType)] = [
        (":page:", .pages), (":artifact:", .artifacts), (":entity:", .entities), (":claim:", .claims)
    ]

    /// Group-row markers, plural, matched as a SUFFIX (a group row has
    /// nothing after the type word).
    private static let groupMarkers: [(marker: String, type: ChildType)] =
        ChildType.allCases.map { (":\($0.rawValue)", $0) }

    /// Parse a node id into its document id, child type (if any), and item
    /// id (if it's an item row). Item markers are checked before group
    /// markers, since an item row's shape is a strict superset of a group
    /// row's (both start "<doc>:<word>"; only an item row has content
    /// after it). Residual ambiguity, same as the old `childRowType`'s own
    /// note: a document id that itself happens to contain a marker
    /// substring (e.g. a folder literally named "entity" immediately
    /// followed by another colon segment) is not distinguishable from a
    /// real item row by string shape alone — not solved here, not worse
    /// than before.
    static func parse(nodeId: String) -> ParsedNodeId {
        for (marker, type) in itemMarkers {
            if let range = nodeId.range(of: marker, options: .backwards) {
                let documentId = String(nodeId[nodeId.startIndex..<range.lowerBound])
                let itemId = String(nodeId[range.upperBound...])
                return ParsedNodeId(documentId: documentId, childType: type, itemId: itemId)
            }
        }
        for (marker, type) in groupMarkers where nodeId.hasSuffix(marker) {
            let documentId = String(nodeId.dropLast(marker.count))
            return ParsedNodeId(documentId: documentId, childType: type, itemId: nil)
        }
        return ParsedNodeId(documentId: nodeId, childType: nil, itemId: nil)
    }

    /// Classify an outline node id back to its child-row type, or nil for a
    /// document row / unrecognised id. Re-expressed on `parse(nodeId:)`
    /// (#4850) — was its own naive `split(separator: ":")` taking
    /// `parts[1]`, which had the identical colon-bearing-document-id
    /// fragility `parse` fixes, just for a TYPE lookup rather than an id.
    static func childRowType(forNodeId id: String) -> ChildType? {
        parse(nodeId: id).childType
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
