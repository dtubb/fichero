//
//  ActivityPaneGroupByFileTests.swift — `activity.pane.group-by-run-or-by-file` (#6441): the same rows by file, each
//  file opening to its path through the steps in run order, the counting version marked.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityPaneGroupByFileTests {
    @Test("two runs: page 2 has its steps in run order, the two Read versions with their models, the Qwen one counting")
    func pathThroughTheSteps() throws {
        let files = ActivityPane.byFile([ActivityPaneFixture.names, ActivityPaneFixture.letters])
        #expect(files.map(\.documentId) == ["p1", "p2"])
        let p2 = try #require(files.last)
        #expect(p2.name == "Page p2")
        let path = try #require(p2.children)
        #expect(path.map(\.name) == ["Letters › Segment", "Letters › Read", "Letters › Read", "Names › Names"])
        #expect(path.map(\.model) == ["Kraken", "Kraken", "Qwen 2 VL", "Claude"], "a page with no model of its own takes its step's")
        #expect(path.map(\.counts) == [true, false, true, false])
        #expect(p2.phase == .running, "a file row shows what runs on it now")
    }

    @Test("the selection survives the switch: a file's id is the same whichever run it is reached from")
    func stableFileIds() {
        let once = ActivityPane.byFile([ActivityPaneFixture.letters]).map(\.id)
        let twice = ActivityPane.byFile([ActivityPaneFixture.letters, ActivityPaneFixture.names]).map(\.id)
        #expect(once == ["file:p1", "file:p2"])
        #expect(twice == once)
    }

    @Test("a file selected by Run is still selected by File, and a page's step selected by File is its file back by Run")
    func carriedAcrossTheSwitch() {
        let runs = [ActivityPaneFixture.letters, ActivityPaneFixture.names]
        let byRun = ActivityPane.outline(runs), byFile = ActivityPane.byFile(runs)
        let fileUnderRun = byRun.compactMap(\.children).flatMap { $0 }.first { $0.documentId == "p2" }?.id ?? ""
        #expect(ActivityPane.carry([fileUnderRun], into: byFile) == ["file:p2"])
        let step = byFile.last?.children?.first?.id ?? ""
        #expect(step.hasPrefix("file:p2|"))
        let back = ActivityPane.carry([step], into: byRun)
        #expect(back.count == 1 && back.first?.hasSuffix("|file:p2") == true)
        #expect(ActivityPane.carry([ActivityPaneFixture.letters.id], into: byFile).isEmpty, "a run is no file")
    }

    @Test("the grouping is remembered per pane and a new pane opens by Run")
    func remembered() {
        #expect(ActivityPanePrefs().grouping == .run)
        let data = ActivityPanePrefs.store(Data(), key: "pane") { $0.grouping = .file }
        #expect(ActivityPanePrefs.load(data, key: "pane").grouping == .file)
    }
}
