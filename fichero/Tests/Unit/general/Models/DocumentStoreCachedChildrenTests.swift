@testable import Fichero
import Foundation
import Testing

/// #5276: clicking a folder showed its rows only after the engine answered, even when the store
/// already held them in `childrenCache` (a folder visited a moment ago, or one the sidebar
/// prefetched). The cached rows now draw at once and the fetch refreshes them in place.
@MainActor
@Suite("A folder's cached children show before the fetch (#5276)")
struct DocumentStoreCachedChildrenTests {

    @Test("cached rows are shown, and a failed refresh does not blank them")
    func cachedRowsSurviveAFailedFetch() async {
        // No engine answers under test, so the refresh fails: exactly the case where the old code
        // left the table empty.
        let store = DocumentStore(apiClient: APIClient())
        let folder = Document(id: "folder", docType: .folder, name: "hebrew-rtl")
        let rows = [Document(id: "p1", parentId: "folder", name: "p1"),
                    Document(id: "p2", parentId: "folder", name: "p2")]
        store.childrenCache["folder"] = rows

        await store.loadChildren(of: folder)

        #expect(store.currentDocuments.map(\.id) == ["p1", "p2"])
    }

    @Test("an unknown folder still waits for the engine")
    func uncachedFolderShowsNothingOnFailure() async {
        let store = DocumentStore(apiClient: APIClient())
        await store.loadChildren(of: Document(id: "unknown", docType: .folder, name: "x"))
        #expect(store.currentDocuments.isEmpty)
    }
}
