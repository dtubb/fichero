@testable import Fichero
import Foundation
import Testing

// `collections` is ROOTS ONLY — `loadCollections()` assigns `getRoots()`. The
// change-stream splice appended every incoming document to it unguarded, so an
// import of N files put all N into a roots list (#4203).
//
// The trap: that same append was ALSO how imported children reached the sidebar,
// since `SidebarItemBuilder` files anything with a parentId under its parent. So
// the obvious fix — guard on `parentId == nil` and stop — drops the pollution by
// breaking the live delivery Daniel asked for, and gates green, because nothing
// asserted delivery. These tests assert BOTH halves so that can't happen again.
@MainActor
@Suite("DocumentStore.spliceDocument — roots stay roots, children still arrive (#4203)")
struct DocumentStoreSpliceTests {

    private func store() -> DocumentStore {
        DocumentStore(apiClient: APIClient())
    }

    private func doc(_ id: String, parent: String? = nil, name: String? = nil) -> Document {
        Document(id: id, parentId: parent, docType: .file, name: name ?? id)
    }

    @Test("a new root document joins collections")
    func rootIsAppended() {
        let store = store()
        store.spliceDocument(doc("root-1"))
        #expect(store.collections.map(\.id) == ["root-1"])
    }

    // The bug: N imported files landing in a roots-only list.
    @Test("an imported child does NOT pollute the roots list")
    func nestedDocumentStaysOutOfCollections() {
        let store = store()
        store.collections = [doc("folder", name: "Folder")]

        for index in 0..<50 {
            store.spliceDocument(doc("file-\(index)", parent: "folder"))
        }

        #expect(store.collections.map(\.id) == ["folder"], "50 imported files must not become roots")
    }

    // The half that a naive fix breaks: an OPEN folder must still fill live.
    @Test("a child of a loaded parent reaches the children cache")
    func childOfLoadedParentIsDelivered() {
        let store = store()
        store.collections = [doc("folder", name: "Folder")]
        store.childrenCache["folder"] = []          // the user has this folder open

        store.spliceDocument(doc("file-1", parent: "folder"))

        #expect(store.childrenCache["folder"]?.map(\.id) == ["file-1"], "delivery must survive")
        #expect(store.collections.map(\.id) == ["folder"], "and must not also pollute roots")
    }

    @Test("a child of a closed folder is not cached — expansion fetches it")
    func childOfUnloadedParentIsSkipped() {
        let store = store()
        store.collections = [doc("folder", name: "Folder")]

        store.spliceDocument(doc("file-1", parent: "folder"))

        #expect(store.childrenCache["folder"] == nil)
        #expect(store.collections.map(\.id) == ["folder"])
    }

    @Test("an existing row is patched in place, not duplicated")
    func existingRowIsPatched() {
        let store = store()
        store.collections = [doc("root-1", name: "Before")]

        store.spliceDocument(doc("root-1", name: "After"))

        #expect(store.collections.count == 1)
        #expect(store.collections.first?.name == "After")
    }

    // A row already in the cache updates in place; a rename during import must
    // not append a second copy under the same parent.
    @Test("an existing child is patched in the cache, not appended twice")
    func existingChildIsPatched() {
        let store = store()
        store.childrenCache["folder"] = [doc("file-1", parent: "folder", name: "Before")]

        store.spliceDocument(doc("file-1", parent: "folder", name: "After"))

        #expect(store.childrenCache["folder"]?.count == 1)
        #expect(store.childrenCache["folder"]?.first?.name == "After")
    }

    @Test("a child of the selected collection still reaches the grid")
    func childOfSelectionReachesGrid() {
        let store = store()
        let folder = Document(id: "folder", docType: .folder, name: "Folder")
        store.collections = [folder]
        store.selectedCollection = folder

        store.spliceDocument(doc("file-1", parent: "folder"))

        #expect(store.currentDocuments.map(\.id) == ["file-1"])
    }
}
