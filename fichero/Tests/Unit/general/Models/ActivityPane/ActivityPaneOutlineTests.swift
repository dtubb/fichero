//
//  ActivityPaneOutlineTests.swift — `activity.pane.one-outline-table` (#6441): ONE flat table, sorted by state then start,
//  no section rows, TWO levels (a run and its files). Breaks if sections, steps or a third level come back.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityPaneOutlineTests {
    typealias Fix = ActivityPaneFixture

    /// `activity.pane.needs-you-first` (#6599, supersedes the plain state-then-start order): what needs the person first.
    @Test("rows sort by what needs you first: failed and paused for a cause, then running, then waiting, then done, newest first")
    func flatOrder() {
        var mine = Fix.row("paused-by-you", .paused, started: Fix.day.addingTimeInterval(30))
        mine.reason = "Paused by you"
        let rows = ActivityPane.outline([
            Fix.row("done-old", .done, started: Fix.day), Fix.row("failed", .failed, started: Fix.day),
            Fix.row("running", .running), Fix.row("done-new", .done, started: Fix.day.addingTimeInterval(60)),
            Fix.row("paused", .paused, started: Fix.day.addingTimeInterval(10)), Fix.row("waiting", .waiting), mine
        ])
        #expect(rows.map(\.id) == ["paused", "failed", "running", "paused-by-you", "waiting", "done-new", "done-old"])
    }

    @Test("a run opens to its files, one per document, never to its steps; a file holds its pages' worst state")
    func twoLevels() throws {
        let run = try #require(ActivityPane.outline([Fix.letters]).first)
        let files = try #require(run.children)
        #expect(files.map(\.documentId) == ["p1", "p2"])
        #expect(files.allSatisfy { $0.kind == .page && $0.children == nil }, "two levels: a file has no rows under it")
        #expect(files[1].phase == .failed, "p2 failed once: the failure shows over the done reads")
        #expect(files[1].total == 3, "p2's three page runs: Segment, Read, Read again")
        #expect(!files.contains { $0.kind == .step })
    }

    /// `activity.pane.children-are-what-it-works-on` (#6599): a job of its own opens to the files in flight, by name.
    @Test("a thumbnails queue with two pages in flight opens to those two files by name; none in flight, no disclosure")
    func queueOpensToItsFilesInFlight() throws {
        let queue = Fix.row("waiting:thumbnail", .waiting, kind: .job, total: 14)
        let items = [ActivityQueuedItem(id: "q1", subject: "d1", state: "running", name: "IMG_0412.jpg"),
                     ActivityQueuedItem(id: "q2", subject: "d2", state: "running", name: "IMG_0413.jpg"),
                     ActivityQueuedItem(id: "q3", subject: "d3", state: "waiting", name: "IMG_0414.jpg")]
        let row = try #require(ActivityPane.outline(ActivityPane.withQueuedFiles([queue], queued: ["thumbnail": items])).first)
        #expect(row.children?.map(\.name) == ["IMG_0412.jpg", "IMG_0413.jpg"])
        #expect(row.children?.allSatisfy { $0.kind == .page && $0.children == nil } == true)
        let idle = ActivityPane.withQueuedFiles([queue], queued: ["thumbnail": [items[2]]])
        #expect(ActivityPane.outline(idle).first?.children == nil)
    }

    @Test("a job with no tree has no disclosure")
    func noTreeNoDisclosure() {
        #expect(ActivityPane.outline([Fix.row("thumbs", .waiting)]).first?.children == nil)
    }

    @Test("the disclosure state is remembered per pane, and survives a relaunch through the stored prefs")
    func rememberedDisclosure() {
        let data = ActivityPanePrefs.store(Data(), key: "pane-a") { $0.expanded.insert("letters") }
        #expect(ActivityPanePrefs.load(data, key: "pane-a").expanded == ["letters"])
        #expect(ActivityPanePrefs.load(data, key: "pane-b").expanded.isEmpty, "another pane keeps its own")
    }

    @Test("a column header sorts the top-level rows and keeps each run's files in tree order; no sort keeps the outline's")
    func sortedByAColumn() {
        let outline = ActivityPane.outline([ActivityPaneFixture.letters, ActivityPaneFixture.names])
        #expect(ActivityPane.sorted(outline, by: []).map(\.id) == outline.map(\.id))
        let byName = ActivityPane.sorted(outline, by: [KeyPathComparator(\.name)])
        #expect(byName.map(\.name) == ["Letters", "Names"])
        #expect(ActivityPane.sorted(outline, by: [KeyPathComparator(\.name, order: .reverse)]).map(\.name) == ["Names", "Letters"])
        #expect(byName.first?.children?.map(\.id) == outline.first { $0.id == "letters" }?.children?.map(\.id))
        #expect(ActivityPane.sorted(outline, by: [KeyPathComparator(\.stateRankKey)]).first?.id == "names", "running sorts first")
    }

    /// `activity.window.acts-on` (#5839, ruled 2026-11-23): the pane's file rows under a run row ARE the list; the counts are the Trail.
    @Test("a running recipe run says its trail and opens to its files, each with its state and a failed page's reason")
    func runRowOpensToItsFilesWithStateAndReason() throws {
        var failed = Fix.page("r-p2", .failed, doc: "p2", model: "Kraken")
        failed.reason = "no lines found"
        var run = Fix.row("recipe", .running, kind: .run, name: "Letters", children: [
            Fix.row("read", .running, kind: .step, name: "Read", model: "Kraken",
                    children: [Fix.page("r-p1", .done, doc: "p1", model: "Kraken"), failed,
                               Fix.page("r-p3", .running, doc: "p3", model: "Kraken")])
        ])
        run.trail = "Segment ✓ → Read ▶ 1/3"
        let row = try #require(ActivityPane.outline([run]).first)
        #expect(ActivityPane.progressLine(row) == "Segment ✓ → Read ▶ 1/3", "the Trail is the count")
        let files = try #require(row.children)
        #expect(files.map(\.documentId) == ["p1", "p2", "p3"])
        #expect(files.map(\.phase) == [.done, .failed, .running])
        #expect(files[1].reason == "no lines found", "the failed page's reason is on its row")
    }
}
