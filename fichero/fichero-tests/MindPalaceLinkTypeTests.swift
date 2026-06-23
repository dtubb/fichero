@testable import Fichero
import Foundation
import Testing

// MARK: - LinkType decoding (Phase 3 / #1297 follow-up)

struct LinkTypeTests {

    /// Each canonical raw value round-trips.
    @Test("canonical raw values round-trip")
    func canonicalRawValues() throws {
        let cases: [(String, LinkType)] = [
            ("citation", .citation),
            ("mentions", .mentions),
            ("depicts", .depicts),
            ("related", .related),
            ("contradicts", .contradicts),
            ("supersedes", .supersedes),
            ("parent_child", .parentChild),
            ("user_drawn", .userDrawn),
            ("unknown", .unknown)
        ]
        for (raw, expected) in cases {
            let json = "\"\(raw)\""
            let decoded = try JSONDecoder().decode(LinkType.self, from: Data(json.utf8))
            #expect(decoded == expected, "raw '\(raw)' should decode to \(expected)")
        }
    }

    /// Synonyms map to the right canonical case.
    @Test("synonym mapping")
    func synonyms() {
        #expect(LinkType.fallback(for: "cites") == .citation)
        #expect(LinkType.fallback(for: "CITED_BY") == .citation)
        #expect(LinkType.fallback(for: "mentioned_in") == .mentions)
        #expect(LinkType.fallback(for: "refutes") == .contradicts)
        #expect(LinkType.fallback(for: "replaces") == .supersedes)
        #expect(LinkType.fallback(for: "contains") == .parentChild)
    }

    /// Anything unknown falls back to `.related` — the renderer's safe default.
    /// This is the load-bearing guarantee that a new backend predicate won't
    /// drop the scene.
    @Test("unknown raw falls back to .related")
    func unknownFallback() throws {
        let json = "\"some_brand_new_predicate\""
        let decoded = try JSONDecoder().decode(LinkType.self, from: Data(json.utf8))
        #expect(decoded == .related)
    }

    /// `SpatialConnection.linkType` derives from `linkSubtype` when set,
    /// otherwise from `connectionType`. Lets the renderer paint a room edge
    /// and a content-level link with the same palette.
    @Test("SpatialConnection.linkType derivation")
    func connectionLinkType() throws {
        // linkSubtype overrides connectionType.
        let withSubtype = try decodeConnection(
            connectionType: "semantic",
            linkSubtype: "cites"
        )
        #expect(withSubtype.linkType == .citation)

        // No subtype → ConnectionType mapping.
        let evidentiary = try decodeConnection(
            connectionType: "evidentiary",
            linkSubtype: nil
        )
        #expect(evidentiary.linkType == .citation)

        let hermeneutic = try decodeConnection(
            connectionType: "hermeneutic",
            linkSubtype: nil
        )
        #expect(hermeneutic.linkType == .mentions)
    }

    private func decodeConnection(connectionType: String, linkSubtype: String?) throws -> SpatialConnection {
        let subtypeJSON = linkSubtype.map { "\"\($0)\"" } ?? "null"
        let json = """
        {
          "id": "c1",
          "roomId": "r1",
          "sourceNodeId": "n1",
          "targetNodeId": "n2",
          "connectionType": "\(connectionType)",
          "linkSubtype": \(subtypeJSON)
        }
        """
        return try JSONDecoder().decode(SpatialConnection.self, from: Data(json.utf8))
    }
}

// MARK: - Library projector (Phase 3 / #1297 follow-up)

struct SpatialLibraryProjectorTests {

    /// Document count + entity count map directly onto node count.
    @Test("node count = docs + entities")
    func nodeCount() {
        let input = SpatialLibraryInput(
            documents: [
                .init(id: "d1", name: "Doc 1", parentId: nil),
                .init(id: "d2", name: "Doc 2", parentId: "d1")
            ],
            entities: [
                .init(id: "e1", canonicalName: "Alice", entityType: "person"),
                .init(id: "e2", canonicalName: "Bob", entityType: "person"),
                .init(id: "e3", canonicalName: "Carol", entityType: "person")
            ],
            claims: []
        )
        let projection = SpatialLibraryProjector.project(input)
        #expect(projection.nodes.count == 5)
        #expect(projection.nodes.filter { $0.nodeType == .source }.count == 2)
        #expect(projection.nodes.filter { $0.nodeType == .entity }.count == 3)
    }

