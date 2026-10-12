import Foundation
@testable import Fichero
import Testing

/// #5652 slice 2: the Read menu became Page with the Segment menu folded in, and Project › Read › Reading ▸ holds
/// Run the Recipe on This Folder…. The menus themselves cannot be mounted in a unit target; what they say and act on
/// can. What breaks without these: a Page › Segments item that greys out with no word, or a Reading ▸ item (or a
/// folder's context menu) that runs the recipe on the wrong folder. The bar's shape (no Read, no Segment menu; Page's
/// items) is `MenuTerminologyBoundaryTests.testPageMenuReplacesReadAndSegment`; the moved chords are
/// `MenuShortcutUniquenessTests.pageMenuChordsAreUnique`.
@MainActor
@Suite("Page › Segments and Project › Read › Reading ▸ (#5652 slice 2)")
struct PageMenuTests {
    @Test("Page › Segments says why its verbs cannot act, once, under Edit Segments")
    func segmentsSayWhy() {
        #expect(SegmentMenuContent.reason(hasPage: false, editing: false, selected: 0)
            == "Show a page in \(SourcePane.name) to edit its segments")
        #expect(SegmentMenuContent.reason(hasPage: true, editing: false, selected: 2)
            == "Turn on Edit Segments to change segments")
        #expect(SegmentMenuContent.reason(hasPage: true, editing: true, selected: 0) == "Select segments on the page")
        #expect(SegmentMenuContent.reason(hasPage: true, editing: true, selected: 1) == nil)
    }

    @Test("Reading ▸ › Run the Recipe on This Folder… says why it cannot act")
    func readingSaysWhy() {
        #expect(FocusedRunRecipeOnFolderButton.disabledReason(hasProject: false, folderId: nil)
            == "Open a project to run its recipe")
        #expect(FocusedRunRecipeOnFolderButton.disabledReason(hasProject: true, folderId: nil)
            == "Select one folder to run the recipe on")
        #expect(FocusedRunRecipeOnFolderButton.disabledReason(hasProject: true, folderId: "f1") == nil)
    }

    @Test("the menu bar runs the recipe on the one selected folder, else the folder the window shows")
    func menuBarFolder() {
        let folders: Set<String> = ["f1", "f2"]
        let isFolder = { (id: String) in folders.contains(id) }
        #expect(RecipeFolderScope.forSelection(["f1"], shownFolderId: "f2", isFolder: isFolder) == "f1")
        #expect(RecipeFolderScope.forSelection([], shownFolderId: "f2", isFolder: isFolder) == "f2")
        #expect(RecipeFolderScope.forSelection(["p1"], shownFolderId: "f2", isFolder: isFolder) == nil, "a page")
        #expect(RecipeFolderScope.forSelection(["f1", "f2"], shownFolderId: nil, isFolder: isFolder) == nil)
    }

    @Test("a folder's context menu runs it on the clicked folder, never on part of a selection")
    func contextMenuFolder() {
        #expect(RecipeFolderScope.forClick(on: "f1", isFolder: true, selection: []) == "f1")
        #expect(RecipeFolderScope.forClick(on: "f1", isFolder: true, selection: ["f1", "f2"]) == nil)
        #expect(RecipeFolderScope.forClick(on: "p1", isFolder: false, selection: []) == nil)
    }
}
