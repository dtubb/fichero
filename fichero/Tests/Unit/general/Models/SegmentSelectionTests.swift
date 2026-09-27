@testable import Fichero
import Testing

/// `source.editor.selection-shared` and every editor verb behind it (#4941).
///
/// The app had three ways to say what is selected and none of them could address a
/// SEGMENT: `RegionSelection` holds indices into one artifact's box list, the reader
/// posts character offsets, and `FocusedRegionSelection` holds region-node document
/// ids. Every engine verb needs an id and a version — `segment.update` takes
/// `segment_id` and `expected_version`, `segment.delete` a version per id — so this
/// is the vocabulary the editor has to have before any of its verbs can exist.
///
/// What these tests pin is the refusals and the pruning, because those are what stop
/// a verb acting on a page the person is not looking at or on a row that is gone.
@MainActor
struct SegmentSelectionTests {

    private func selection() -> SegmentSelection { SegmentSelection() }

    @Test("a selection carries ids, its document, and the versions a verb must send")
    func selectionCarriesWhatAVerbNeeds() {
        let sel = selection()

        sel.select(["seg-1", "seg-2"], documentId: "doc-1", passId: "pass-1",
                   versions: ["seg-1": 3, "seg-2": 1])

        #expect(sel.segmentIds == ["seg-1", "seg-2"])
        #expect(sel.documentId == "doc-1")
        #expect(sel.passId == "pass-1")
        #expect(sel.expectedVersions == ["seg-1": 3, "seg-2": 1])
    }

    @Test("pick order is kept, because it is a record of what the person did")
    func pickOrderIsKept() {
        let sel = selection()

        sel.select(["seg-3"], documentId: "doc-1")
        sel.add("seg-1", documentId: "doc-1")
        sel.add("seg-2", documentId: "doc-1")

        #expect(sel.segmentIds == ["seg-3", "seg-1", "seg-2"], "not sorted, not reordered")
    }

    @Test("adding the same segment twice does not duplicate it")
    func addIsIdempotent() {
        let sel = selection()

        sel.select(["seg-1"], documentId: "doc-1")
        sel.add("seg-1", documentId: "doc-1")

        #expect(sel.segmentIds == ["seg-1"])
    }

    @Test("a selection never spans documents, and the refused add says so")
    func crossDocumentAddIsRefused() {
        // Two pages share no coordinate frame, no pass and no reading order. A verb
        // sent ids from two pages would be one audited action claiming to be about a
        // page it is not. `add` returns false so a caller can say why — a shift-click
        // that appears to do nothing is a bug report, and one that silently moved the
        // selection to another page is worse.
        let sel = selection()
        sel.select(["seg-1"], documentId: "doc-1")

        let accepted = sel.add("seg-9", documentId: "doc-2")

        #expect(accepted == false)
        #expect(sel.segmentIds == ["seg-1"])
        #expect(sel.documentId == "doc-1")
    }

    @Test("deselecting the last segment clears the document and pass too")
    func emptyingClearsTheContext() {
        // A selection of nothing that still claims a document would let a verb's
        // "is this the page on screen?" check pass on an empty selection.
        let sel = selection()
        sel.select(["seg-1"], documentId: "doc-1", passId: "pass-1")

        sel.deselect("seg-1")

        #expect(sel.isEmpty)
        #expect(sel.documentId == nil)
        #expect(sel.passId == nil)
    }

    @Test("pruning drops ids the page no longer has and REPORTS them")
    func pruningReportsWhatWent() {
        // A merge makes its absorbed ids stop existing; a delete removes one. Keeping
        // them sends a verb ids the engine refuses one at a time; dropping them
        // silently makes a Delete act on fewer lines than are highlighted.
        let sel = selection()
        sel.select(["seg-1", "seg-2", "seg-3"], documentId: "doc-1",
                   versions: ["seg-1": 1, "seg-2": 1, "seg-3": 1])

        let gone = sel.prune(toLive: ["seg-1", "seg-3"])

        #expect(gone == ["seg-2"])
        #expect(sel.segmentIds == ["seg-1", "seg-3"])
        #expect(sel.expectedVersions?.keys.sorted() == ["seg-1", "seg-3"])
    }

    @Test("pruning everything clears the selection rather than leaving an empty one in place")
    func pruningEverythingClears() {
        let sel = selection()
        sel.select(["seg-1"], documentId: "doc-1", passId: "pass-1", versions: ["seg-1": 1])

        #expect(sel.prune(toLive: []) == ["seg-1"])
        #expect(sel.isEmpty)
        #expect(sel.documentId == nil)
    }

    @Test("pruning nothing is not a change")
    func pruningNothingIsNoChange() {
        let sel = selection()
        sel.select(["seg-1"], documentId: "doc-1")

        #expect(sel.prune(toLive: ["seg-1", "seg-2"]) == [])
        #expect(sel.segmentIds == ["seg-1"])
    }

    @Test("expectedVersions is all or nothing")
    func versionsAreAllOrNothing() {
        // `segment.delete` takes a version per id. A partial map would delete the rows
        // it knows versions for and refuse the rest: half a Delete, which is worse than
        // none — so a verb must be able to tell that it cannot send one at all.
        let sel = selection()
        sel.select(["seg-1", "seg-2"], documentId: "doc-1", versions: ["seg-1": 3])

        #expect(sel.expectedVersions == nil)

        sel.select(["seg-1", "seg-2"], documentId: "doc-1",
                   versions: ["seg-1": 3, "seg-2": 4])
        #expect(sel.expectedVersions == ["seg-1": 3, "seg-2": 4])
    }

    @Test("versions for segments that are not selected are dropped on select")
    func staleVersionsDoNotRideAlong() {
        // Otherwise a later add of that id would carry a version read before the
        // previous selection changed — a stale compare-and-set that looks fresh.
        let sel = selection()

        sel.select(["seg-1"], documentId: "doc-1", versions: ["seg-1": 1, "seg-old": 7])

        #expect(sel.expectedVersions == ["seg-1": 1])
    }

    @Test("an empty selection has no versions to send")
    func emptySelectionHasNoVersions() {
        #expect(selection().expectedVersions == nil)
    }
}
