@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.make-region-in-every-menu`,
/// `segment-editor.make-region-selects-the-region`. What breaks without these: Make Region from Lines or Ungroup Region
/// missing from the row menu, offered for one line, a Join titled the same for two lines and for five, or a selection that
/// stays on the lines after the engine made the region.
@MainActor
@Suite(.tags(.paleography))
struct SegmentVerbMenuTests {
    @Test("two lines are offered Make Region from Lines; one line is not; a region is offered Ungroup Region")
    func offered() {
        #expect(SegmentVerbMenu.regionVerbs(kinds: ["line", "line"]) == [.makeRegion])
        #expect(SegmentVerbMenu.regionVerbs(kinds: ["line"]).isEmpty)
        #expect(SegmentVerbMenu.regionVerbs(kinds: ["region"]) == [.ungroupRegion])
        #expect(SegmentVerbMenu.regionVerbs(kinds: ["line", "region"]) == [.makeRegion, .ungroupRegion])
        #expect(SegmentVerbMenu.regionVerbs(kinds: []).isEmpty)
    }

    @Test("the verbs are titled as the Edit menu titles them")
    func titles() {
        #expect(SegmentVerbMenu.RegionVerb.makeRegion.title == "Make Region from Lines")
        #expect(SegmentVerbMenu.RegionVerb.ungroupRegion.title == "Ungroup Region")
    }

    @Test("Join and Delete are titled by what is selected")
    func labels() {
        #expect(SegmentMenuContent.joinTitle(2) == "Join 2 Segments")
        #expect(SegmentMenuContent.joinTitle(5) == "Join 5 Segments")
        #expect(SegmentMenuContent.joinTitle(1) == "Join")
        #expect(SegmentMenuContent.deleteTitle(1) == "Delete Segment")
        #expect(SegmentMenuContent.deleteTitle(3) == "Delete 3 Segments")
    }

    @Test("after segment.group_lines the selection is the answer's region_id; with none it is left as it was")
    func selectionIsTheRegion() {
        #expect(SegmentEdit.selectionAfterGroup(regionId: "r1") == ["r1"])
        #expect(SegmentEdit.selectionAfterGroup(regionId: nil).isEmpty)
    }

    @Test("the answer's top-level strings are read by key")
    func answerStrings() {
        let value: [String: (any Sendable)?] = ["region_id": "r1", "n": 3, "segment_ids": ["r1"]]
        #expect(ActionInvokeResult.strings(value) == ["region_id": "r1"])
        #expect(ActionInvokeResult.strings(nil).isEmpty)
    }
}
