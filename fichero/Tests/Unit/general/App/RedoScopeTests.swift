@testable import Fichero
import Testing

/// #6744: "Run a Step Again" on several folders, a parent folder, or selected Items-pane items runs as ONE
/// run on the pages under them: the engine's `documents`, which takes pages, never folders.
@Suite("RecipeFolderScope.redoPages")
struct RedoScopeTests {
    private let documents = [
        Document(id: "top", parentId: nil, docType: .folder, name: "Top"),
        Document(id: "f1", parentId: "top", docType: .folder, name: "F1"),
        Document(id: "f2", parentId: "top", docType: .folder, name: "F2"),
        Document(id: "p1", parentId: "f1", name: "P1"),
        Document(id: "p2", parentId: "f2", name: "P2"),
        Document(id: "deep", parentId: "f3", name: "Deep"),
        Document(id: "f3", parentId: "f1", docType: .folder, name: "F3"),
        Document(id: "loose", parentId: "top", name: "Loose")
    ]

    @Test("several folders are the pages under them, once each")
    func severalFolders() {
        #expect(RecipeFolderScope.redoPages(selection: ["f1", "f2"], in: documents).sorted() == ["deep", "p1", "p2"])
    }

    @Test("a parent folder reaches every depth, and a page selected twice is listed once")
    func parentFolderRecursive() {
        #expect(RecipeFolderScope.redoPages(selection: ["top", "p1"], in: documents).sorted()
            == ["deep", "loose", "p1", "p2"])
    }

    @Test("selected items are themselves, and a folder with no pages is nothing")
    func selectedItems() {
        #expect(RecipeFolderScope.redoPages(selection: ["p2", "loose"], in: documents).sorted() == ["loose", "p2"])
        #expect(RecipeFolderScope.redoPages(selection: ["f3", "f2"], in: [documents[2], documents[4], documents[6]])
            == ["p2"])
        #expect(RecipeFolderScope.redoPages(selection: [], in: documents).isEmpty)
    }

    @Test("a two-item selection is both pages (#7087)")
    func twoItemSelection() {
        #expect(RecipeFolderScope.redoPages(selection: ["p1", "p2"], in: documents).sorted() == ["p1", "p2"])
    }

    @Test("a click inside the selection acts on the selection; outside it, on the clicked row alone")
    func clickedRowOrSelection() {
        #expect(RecipeFolderScope.runStepTargets(clicked: "p1", selection: ["p1", "p2"]) == ["p1", "p2"])
        #expect(RecipeFolderScope.runStepTargets(clicked: "loose", selection: ["p1", "p2"]) == ["loose"])
        #expect(RecipeFolderScope.runStepTargets(clicked: "f1", selection: []) == ["f1"])
    }

    @Test("pages the sidebar has not loaded still count: the pane's rows are joined in, each document once")
    func knownDocumentsJoinSurfaces() {
        let known = RecipeFolderScope.knownDocuments([documents[3]], [documents[3], documents[4]])
        #expect(known.map(\.id) == ["p1", "p2"])
    }

    @Test("the menu is named Run Step on every surface")
    func menuTitle() {
        #expect(RunStepAgainOnSelectionMenu.title == "Run Step")
    }
}
