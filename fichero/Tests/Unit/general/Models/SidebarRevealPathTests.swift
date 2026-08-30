@testable import Fichero
import Testing

// The sidebar reveal's ancestor walk (2026-08-23): root-first, cache-served,
// and — the part with a scar — CYCLE-PROOF. An ancestors loop once ran the
// engine suite to 50GB; bad parent data must degrade to a short path, never
// a hang or a runaway.
@MainActor
struct SidebarRevealPathTests {
    private func store() -> DocumentStore { DocumentStore(apiClient: APIClient()) }

    private func doc(_ id: String, parent: String? = nil) -> Document {
        Document(id: id, parentId: parent, docType: .folder, name: id)
    }

    @Test("ancestors come back root-first, excluding the target")
    func rootFirst() async {
        let store = store()
        store.currentDocuments = [
            doc("root"), doc("mid", parent: "root"), doc("leaf", parent: "mid")
        ]
        let path = await store.sidebarRevealPath(to: "leaf")
        #expect(path?.map(\.id) == ["root", "mid"])
    }

    @Test("a parent cycle terminates with the partial chain")
    func cycleGuard() async {
        let store = store()
        // a → b → a: malformed, must not loop.
        store.currentDocuments = [doc("a", parent: "b"), doc("b", parent: "a")]
        let path = await store.sidebarRevealPath(to: "a")
        #expect(path?.map(\.id) == ["b"])
    }

    @Test("a root-level document reveals with an empty chain, not nil")
    func rootLevel() async {
        let store = store()
        store.currentDocuments = [doc("solo")]
        let path = await store.sidebarRevealPath(to: "solo")
        #expect(path?.isEmpty == true)
    }
}
