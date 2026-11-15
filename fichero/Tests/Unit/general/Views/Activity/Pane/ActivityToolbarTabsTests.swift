@testable import Fichero
import Foundation
import SwiftUI
import Testing

/// `activity.window.toolbar-tabs` (#6588, decision 23; spec docs/contributor_manual/specs/ui/activity-pane.md): Runs | Files |
/// Cost | Where, each a grouping and a column set over the same rows, per pane and remembered.
@MainActor
struct ActivityToolbarTabsTests {
    typealias Tab = ActivityPane.Tab

    @Test("each tab is a grouping and its columns: Files by file, the others by run; Cost and Where their own columns")
    func tabsAreGroupingsAndColumns() {
        // The sidebar's five items since decision 32 (Archived its own item, `activity.window.sidebar`).
        #expect(Tab.allCases.map(\.title) == ["Runs", "Files", "Cost", "Where", "Archived"])
        #expect(Tab.allCases.map(\.grouping) == [.run, .file, .run, .run, .run])
        let prefs = ActivityPanePrefs()
        #expect(prefs.columns(for: .cost)[visibility: "tokens"] == .visible)
        #expect(prefs.columns(for: .cost)[visibility: "trail"] == .hidden)
        #expect(prefs.columns(for: .place)[visibility: "runsOn"] == .visible)
        #expect(prefs.columns(for: .place)[visibility: "cost"] == .hidden)
        #expect(Set(Tab.runs.columns) == Set(ActivityPane.Column.allCases.filter(\.isOnByDefault)), "Runs is the old default")
    }

    @Test("a column a person turns on in one tab stays in that tab, and the tab survives a relaunch")
    func rememberedPerTab() throws {
        var prefs = ActivityPanePrefs()
        prefs.tab = .cost
        var cost = prefs.columns(for: .cost)
        cost[visibility: "lane"] = .visible
        prefs.setColumns(cost, for: .cost)
        let stored = ActivityPanePrefs.store(Data(), key: "p") { $0 = prefs }
        let loaded = ActivityPanePrefs.load(stored, key: "p")
        #expect(loaded.tab == .cost)
        #expect(loaded.columns(for: .cost)[visibility: "lane"] == .visible)
        #expect(loaded.columns(for: .runs)[visibility: "lane"] != .visible, "the Runs tab is untouched")
    }

    @Test("prefs stored before the tabs still load, their grouping becoming the tab")
    func oldPrefsLoad() throws {
        let old = Data(#"{"p":{"grouping":"file","filter":"state: failed","expanded":[]}}"#.utf8)
        let loaded = ActivityPanePrefs.load(old, key: "p")
        #expect(loaded.filter == "state: failed", "nothing reset")
        #expect(loaded.tab == .files)
    }

    @Test("the Where cell says where the engine says it runs; To Finish only while it runs and spends")
    func whereAndToFinish() {
        var row = ActivityPaneFixture.row("r", .running, costUsd: 0.4)
        #expect(ActivityPane.whereLine(row).isEmpty)
        row.runsOn = "cluster"
        #expect(ActivityPane.whereLine(row) == "Cluster")
        row.costEstimateUsd = 1.2
        #expect(ActivityPane.toFinishLine(row) == "~$1.20")
        row.phase = .done
        #expect(ActivityPane.toFinishLine(row).isEmpty)
    }

    @Test("a tab names its columns: File and Last Run on Files, Spent on Cost; the others keep their own titles")
    func titles() {
        #expect(ActivityPane.Column.name.title(in: .files) == "File")
        #expect(ActivityPane.Column.started.title(in: .files) == "Last Run")
        #expect(ActivityPane.Column.cost.title(in: .cost) == "Spent")
        #expect(ActivityPane.Column.name.title(in: .runs) == "Name")
        #expect(ActivityPane.Column.cost.title(in: .runs) == "Cost")
    }
}
