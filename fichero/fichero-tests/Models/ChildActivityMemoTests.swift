@testable import Fichero
import FicheroAPIClient
import Testing

// The childActivityCounts memo (2026-08-09 stall fix): cached per
// (revision, overrides-token), so it must still change its answer the moment
// either input changes — a stale memo here is a spinner that never stops.
@MainActor
@Suite("childActivityCounts — memoized but never stale")
struct ChildActivityMemoTests {
    private func makeStore() -> DocumentStore {
        DocumentStore(apiClient: APIClient(client: FicheroClient(libraryPath: nil)))
    }

    @Test("counts follow document mutations across the memo")
    func countsFollowRevision() {
        let store = makeStore()
        store.currentDocuments = [
            Document(id: "c1", parentId: "p", name: "one", status: .processing),
            Document(id: "c2", parentId: "p", name: "two", status: .completed)
        ]
        #expect(store.childActivityCounts(of: "p") == (busy: 1, total: 2))
        // Memo hit — same answer.
        #expect(store.childActivityCounts(of: "p") == (busy: 1, total: 2))

        // Document mutation bumps revision → memo must refresh.
        store.currentDocuments = [
            Document(id: "c1", parentId: "p", name: "one", status: .completed),
            Document(id: "c2", parentId: "p", name: "two", status: .completed)
        ]
        #expect(store.childActivityCounts(of: "p") == (busy: 0, total: 2))
    }

    @Test("an override write invalidates the memo without a document change")
    func overridesInvalidate() {
        let store = makeStore()
        store.currentDocuments = [
            Document(id: "c1", parentId: "p", name: "one", status: .completed)
        ]
        #expect(store.childActivityCounts(of: "p") == (busy: 0, total: 1))
        store.workflowStatusOverrides["c1"] = .processing
        #expect(store.childActivityCounts(of: "p") == (busy: 1, total: 1))
        store.workflowStatusOverrides.removeValue(forKey: "c1")
        #expect(store.childActivityCounts(of: "p") == (busy: 0, total: 1))
    }
}
