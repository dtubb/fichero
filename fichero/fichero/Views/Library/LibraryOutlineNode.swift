import FicheroAPIClient
import Foundation
import Observation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "LibraryOutlineModel")

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
    /// Internal (not private) so tests can inject state directly.
    var rollups: [String: Components.Schemas.DocumentRollupResponse] = [:]
    /// In-flight / failed ids so we never double-fetch or hammer a
    /// 404'd document on every disclosure toggle.
    private var requested: Set<String> = []

    /// Page documents grouped by their parent document id.
    /// Populated by LibraryView from documentStore.currentDocuments
    /// (pages are already loaded — no extra fetch needed).
    var pagesByParentId: [String: [Document]] = [:]

    /// Own-scope artifacts (non-descendant) by document id.
    /// Populated on demand when a document row is expanded.
    /// Internal (not private) so tests can inject state directly.
    var artifactsByDocumentId: [String: [Artifact]] = [:]
    private var artifactRequested: Set<String> = []
    var entitiesByDocumentId: [String: [Components.Schemas.KnowledgeEntity]] = [:]
    private var entityRequested: Set<String> = []
    var claimsByDocumentId: [String: [Components.Schemas.KnowledgeClaim]] = [:]
    private var claimRequested: Set<String> = []

    private let service: EntityServiceGenerated
    private let artifactService: ArtifactServiceGenerated

    init(service: EntityServiceGenerated, artifactService: ArtifactServiceGenerated) {
        self.service = service
        self.artifactService = artifactService
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

    /// Fetch own-scope artifacts for a document once (non-descendant, matching
    /// the V2 inspector scope). Idempotent — subsequent calls while in-flight
    /// or already loaded are no-ops.
    func loadArtifacts(for documentId: String) async {
        guard artifactsByDocumentId[documentId] == nil,
              !artifactRequested.contains(documentId) else { return }
        artifactRequested.insert(documentId)
        do {
            let arts = try await artifactService.getArtifacts(
                forDocumentId: documentId,
                includeDescendants: false
            )
            artifactsByDocumentId[documentId] = arts
        } catch {
            logger.debug("Artifact load failed for \(documentId): \(error)")
            // Failure keeps the count-fallback group visible until next expansion.
        }
    }

    func loadEntities(for documentId: String) async {
        guard entitiesByDocumentId[documentId] == nil,
              !entityRequested.contains(documentId) else { return }
        entityRequested.insert(documentId)
        do {
            entitiesByDocumentId[documentId] = try await artifactService.listInspectorEntitiesForDocument(
                documentId: documentId
            )
        } catch {
            logger.debug("Entity load failed for \(documentId): \(error)")
        }
    }

    func loadClaims(for documentId: String) async {
        guard claimsByDocumentId[documentId] == nil,
              !claimRequested.contains(documentId) else { return }
        claimRequested.insert(documentId)
        do {
            claimsByDocumentId[documentId] = try await artifactService.listClaims(
                sourceDocumentId: documentId,
                includeDescendants: false,
                limit: 500
            )
        } catch {
            logger.debug("Claim load failed for \(documentId): \(error)")
        }
    }

    // swiftlint:disable cyclomatic_complexity
    /// Build the typed child nodes for one document from its cached rollup.
    /// - Pages → individual page item rows (from pagesByParentId, already loaded).
    /// - Artifacts → individual artifact item rows once loaded; count-group fallback until then.
    /// - Entities / notes / claims → count-group rows as before.
    /// Returns `nil` if the rollup has not loaded yet (disclosure shows but is empty).
    func childNodes(for document: Document) -> [LibraryOutlineNode]? {
        guard let rollup = rollups[document.id] else { return nil }
        var nodes: [LibraryOutlineNode] = []
        for type in LibraryOutlineNode.ChildType.allCases {
            switch type {
            case .pages:
                let pages = (pagesByParentId[document.id] ?? [])
                    .sorted { ($0.sequence ?? 0) < ($1.sequence ?? 0) }
                nodes += pages.map { LibraryOutlineNode.pageItem($0, parent: document) }
            case .artifacts:
                if let arts = artifactsByDocumentId[document.id] {
                    nodes += arts.map { LibraryOutlineNode.artifactItem($0, parent: document) }
                } else if rollup.artifacts > 0 {
                    // Show count summary until per-document fetch completes.
                    nodes.append(
                        LibraryOutlineNode.childGroup(type, document: document, count: rollup.artifacts)
                    )
                }
            case .entities:
                let count = type.count(in: rollup)
                if let entities = entitiesByDocumentId[document.id] {
                    let children = entities.map { LibraryOutlineNode.entityItem($0, parent: document) }
                    nodes.append(LibraryOutlineNode.childGroup(type, document: document, count: count, children: children))
                } else if count > 0 {
                    nodes.append(LibraryOutlineNode.childGroup(type, document: document, count: count))
                }
            case .claims:
                let count = type.count(in: rollup)
                if let claims = claimsByDocumentId[document.id] {
                    let children = claims.map { LibraryOutlineNode.claimItem($0, parent: document) }
                    nodes.append(LibraryOutlineNode.childGroup(type, document: document, count: count, children: children))
                } else if count > 0 {
                    nodes.append(LibraryOutlineNode.childGroup(type, document: document, count: count))
                }
            case .notes:
                let count = type.count(in: rollup)
                if count > 0 {
                    nodes.append(LibraryOutlineNode.childGroup(type, document: document, count: count))
                }
            }
        }
        return nodes
    }
    // swiftlint:enable cyclomatic_complexity

    /// Assemble the top-level outline nodes for the visible documents.
    /// Each document node carries whatever child nodes are already known;
    /// expanding a row triggers `loadRollup` + `loadArtifacts` to fill them in.
    func nodes(for documents: [Document]) -> [LibraryOutlineNode] {
        documents.map { document in
            LibraryOutlineNode.document(document, children: childNodes(for: document))
        }
    }
}
