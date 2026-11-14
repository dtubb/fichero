//
//  ActivityCommandsTests.swift — `activity.pane.commands-through-the-table` (#6441): Show in Activity's target, and the
//  background lane's two commands kept apart from a row's verbs.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ActivityCommandsTests {
    @Test("Show in Activity on a page selects the page's file row by File, else its document's; nothing when neither is listed")
    func showInActivityTarget() {
        let files = ActivityPane.byFile([ActivityPaneFixture.letters, ActivityPaneFixture.names])
        #expect(ActivityPane.fileRowId(["p2"], in: files) == "file:p2")
        #expect(ActivityPane.fileRowId(["unread-page", "p1"], in: files) == "file:p1", "a page with no row of its own: its document")
        #expect(ActivityPane.fileRowId(["elsewhere"], in: files) == nil)
    }

    @Test("Show in Activity asks the one window for the page, then its parent document")
    func showFileAsksTheWindow() {
        let state = ActivityWindowSelectionState()
        state.showFile(Document(id: "page", parentId: "letter", name: "Page 1"))
        #expect(state.revealFiles == ["page", "letter"])
        state.showFile(Document(id: "letter", name: "Letter"))
        #expect(state.revealFiles == ["letter"])
    }

    @Test("every verb of the one list has one title, and none is a background-lane command's")
    func oneTitlePerVerb() {
        let titles = ActivityPaneVerb.allCases.map(\.title)
        #expect(Set(titles).count == titles.count)
        #expect(!titles.contains(RunAutomaticallySetting.pauseCommand) && !titles.contains(RunAutomaticallySetting.resumeCommand))
        #expect(titles.contains("Continue") && !titles.contains("Resume"), "a row continues; only the lane resumes")
    }
}
