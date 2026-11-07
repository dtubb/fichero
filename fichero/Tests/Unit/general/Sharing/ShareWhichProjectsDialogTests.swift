//
//  ShareWhichProjectsDialogTests.swift
//  FicheroTests
//
//  sharing.host.asks-which-projects-when-nothing-is-shared / sharing.host.which-projects-dialog (#6366): the dialog opens
//  only when nothing is shared, Share is off until a project is checked, and Share sends one call per checked project and
//  chosen person; Not Now sends nothing.
//

@testable import Fichero
import Testing

@MainActor
struct ShareWhichProjectsDialogTests {
    @Test func opensOnlyWhenTheEngineSaysNothingIsShared() {
        #expect(ShareWhichProjectsModel.opens(sharedCount: 0))
        #expect(!ShareWhichProjectsModel.opens(sharedCount: 1))
        #expect(!ShareWhichProjectsModel.opens(sharedCount: nil), "an older engine: no count, no dialog")
    }

    @Test func checkingNothingLeavesShareOff() {
        #expect(!ShareWhichProjectsModel().canShare)
    }

    @Test func checkingAAndChoosingMayaAsEditorSendsExactlyOneCall() {
        var model = ShareWhichProjectsModel()
        model.checked = ["A"]
        model.people = ["A": ["maya": "editor"], "B": ["sam": "viewer"]]
        #expect(model.canShare)
        #expect(model.grants(order: ["A", "B"]) == [.init(libraryId: "A", personId: "maya", role: "editor")])
    }

    /// Multi-user off, A and B checked: ONE link gives both, the first one's Share sheet makes it (#6366, ruled sub-bullet).
    @Test func withNoAccountsOneLinkCarriesEveryCheckedProjectInOrder() {
        var model = ShareWhichProjectsModel()
        model.checked = ["C", "A"]
        #expect(model.linkSet(order: ["A", "B", "C"]) == ["A", "C"])
    }

    @Test func notNowSendsNothing() {
        #expect(ShareWhichProjectsModel().grants(order: ["A", "B"]).isEmpty)
    }

#if canImport(AppKit)
    @Test func thePaneSaysNothingIsSharedInOneSentence() {
        #expect(ShareSettingsView.nothingSharedSentence == "Sharing is on. No project is shared yet.")
    }
#endif
}
