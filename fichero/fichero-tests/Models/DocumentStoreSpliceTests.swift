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
// breaking the live delivery the requirement was, and gates green, because nothing
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

    // The bug this file was written for: N imported files landing in a
    // roots-only list. It only holds when the parent's children are LOADED —
    // see `childOfUnloadedParentIsDeliveredViaCollections` for why the
    // unloaded case deliberately does the opposite.
    @Test("imported children of a LOADED parent do not pollute the roots list")
    func nestedDocumentStaysOutOfCollections() {
        let store = store()
        store.collections = [doc("folder", name: "Folder")]
        store.childrenCache["folder"] = []          // the user has this folder open

        for index in 0..<50 {
            store.spliceDocument(doc("file-\(index)", parent: "folder"))
        }

        #expect(store.collections.map(\.id) == ["folder"], "50 imported files must not become roots")
        #expect(store.childrenCache["folder"]?.count == 50, "they belong to the open folder")
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

    // THIS TEST PREVIOUSLY ASSERTED THE OPPOSITE, AND THE ASSERTION WAS WRONG.
    // It pinned "a child of a closed folder is skipped", which is what the first
    // version of the roots guard did — and that silently broke live delivery
    // into folders the user had not expanded: importing into a collapsed folder
    // showed nothing at all (fixed in 200e56400).
    //
    // The passing test defended the bug. Nothing catches that shape: it passes,
    // it fails when mutated, and it reads as evidence. The only defence is
    // asking whether what a test forbids is genuinely undesirable.
    //
    // `SidebarItemBuilder` files anything carrying a parentId under its parent,
    // so with the children cache empty `collections` is the ONLY container that
    // makes the row visible. The cost — `collections` transiently holding
    // non-roots until the next `loadCollections()` — is the lesser evil: the
    // pollution is invisible, a missing row is not.
    @Test("a child of a CLOSED folder still reaches the sidebar, via collections")
    func childOfUnloadedParentIsDeliveredViaCollections() {
        let store = store()
        store.collections = [doc("folder", name: "Folder")]

        store.spliceDocument(doc("file-1", parent: "folder"))

        #expect(store.childrenCache["folder"] == nil, "the closed folder is still unfetched")
        #expect(
            store.collections.map(\.id) == ["folder", "file-1"],
            "the row must be visible somewhere — collections is the only container left"
        )
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

    // #4235 batching: a change-stream flush that delivers nothing new must not
    // publish at all — the whole point of the changed-flags is that a no-op
    // poll cannot invalidate the sidebar. `withObservationTracking`'s onChange
    // fires synchronously on the first willSet, so `fired` staying false IS
    // the assertion that no container was reassigned.
    @Test("re-splicing identical documents publishes nothing")
    func noOpBatchDoesNotPublish() {
        let store = store()
        let root = doc("root-1")
        let child = doc("file-1", parent: "root-1")
        store.spliceDocuments([root])
        store.childrenCache["root-1"] = [child]

        var fired = false
        withObservationTracking {
            _ = store.collections
            _ = store.currentDocuments
            _ = store.childrenCache
        } onChange: {
            fired = true
        }
        store.spliceDocuments([root, child])

        #expect(!fired, "an identical batch reassigned a published container — no-op polls now rebuild the sidebar")
    }
}
