import FicheroAPIClient
import Foundation

// Where the projection lives:
//
//   ┌─ Backend (today) ─────────┐    ┌─ Projector (this file) ─┐    ┌─ Renderer ──┐
//   │ /api/documents            │ →  │  build nodes + links     │ →  │ Spatial2DCanvas
//   │ /api/entities             │    │  pure data → data        │    │ (live 2D view)
//   │ /api/claims               │    │  seeded phyllotaxis      │    │
//   └───────────────────────────┘    └──────────────────────────┘    └─────────────┘
//
// Phase 1 composes everything client-side because the backend doesn't yet have
// a single "library scene" endpoint. Per `feedback_kg_logic_in_backend`,
// positions and the projection should ultimately live in the backend (planned
// for Phase 4 — `/api/spatial/library/scene`). This file is the temporary
// bridge so the renderer can be built and tested NOW without waiting for that
// endpoint.

/// Pure-data input the projector turns into nodes + links. Decoupled from the
/// generated schemas so it can be tested without spinning up the engine.
struct SpatialLibraryInput: Hashable {
    /// One library document — a real file in the catalogue.
    struct Document: Hashable {
        let id: String
        let name: String
        let parentId: String?
    }

    /// One KG entity — a canonical "thing" the extractor surfaced.
    struct Entity: Hashable {
        let id: String
        let canonicalName: String
        let entityType: String?
    }

    /// One KG claim, projected onto the entity IDs it mentions and the
    /// document it came from. We don't need the claim text itself for the
    /// projection — just the connectedness.
    struct Claim: Hashable {
        let id: String
        let predicateVerb: String?
        let sourceDocumentId: String?
        let entityIds: [String]
    }

    let documents: [Document]
    let entities: [Entity]
    let claims: [Claim]
}

/// Pure-data output the renderer consumes.
struct SpatialLibraryProjection: Hashable {
    /// Spatial nodes (documents + entities), with stable IDs.
    let nodes: [SpatialNode]
    /// Typed links between the spatial nodes.
    let links: [SpatialLink]

    var isEmpty: Bool { nodes.isEmpty }
}

enum SpatialLibraryProjector {

    // MARK: - Stable spatial-node IDs

    /// Spatial node ID for a document — stable across projections so the same
    /// doc lands at the same position in a redraw.
    static func nodeId(forDocument docId: String) -> String { "doc:\(docId)" }

    /// Spatial node ID for an entity — same stability guarantee.
    static func nodeId(forEntity entityId: String) -> String { "entity:\(entityId)" }

    /// The document id inside a `doc:<id>` spatial node id, or nil for a
    /// non-document node (entity / canvas item). The inverse of
    /// `nodeId(forDocument:)`, used by drag-onto to reach `document.move` (#3086).
    static func documentId(fromNodeId nodeId: String) -> String? {
        nodeId.hasPrefix("doc:") ? String(nodeId.dropFirst("doc:".count)) : nil
    }

    // MARK: - Pure projection (testable)

