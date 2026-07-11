@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

// Tests for LibraryOutlineModel page/artifact child rows (#2405).
// Covers: pages ordered by sequence, artifact fallback group, artifacts
// when loaded, nil when rollup missing, and stable page-item IDs.

@Suite("LibraryOutlineModel — page and artifact child rows (#2405)")
struct LibraryOutlineModelTests {

    // MARK: - Helpers

    @MainActor private func makeModel() -> LibraryOutlineModel {
        let client = FicheroClient(libraryPath: "/tmp/test-outline.fichero")
        return LibraryOutlineModel(
            service: EntityServiceGenerated(ficheroClient: client),
            artifactService: ArtifactServiceGenerated(ficheroClient: client)
        )
    }

    private func makeDoc(id: String) -> Document {
        Document(id: id, name: id)
    }

    private func makePage(id: String, parentId: String, sequence: Int) -> Document {
        Document(id: id, parentId: parentId, docType: .page, name: "Page \(sequence)",
                 sequence: sequence)
    }

    private func makeArtifact(id: String, documentId: String) -> Artifact {
        Artifact(id: id, documentId: documentId, sourceArtifactId: nil,
                 version: 1, artifactType: "transcript", content: nil,
                 data: nil, runId: nil, provider: nil, model: nil,
                 stepName: "transcript", confidence: nil,
                 reviewed: false, createdAt: Date())
    }

    /// Build a rollup via JSON so we're robust to generated-type field ordering.
    private func makeRollup(
        pages: Int = 0,
        artifacts: Int = 0,
        entities: Int = 0,
        claims: Int = 0
    ) throws -> Components.Schemas.DocumentRollupResponse {
        let json = """
        {"document_id":"any","pages":\(pages),"artifacts":\(artifacts),"entities":\(entities),"notes":0,"claims":\(claims)}
        """
        return try JSONDecoder().decode(
            Components.Schemas.DocumentRollupResponse.self,
            from: Data(json.utf8)
        )
    }

    private func makeEntity(id: String, name: String) -> Components.Schemas.KnowledgeEntity {
        Components.Schemas.KnowledgeEntity(
            id: id,
            canonicalName: name,
            entityType: .person,
            aliases: nil,
            description: nil,
            language: nil,
            metadata: nil,
            mergedIntoId: nil
        )
    }

    private func makeClaim(id: String, text: String) -> Components.Schemas.KnowledgeClaim {
        Components.Schemas.KnowledgeClaim(
            id: id,
            text: text,
            subjectCanonical: nil,
            predicateVerb: nil,
            objectPhrase: nil
        )
    }

    // MARK: - Tests

    @Test("childNodes returns nil when rollup not yet loaded")
    @MainActor func returnsNilWhenRollupMissing() {
        let model = makeModel()
        #expect(model.childNodes(for: makeDoc(id: "doc-a")) == nil)
    }

    @Test("Empty rollup produces empty children array")
    @MainActor func emptyRollupGivesEmptyChildren() throws {
        let model = makeModel()
        let doc = makeDoc(id: "doc-b")
        model.rollups["doc-b"] = try makeRollup()
        let children = model.childNodes(for: doc)
        #expect(children != nil)
        #expect(children?.isEmpty == true)
    }

    @Test("Page items appear ordered by sequence even when fed out of order")
    @MainActor func pageItemsOrderedBySequence() throws {
        let model = makeModel()
        let doc = makeDoc(id: "pdf-1")
        model.rollups["pdf-1"] = try makeRollup(pages: 3)
        model.pagesByParentId["pdf-1"] = [
            makePage(id: "p3", parentId: "pdf-1", sequence: 3),
            makePage(id: "p1", parentId: "pdf-1", sequence: 1),
            makePage(id: "p2", parentId: "pdf-1", sequence: 2)
        ]

        let children = model.childNodes(for: doc) ?? []
        let sequences = children.compactMap { node -> Int? in
            guard case .pageItem(let page) = node.kind else { return nil }
            return page.sequence
        }
        #expect(sequences == [1, 2, 3])
    }

    @Test("Page item count matches loaded pages")
    @MainActor func pageItemCountMatchesLoaded() throws {
        let model = makeModel()
        let doc = makeDoc(id: "pdf-2")
        model.rollups["pdf-2"] = try makeRollup(pages: 2)
        model.pagesByParentId["pdf-2"] = [
            makePage(id: "pa", parentId: "pdf-2", sequence: 1),
            makePage(id: "pb", parentId: "pdf-2", sequence: 2)
        ]

        let pageItems = model.childNodes(for: doc)?.filter {
            if case .pageItem = $0.kind { return true }; return false
        }
        #expect(pageItems?.count == 2)
    }

