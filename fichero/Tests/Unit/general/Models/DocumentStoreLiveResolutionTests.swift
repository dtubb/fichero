@testable import Fichero
import Foundation
import Testing

// #4318: the content pane showed stale page_content after a workflow wrote it,
// because every content-pane accessor resolved only through `currentDocuments`
// while the change-stream splice lands page children in `childrenCache` (or the
// `collections` fallback for unexpanded parents). These tests pin the
// full-container resolver and the revision/changed-ids signal the views key on.
@MainActor
@Suite("DocumentStore live-document resolution (#4318)")
struct DocumentStoreLiveResolutionTests {

    private func store() -> DocumentStore {
        DocumentStore(apiClient: APIClient())
    }

    private func doc(_ id: String, parent: String? = nil, name: String? = nil) -> Document {
        Document(id: id, parentId: parent, docType: .file, name: name ?? id)
    }

    // MARK: - Pure resolver

    @Test("resolves a page child that lives only in childrenCache")
    func resolvesFromChildrenCache() {
        let resolved = DocumentStore.resolveLiveDocument(
            id: "page-1",
            currentDocuments: [doc("other")],
            childrenCache: ["pdf-1": [doc("page-1", parent: "pdf-1", name: "fresh")]],
            collections: [],
            workspaces: []
        )
        #expect(resolved?.name == "fresh")
    }

    @Test("resolves through the collections fallback (unexpanded parent)")
    func resolvesFromCollections() {
        let resolved = DocumentStore.resolveLiveDocument(
            id: "page-1",
            currentDocuments: [],
            childrenCache: [:],
            collections: [doc("page-1", parent: "pdf-1", name: "fresh")],
            workspaces: []
        )
        #expect(resolved?.name == "fresh")
    }

    @Test("resolves a workspace document")
    func resolvesFromWorkspaces() {
        let resolved = DocumentStore.resolveLiveDocument(
            id: "ws-1",
            currentDocuments: [],
            childrenCache: [:],
            collections: [],
            workspaces: [doc("ws-1", name: "fresh")]
        )
        #expect(resolved?.name == "fresh")
    }

    @Test("prefers the grid copy when a row is in several containers")
    func prefersCurrentDocuments() {
        let resolved = DocumentStore.resolveLiveDocument(
            id: "doc-1",
            currentDocuments: [doc("doc-1", name: "grid")],
            childrenCache: ["p": [doc("doc-1", parent: "p", name: "cache")]],
            collections: [doc("doc-1", name: "roots")],
            workspaces: []
        )
        #expect(resolved?.name == "grid")
    }

    @Test("a miss returns nil — never a substitute document")
    func missReturnsNil() {
        let resolved = DocumentStore.resolveLiveDocument(
            id: "absent",
            currentDocuments: [doc("a")],
            childrenCache: ["p": [doc("b", parent: "p")]],
            collections: [doc("c")],
            workspaces: [doc("d")]
        )
        #expect(resolved == nil)
    }

    // MARK: - Store signal: a childrenCache-only splice must be observable

    @Test("a splice landing only in childrenCache bumps revision and records the ids")
    func childrenCacheSpliceBumpsRevision() {
        let store = store()
        store.collections = [doc("pdf-1", name: "PDF")]
        store.childrenCache["pdf-1"] = [doc("page-1", parent: "pdf-1", name: "stale")]

        let before = store.revision
        store.spliceDocuments([doc("page-1", parent: "pdf-1", name: "fresh")])

        #expect(store.revision > before, "childrenCache is @ObservationIgnored — the token is the only re-render signal")
        #expect(store.lastChangedDocumentIds == ["page-1"])
        #expect(store.liveDocument(id: "page-1")?.name == "fresh")
    }

    @Test("a no-op splice does not bump revision or clobber the changed ids")
    func noOpSpliceLeavesSignalAlone() {
        let store = store()
        let page = doc("page-1", parent: "pdf-1", name: "same")
        store.childrenCache["pdf-1"] = [page]
        store.spliceDocuments([doc("page-2", parent: "pdf-1", name: "first")])
        let before = store.revision
        let idsBefore = store.lastChangedDocumentIds

        store.spliceDocuments([page])

        #expect(store.revision == before)
        #expect(store.lastChangedDocumentIds == idsBefore)
    }

    @Test("liveDocument reads through the store's containers")
    func liveDocumentReadsAllContainers() {
        let store = store()
        store.currentDocuments = [doc("grid-1")]
        store.childrenCache["pdf-1"] = [doc("page-1", parent: "pdf-1")]
        store.workspaces = [doc("ws-1")]

        #expect(store.liveDocument(id: "grid-1") != nil)
        #expect(store.liveDocument(id: "page-1") != nil)
        #expect(store.liveDocument(id: "ws-1") != nil)
        #expect(store.liveDocument(id: "absent") == nil)
    }

    // MARK: - Shell snapshot refresh still favors the fresh row

    @Test("refreshedFocusedDocument swaps in the fresh row and keeps focus on a miss")
    func refreshedFocusedDocumentBehaviour() {
        let current = doc("page-1", name: "stale")
        let fresh = doc("page-1", name: "fresh")

        #expect(ContentView.refreshedFocusedDocument(current, in: [fresh])?.name == "fresh")
        #expect(ContentView.refreshedFocusedDocument(current, in: [doc("other")])?.name == "stale")
        #expect(ContentView.refreshedFocusedDocument(nil, in: [fresh]) == nil)
    }
}