    /// Build the projection from raw library data. Deterministic: same input →
    /// same output, including positions.
    ///
    /// Layout (Phase-1 placeholder per design doc): golden-angle phyllotaxis
    /// on the XZ plane for documents, slightly raised in Y for entities. Index
    /// order is `documents` first, then `entities`, so adding documents at the
    /// end doesn't reshuffle existing positions.
    static func project(_ input: SpatialLibraryInput) -> SpatialLibraryProjection {
        var nodes: [SpatialNode] = []
        nodes.reserveCapacity(input.documents.count + input.entities.count)

        let docCount = input.documents.count
        let entityCount = input.entities.count
        let goldenAngle = .pi * (3.0 - sqrt(5.0))           // ~2.39996 rad

        // Document cards on the base plane.
        let docRadiusStep = max(0.6, 0.18 + 0.02 * Double(docCount).squareRoot())
        for (index, doc) in input.documents.enumerated() {
            let theta = Double(index) * goldenAngle
            let radius = docRadiusStep * Double(index).squareRoot()
            let position = SIMD3<Double>(
                radius * cos(theta),
                0,
                radius * sin(theta)
            )
            nodes.append(
                SpatialNode(
                    id: nodeId(forDocument: doc.id),
                    roomId: wholeLibraryRoomId,
                    nodeType: .source,
                    sourceId: doc.id,
                    label: doc.name,
                    positionX: position.x,
                    positionY: position.y,
                    positionZ: position.z
                )
            )
        }

        // Entity orbs raised above the docs so the layers read as distinct.
        let entityRadiusStep = max(0.6, 0.20 + 0.02 * Double(entityCount).squareRoot())
        let entityRiseStep = 0.04
        for (index, entity) in input.entities.enumerated() {
            let theta = Double(index) * goldenAngle
            let radius = entityRadiusStep * Double(index).squareRoot()
            let position = SIMD3<Double>(
                radius * cos(theta),
                1.2 + entityRiseStep * Double(index % 6),
                radius * sin(theta)
            )
            nodes.append(
                SpatialNode(
                    id: nodeId(forEntity: entity.id),
                    roomId: wholeLibraryRoomId,
                    nodeType: .entity,
                    sourceId: entity.id,
                    label: entity.canonicalName,
                    positionX: position.x,
                    positionY: position.y,
                    positionZ: position.z
                )
            )
        }

        // Links: parent→child between docs, claim→entity mentions, claim
        // co-occurrences (entity ↔ entity through a shared claim).
        let docIds = Set(input.documents.map(\.id))
        let entityIds = Set(input.entities.map(\.id))
        var links: Set<SpatialLink> = []

        for doc in input.documents {
            guard let parentId = doc.parentId, docIds.contains(parentId) else { continue }
            links.insert(
                SpatialLink(
                    sourceId: nodeId(forDocument: parentId),
                    targetId: nodeId(forDocument: doc.id),
                    linkType: .parentChild
                )
            )
        }

        for claim in input.claims {
            let claimType = LinkType.fallback(for: claim.predicateVerb ?? "")
            let presentEntityIds = claim.entityIds.filter { entityIds.contains($0) }

            // Entity ↔ document mentions.
            if let docId = claim.sourceDocumentId, docIds.contains(docId) {
                for entId in presentEntityIds {
                    links.insert(
                        SpatialLink(
                            sourceId: nodeId(forDocument: docId),
                            targetId: nodeId(forEntity: entId),
                            linkType: .mentions,
                            label: claim.predicateVerb
                        )
                    )
                }
            }

            // Entity-entity co-occurrence — use the predicate-derived type so
            // a "cites" claim between two entities lights up blue, "mentions"
            // stays teal, etc.
            if presentEntityIds.count >= 2 {
                for pairIndex in 1..<presentEntityIds.count {
                    let source = presentEntityIds[0]
                    let target = presentEntityIds[pairIndex]
                    guard source != target else { continue }
                    links.insert(
                        SpatialLink(
                            sourceId: nodeId(forEntity: source),
                            targetId: nodeId(forEntity: target),
                            linkType: claimType,
                            label: claim.predicateVerb
                        )
                    )
                }
            }
        }

        return SpatialLibraryProjection(
            nodes: nodes,
            links: Array(links).sorted { $0.id < $1.id }
        )
    }

    // MARK: - Schema adapters

    static func makeInput(
        documents: [Components.Schemas.Document],
        entities: [Components.Schemas.KnowledgeEntity],
        claims: [Components.Schemas.KnowledgeClaim]
    ) -> SpatialLibraryInput {
        SpatialLibraryInput(
            documents: documents.compactMap { doc in
                guard let id = doc.id else { return nil }
                return SpatialLibraryInput.Document(
                    id: id,
                    name: doc.name,
                    parentId: doc.parentId
                )
            },
            entities: entities.compactMap { entity in
                guard let id = entity.id else { return nil }
                return SpatialLibraryInput.Entity(
                    id: id,
                    canonicalName: entity.canonicalName,
                    entityType: entity.entityType?.rawValue
                )
            },
            claims: claims.compactMap { claim in
                guard let id = claim.id else { return nil }
                return SpatialLibraryInput.Claim(
                    id: id,
                    predicateVerb: claim.predicateVerb,
                    sourceDocumentId: claim.sourceDocumentId,
                    entityIds: claim.entityIds ?? []
                )
            }
        )
    }
}
