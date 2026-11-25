@testable import Fichero
import Foundation
import Testing

/// `segment-actions.automatic-rerun-after-an-edit` (#6069): the lines a shape edit names, and the pause before they are
/// sent. What breaks without these: a drag that asks for a re-read at every step, a text edit that re-reads, or an edited
/// line that is never sent.
@MainActor
@Suite("An edited line is read again after a pause (#6069)")
struct SegmentRereadTests {
    private func anchor() -> SegmentAnchorParams {
        SegmentAnchorParams(
            documentId: "p1", pageId: nil, renditionId: nil, space: nil, rect: [0, 0, 1, 1], polygon: nil,
            rotation: nil, granularity: nil, shapes: nil
        )
    }

    @Test("a move or resize names its line; a join names the kept line; a delete names nothing")
    func affected() {
        let move = SegmentEdit.Call(
            action: "segment.update", params: .update(SegmentUpdateRequest(segmentId: "l1", expectedVersion: 1, anchor: anchor()))
        )
        #expect(SegmentReread.affectedIds(move) == ["l1"])
        let join = SegmentEdit.Call(
            action: "segment.merge",
            params: .merge(SegmentMergeRequest(segmentIds: ["l1", "l2"], keepId: "l1", expectedVersions: ["l1": 1, "l2": 1]))
        )
        #expect(SegmentReread.affectedIds(join) == ["l1"])
        let delete = SegmentEdit.Call(
            action: "segment.delete", params: .delete(SegmentDeleteRequest(segmentIds: ["l1"], expectedVersions: ["l1": 1]))
        )
        #expect(SegmentReread.affectedIds(delete).isEmpty)
    }

    @Test("edits within the pause are sent once, each line once; nothing is sent while they go on")
    func debounce() async throws {
        var sent: [[String]] = []
        let scheduler = SegmentRereadScheduler(delay: .milliseconds(150)) { sent.append($0) }
        scheduler.note(["l1"])
        try await Task.sleep(for: .milliseconds(60))
        scheduler.note(["l1", "l2"])
        try await Task.sleep(for: .milliseconds(60))
        #expect(sent.isEmpty)
        try await Task.sleep(for: .milliseconds(300))
        #expect(sent == [["l1", "l2"]])
    }

    @Test("a cloud-read line is marked out of date until it is read again")
    func staleMarks() {
        let state = SegmentRereadState()
        state.markStale(["l1"])
        #expect(state.stale == ["l1"])
        state.clear(["l1"])
        #expect(state.stale.isEmpty)
    }
}