    /// Stable spatial-node IDs — re-projecting the same input gives the same
    /// IDs and positions. This is what lets the renderer redraw without
    /// shuffling the layout.
    @Test("projection is deterministic")
    func deterministic() {
        let input = sampleInput()
        let first = SpatialLibraryProjector.project(input)
        let second = SpatialLibraryProjector.project(input)
        #expect(first.nodes.map(\.id) == second.nodes.map(\.id))
        #expect(first.nodes.map(\.positionX) == second.nodes.map(\.positionX))
        #expect(first.nodes.map(\.positionZ) == second.nodes.map(\.positionZ))
        #expect(first.links.map(\.id) == second.links.map(\.id))
    }

    /// parent_id between two known docs becomes a `.parentChild` link.
    @Test("parent_child link emitted for known parent")
    func parentChildLinks() {
        let input = SpatialLibraryInput(
            documents: [
                .init(id: "parent", name: "Parent", parentId: nil),
                .init(id: "child", name: "Child", parentId: "parent"),
                // Dangling parent_id → not linked (parent not in scope).
                .init(id: "orphan", name: "Orphan", parentId: "missing")
            ],
            entities: [],
            claims: []
        )
        let projection = SpatialLibraryProjector.project(input)
        let parentChildren = projection.links.filter { $0.linkType == .parentChild }
        #expect(parentChildren.count == 1)
        #expect(parentChildren.first?.sourceId == SpatialLibraryProjector.nodeId(forDocument: "parent"))
        #expect(parentChildren.first?.targetId == SpatialLibraryProjector.nodeId(forDocument: "child"))
    }

    /// A claim with `entity_ids` and a `sourceDocumentId` mints both
    /// doc→entity `.mentions` links and entity↔entity links typed by the
    /// claim's predicate.
    @Test("claim links — mentions + entity↔entity")
    func claimLinks() {
        let input = SpatialLibraryInput(
            documents: [.init(id: "d1", name: "Doc", parentId: nil)],
            entities: [
                .init(id: "e1", canonicalName: "X", entityType: nil),
                .init(id: "e2", canonicalName: "Y", entityType: nil)
            ],
            claims: [
                .init(
                    id: "c1",
                    predicateVerb: "cites",
                    sourceDocumentId: "d1",
                    entityIds: ["e1", "e2"]
                )
            ]
        )
        let projection = SpatialLibraryProjector.project(input)
        let mentions = projection.links.filter { $0.linkType == .mentions }
        #expect(mentions.count == 2)  // d1 ↔ e1, d1 ↔ e2

        let citations = projection.links.filter { $0.linkType == .citation }
        #expect(citations.count == 1)  // e1 ↔ e2 (claim predicate "cites" → citation)
    }

    /// Entity IDs absent from the input scope are quietly dropped (don't emit
    /// dangling links). One malformed claim can't drop the whole scene.
    @Test("links to unknown entities are dropped")
    func dropUnknownTargets() {
        let input = SpatialLibraryInput(
            documents: [.init(id: "d1", name: "Doc", parentId: nil)],
            entities: [.init(id: "e1", canonicalName: "X", entityType: nil)],
            claims: [
                .init(
                    id: "c1",
                    predicateVerb: "mentions",
                    sourceDocumentId: "d1",
                    entityIds: ["e1", "e_missing"]
                )
            ]
        )
        let projection = SpatialLibraryProjector.project(input)
        // Only e1 is in scope → one mention link, no entity↔entity link.
        #expect(projection.links.allSatisfy { link in
            // Every endpoint must resolve to a node we actually rendered.
            let nodeIds = Set(projection.nodes.map(\.id))
            return nodeIds.contains(link.sourceId) && nodeIds.contains(link.targetId)
        })
    }

    private func sampleInput() -> SpatialLibraryInput {
        SpatialLibraryInput(
            documents: [
                .init(id: "d1", name: "First", parentId: nil),
                .init(id: "d2", name: "Second", parentId: "d1")
            ],
            entities: [
                .init(id: "e1", canonicalName: "Alice", entityType: "person"),
                .init(id: "e2", canonicalName: "Bob", entityType: "person")
            ],
            claims: [
                .init(id: "c1", predicateVerb: "mentions", sourceDocumentId: "d1", entityIds: ["e1"]),
                .init(id: "c2", predicateVerb: "cites", sourceDocumentId: "d2", entityIds: ["e1", "e2"])
            ]
        )
    }
}
