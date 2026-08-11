@testable import Fichero
import FicheroAPIClient
import Testing

// The sidebarDocuments memo (2026-08-09 stall log, 1747ms context-menu
// resolve): cached per (revision, cache shape), so it must still change its
// answer the moment membership actually changes — a stale memo here is a
// workflow run aimed at documents the user can no longer see.
@MainActor
@Suite("sidebarDocuments — memoized but never stale")
struct SidebarDocumentsMemoTests {
    private func makeStore() -> DocumentStore {
        DocumentStore(apiClient: APIClient(client: FicheroClient(libraryPath: nil)))
    }

    @Test("roots + cached children, deduplicated, and a memo hit repeats it")
    func unionAndMemoHit() {
        let store = makeStore()
        store.collections = [Document(id: "root", name: "Root")]
        store.childrenCache["root"] = [
            Document(id: "kid", parentId: "root", name: "Kid"),
            Document(id: "root", name: "Root")  // duplicate id across containers
        ]
        let first = store.sidebarDocuments
        #expect(Set(first.map(\.id)) == ["root", "kid"])
        #expect(first.count == 2)
        #expect(store.sidebarDocuments.map(\.id) == first.map(\.id))  // memo hit
    }

    @Test("a new cached child invalidates the memo without a revision bump")
    func cacheGrowthInvalidates() {
        let store = makeStore()
        store.collections = [Document(id: "root", name: "Root")]
        _ = store.sidebarDocuments  // prime
        store.childrenCache["root"] = [Document(id: "kid", parentId: "root", name: "Kid")]
        #expect(Set(store.sidebarDocuments.map(\.id)) == ["root", "kid"])
    }

    @Test("a revision bump refreshes membership even at identical counts")
    func revisionBumpInvalidates() {
        let store = makeStore()
        store.childrenCache["root"] = [Document(id: "a", parentId: "root", name: "A")]
        _ = store.sidebarDocuments  // prime
        // Same shape (1 parent, 1 child, 0 roots) but different member —
        // splices bump revision for exactly this case.
        store.childrenCache["root"] = [Document(id: "b", parentId: "root", name: "B")]
        store.revision += 1
        #expect(store.sidebarDocuments.map(\.id) == ["b"])
    }
}
