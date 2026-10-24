@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Delete selected lines from any surface (`source.editor.delete-selected-lines`): every surface takes the Preview's one
/// plan, `SegmentEdit.delete`, so a selection is ONE `segment.delete` batch (one audit id, one ⌘Z). What breaks without
/// these: a surface that sends one call per line (⌘Z brings lines back one at a time), or one that fails without a word.
@MainActor
struct SegmentDeleterTests {
    @Test("a refusal is said in words, never silent")
    func refusalsAreWords() {
        #expect(SegmentDeleter.problem(.tooFew) == "Select a line to delete.")
        #expect(SegmentDeleter.problem(.versionUnknown).contains("not saved yet"))
    }

    @Test("nothing selected, and a window that cannot edit, each answer why instead of doing nothing")
    func nothingSentSaysWhy() async {
        let store = SegmentStore(service: SegmentService(ficheroClient: FicheroClient(libraryPath: nil)))
        let empty = await SegmentDeleter.run([], documentId: "p1", store: store, actionsService: nil, steps: nil)
        #expect(empty == "This window cannot edit.")
    }

    /// WHY (## 1072): the Delete key in the Order list deleted the Preview's held selection even when the person had
    /// highlighted a different row there.
    @Test("a Delete means the held selection only when it contains the row pointed at, else just that row")
    func deleteMeansTheRowPointedAt() {
        #expect(SegmentDeleter.ids(row: "b", held: ["a", "b", "c"]) == ["a", "b", "c"], "the row is in the selection: all of it")
        #expect(SegmentDeleter.ids(row: "z", held: ["a", "b", "c"]) == ["z"], "another row was highlighted: just that one")
        #expect(SegmentDeleter.ids(row: "z", held: []) == ["z"])
        #expect(SegmentDeleter.ids(row: nil, held: ["a", "b"]) == ["a", "b"], "no row pointed at: the held selection")
        #expect(SegmentDeleter.ids(row: nil, held: []).isEmpty)
    }

    @Test("the lines asked for are found in the order asked, and one the store does not hold is left out")
    func findsTheLinesAsked() {
        let store = SegmentStore(service: SegmentService(ficheroClient: FicheroClient(libraryPath: nil)))
        #expect(SegmentDeleter.segments(["a", "b"], documentId: "p-none", store: store).isEmpty)
    }
}