    @Test("Artifact fallback count-group shown when artifacts not yet loaded")
    @MainActor func artifactFallbackGroupWhenNotLoaded() throws {
        let model = makeModel()
        let doc = makeDoc(id: "doc-c")
        model.rollups["doc-c"] = try makeRollup(artifacts: 3)

        let groups = model.childNodes(for: doc)?.filter {
            if case .childGroup(.artifacts) = $0.kind { return true }; return false
        } ?? []
        #expect(groups.count == 1)
        #expect(groups.first?.count == 3)
    }

    @Test("Artifact items replace fallback group once loaded")
    @MainActor func artifactItemsReplaceGroupWhenLoaded() throws {
        let model = makeModel()
        let doc = makeDoc(id: "doc-d")
        model.rollups["doc-d"] = try makeRollup(artifacts: 2)
        model.artifactsByDocumentId["doc-d"] = [
            makeArtifact(id: "art-1", documentId: "doc-d"),
            makeArtifact(id: "art-2", documentId: "doc-d")
        ]

        let children = model.childNodes(for: doc) ?? []
        let artItems = children.filter { if case .artifactItem = $0.kind { return true }; return false }
        let groups = children.filter { if case .childGroup(.artifacts) = $0.kind { return true }; return false }
        #expect(artItems.count == 2)
        #expect(groups.isEmpty)
    }

    @Test("Page item node ID encodes parent + page ids")
    func pageItemNodeIdIsStable() {
        let parent = makeDoc(id: "parent-1")
        let page = makePage(id: "page-x", parentId: "parent-1", sequence: 1)
        let node = LibraryOutlineNode.pageItem(page, parent: parent)
        #expect(node.id == "parent-1:page:page-x")
    }

    @Test("Artifact item node ID encodes parent + artifact ids")
    func artifactItemNodeIdIsStable() {
        let parent = makeDoc(id: "parent-2")
        let art = makeArtifact(id: "art-z", documentId: "parent-2")
        let node = LibraryOutlineNode.artifactItem(art, parent: parent)
        #expect(node.id == "parent-2:artifact:art-z")
    }

    @Test("Entity and claim groups expose loaded children instead of leaf count rows")
    @MainActor func entityAndClaimGroupsExposeChildren() throws {
        let model = makeModel()
        let doc = makeDoc(id: "doc-e")
        model.rollups["doc-e"] = try makeRollup(entities: 2, claims: 1)
        model.entitiesByDocumentId["doc-e"] = [
            makeEntity(id: "entity-1", name: "Ada"),
            makeEntity(id: "entity-2", name: "Grace")
        ]
        model.claimsByDocumentId["doc-e"] = [
            makeClaim(id: "claim-1", text: "Ada cites Grace")
        ]

        let children = model.childNodes(for: doc) ?? []
        let entityGroup = children.first {
            if case .childGroup(.entities) = $0.kind { return true }
            return false
        }
        let claimGroup = children.first {
            if case .childGroup(.claims) = $0.kind { return true }
            return false
        }

        #expect(entityGroup?.count == 2)
        #expect(entityGroup?.children?.count == 2)
        #expect(claimGroup?.count == 1)
        #expect(claimGroup?.children?.count == 1)
    }

    @Test("Entity and claim child node IDs are stable")
    func entityAndClaimNodeIdsAreStable() {
        let parent = makeDoc(id: "parent-3")
        let entityNode = LibraryOutlineNode.entityItem(makeEntity(id: "entity-x", name: "Ada"), parent: parent)
        let claimNode = LibraryOutlineNode.claimItem(makeClaim(id: "claim-y", text: "Ada cites Grace"), parent: parent)

        #expect(entityNode.id == "parent-3:entity:entity-x")
        #expect(claimNode.id == "parent-3:claim:claim-y")
    }

    @Test("Entity and claim aggregate rows disclose only when children are loaded")
    func aggregateRowsOnlyExpandWithRealChildren() {
        let parent = makeDoc(id: "parent-4")
        let unloadedGroup = LibraryOutlineNode.childGroup(.entities, document: parent, count: 2)
        let emptyGroup = LibraryOutlineNode.childGroup(.claims, document: parent, count: 1, children: [])
        let loadedGroup = LibraryOutlineNode.childGroup(
            .entities,
            document: parent,
            count: 2,
            children: [
                LibraryOutlineNode.entityItem(makeEntity(id: "entity-a", name: "Ada"), parent: parent)
            ]
        )

        #expect(unloadedGroup.canExpand == false)
        #expect(emptyGroup.canExpand == false)
        #expect(loadedGroup.canExpand)
    }
}
