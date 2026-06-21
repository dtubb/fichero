@testable import Fichero
import Testing

// Tests for LibraryOutlineModel page/artifact child rows (#2405).
// Covers: pages ordered by sequence, artifact fallback group, artifacts
// when loaded, nil when rollup missing, and stable page-item IDs.

@Suite("LibraryOutlineModel — page and artifact child rows (#2405)")
struct LibraryOutlineModelTests {

    // MARK: - Helpers

    private func makeModel() -> LibraryOutlineModel {
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
        Document(id: id, parentId: parentId, name: "Page \(sequence)",
                 docType: .page, sequence: sequence)
    }

    private func makeArtifact(id: String, documentId: String) -> Artifact {
        Artifact(id: id, documentId: documentId, sourceArtifactId: nil,
                 version: 1, artifactType: "transcript", content: nil,
                 data: nil, runId: nil, provider: nil, model: nil,
                 stepName: "transcript", confidence: nil,
                 reviewed: false, createdAt: Date())
    }

    /// Build a rollup via JSON so we're robust to generated-type field ordering.
    private func makeRollup(pages: Int = 0, artifacts: Int = 0) throws -> Components.Schemas.DocumentRollupResponse {
        let json = """
        {"document_id":"any","pages":\(pages),"artifacts":\(artifacts),"entities":0,"notes":0,"claims":0}
        """
        return try JSONDecoder().decode(
            Components.Schemas.DocumentRollupResponse.self,
            from: Data(json.utf8)
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
            makePage(id: "p2", parentId: "pdf-1", sequence: 2),
        ]

        let children = model.childNodes(for: doc) ?? []
        let seqs = children.compactMap { n -> Int? in
            guard case .pageItem(let p) = n.kind else { return nil }
            return p.sequence
        }
        #expect(seqs == [1, 2, 3])
    }

    @Test("Page item count matches loaded pages")
    @MainActor func pageItemCountMatchesLoaded() throws {
        let model = makeModel()
        let doc = makeDoc(id: "pdf-2")
        model.rollups["pdf-2"] = try makeRollup(pages: 2)
        model.pagesByParentId["pdf-2"] = [
            makePage(id: "pa", parentId: "pdf-2", sequence: 1),
            makePage(id: "pb", parentId: "pdf-2", sequence: 2),
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
            makeArtifact(id: "art-2", documentId: "doc-d"),
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
}
