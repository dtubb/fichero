//
//  ActivityInspectorSectionTests.swift — `activity.pane.inspector-shows-the-selected-row` (#6441): what the Inspector's
//  Activity section is given for the pane's selection, per row kind, and nothing for no selection.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityInspectorSectionTests {
    typealias Fix = ActivityPaneFixture

    private let all = [Fix.letters, Fix.names, Fix.row("thumbs", .waiting)]
    private var shown: [ActivityMonitorRow] { ActivityPane.outline(all) }

    @Test("a selected run gives the section its job and the versions of its step that ran twice")
    func runRow() throws {
        let pick = try #require(ActivityPane.pick(["letters"], shown: shown, all: all))
        #expect(pick.selection == ActivitySelection(jobId: "letters", libraryId: nil))
        #expect(pick.versions.map(\.step) == ["Read"])
    }

    @Test("a selected version reads its heading, model and pages: Read, Qwen 2 VL, 2 pages, the one that counts")
    func versionRow() throws {
        let pick = try #require(ActivityPane.pick(["letters"], shown: shown, all: all))
        let read = try #require(pick.versions.first)
        let newest = try #require(read.versions.first)
        #expect(read.step == "Read")
        #expect(newest.model == "Qwen 2 VL")
        #expect(newest.children?.count == 2)
        #expect(newest.counts)
    }

    @Test("a selected file gives the section its first page's job and its run's versions")
    func fileRow() throws {
        let file = try #require(shown.first { $0.id == "letters" }?.children?.first)
        let pick = try #require(ActivityPane.pick([file.id], shown: shown, all: all))
        #expect(pick.selection.jobId == "seg-p1")
        #expect(pick.versions.map(\.step) == ["Read"])
    }

    @Test("a selected job of its own gives the section its job and no versions")
    func jobRow() throws {
        let pick = try #require(ActivityPane.pick(["thumbs"], shown: shown, all: all))
        #expect(pick.selection.jobId == "thumbs")
        #expect(pick.versions.isEmpty)
    }

    @Test("nothing selected, several selected, or a row no longer listed: the section is given nothing")
    func emptyState() {
        #expect(ActivityPane.pick([], shown: shown, all: all) == nil)
        #expect(ActivityPane.pick(["letters", "names"], shown: shown, all: all) == nil)
        #expect(ActivityPane.pick(["gone"], shown: shown, all: all) == nil)
    }

    @Test("a row with no job behind it gives the section nothing")
    func rowWithNoJob() {
        let bare = Fix.row("bare", .waiting, jobId: nil)
        #expect(ActivityPane.pick(["bare"], shown: [bare], all: [bare]) == nil)
    }
}
