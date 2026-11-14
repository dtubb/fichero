//
//  ActivityPaneOutlineTests.swift — `activity.pane.one-outline-table` (#6441): ONE flat table, sorted by state then start,
//  no section rows, TWO levels (a run and its files). Breaks if sections, steps or a third level come back.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityPaneOutlineTests {
    typealias F = ActivityPaneFixture

    @Test("rows sort by state then start: running, paused, waiting, failed, done; newest first within a state")
    func flatOrder() {
        let rows = ActivityPane.outline([
            F.row("done-old", .done, started: F.day), F.row("failed", .failed, started: F.day),
            F.row("running", .running), F.row("done-new", .done, started: F.day.addingTimeInterval(60)),
            F.row("paused", .paused), F.row("waiting", .waiting)
        ])
        #expect(rows.map(\.id) == ["running", "paused", "waiting", "failed", "done-new", "done-old"])
    }

    @Test("a run opens to its files, one per document, never to its steps; a file holds its pages' worst state")
    func twoLevels() throws {
        let run = try #require(ActivityPane.outline([F.letters]).first)
        let files = try #require(run.children)
        #expect(files.map(\.documentId) == ["p1", "p2"])
        #expect(files.allSatisfy { $0.kind == .page && $0.children == nil }, "two levels: a file has no rows under it")
        #expect(files[1].phase == .failed, "p2 failed once: the failure shows over the done reads")
        #expect(files[1].total == 3, "p2's three page runs: Segment, Read, Read again")
        #expect(!files.contains { $0.kind == .step })
    }

    @Test("a job with no tree has no disclosure")
    func noTreeNoDisclosure() {
        #expect(ActivityPane.outline([F.row("thumbs", .waiting)]).first?.children == nil)
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

    @Test("the pane draws no section header: the view has no Section and no Now / Up Next / Done Today")
    func noSectionRows() throws {
        let source = try AppSource.code("Views/Activity/Pane/ActivityPaneView+Table.swift")
        #expect(!source.contains("Section("))
        #expect(!source.contains("Up Next") && !source.contains("Done Today"))
    }
}
