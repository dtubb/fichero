@testable import Fichero
import Foundation
import Testing

/// `activity.pane.blocked-under-its-blocker` (#6593, #6588; spec docs/contributor_manual/specs/ui/activity-pane.md):
/// blocked work is listed UNDER its blocker, each blocked row with the lock and no sentence; the blocker's words are
/// said once, on the blocker; a need no listed job supplies gets one row of its own.
struct ActivityBlockedRowsTests {
    private func job(_ id: String, _ name: String, state: ActivityJob.State = .waiting, blockedBy: String? = nil,
                     reason: String? = nil) -> ActivityMonitorRow {
        var job = ActivityJob(id: id, taskType: "embed", name: name, total: 2618, state: state, reason: reason)
        job.blockedBy = blockedBy
        return ActivityMonitorRow.job(job, libraryId: nil, projectName: nil)
    }

    @Test("the embeds blocked on the download are its children, with the lock and no line")
    func underTheDownload() throws {
        let download = job("dl-1", "Download bge-m3", state: .running)
        let embeds = job("blocked:dl-1", "Embed for search · 2,618 pages", blockedBy: "dl-1",
                         reason: "Waiting for the search model")
        let rows = ActivityPane.underBlockers([download, embeds])

        #expect(rows.map(\.name) == ["Download bge-m3"], "a blocked row is never a top-level row of its own")
        let child = try #require(rows.first?.children?.first)
        #expect(child.name == "Embed for search · 2,618 pages")
        #expect(ActivityPane.glyph(child).symbol == "lock.circle" && ActivityPane.glyph(child).word == "Blocked")
        #expect(ActivityPane.stateLine(child).isEmpty, "no sentence on a blocked row")
    }

    @Test("a need no listed job supplies is one row, its blocked work under it")
    func underANeed() {
        let one = job("blocked:a", "Embed for search · 12 pages", blockedBy: "model:embeddings:bge-m3")
        let two = job("blocked:b", "Prepare pages · Letters · 2,618", blockedBy: "model:embeddings:bge-m3")
        let rows = ActivityPane.underBlockers([one, two])
        #expect(rows.map(\.name) == ["Search model bge-m3"])
        #expect(rows.first?.children?.count == 2)
    }

    @Test("work not blocked is left as it is")
    func nothingBlocked() {
        let rows = [job("w", "Embed for search"), job("d", "Download", state: .running)]
        #expect(ActivityPane.underBlockers(rows).map(\.id) == rows.map(\.id))
        #expect(ActivityPane.glyph(rows[0]).symbol == "circle")
    }
}
