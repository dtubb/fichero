import Foundation
@testable import Fichero
import Testing

/// #5652 slice 3: Project › Activity › Stop and Read Again act on the Activity window's selected run.
/// What breaks without these: a menu item that is on when it can do nothing (or off with no reason), or a
/// second Stop / Read Again in the window that drifts from the menu bar's.
@MainActor
@Suite("Activity's Stop and Read Again in the menu bar (#5652 slice 3)")
struct ActivityRunMenuTests {
    private func target(canStop: Bool, readAgainLabel: String?) -> ActivityRunMenuTarget {
        ActivityRunMenuTarget(
            rowId: "run-1", rowName: "Read the folder", canStop: canStop, readAgainLabel: readAgainLabel,
            stop: {}, readAgain: {}
        )
    }

    @Test("no run selected: both are off, and Stop says to select a run")
    func noRunSelected() {
        #expect(FocusedActivityRunButtons.stopDisabledReason(nil) == "Select a run in the Activity window")
        #expect(FocusedActivityRunButtons.readAgainDisabledReason(nil) == "Select a run in the Activity window")
        #expect(FocusedActivityRunButtons.readAgainTitle(nil) == "Read Again")
    }

    @Test("a running run can be stopped and has nothing to read again yet")
    func runningRun() {
        let running = target(canStop: true, readAgainLabel: nil)
        #expect(FocusedActivityRunButtons.stopDisabledReason(running) == nil)
        #expect(
            FocusedActivityRunButtons.readAgainDisabledReason(running)
                == "Only an ended run with pages to read again offers this"
        )
    }

    @Test("an ended run with pages left offers its own read-again label and cannot be stopped")
    func endedRunWithPagesLeft() {
        let ended = target(canStop: false, readAgainLabel: "Read the 3 pages that failed")
        #expect(
            FocusedActivityRunButtons.stopDisabledReason(ended)
                == "Only a run that is running or waiting can be stopped"
        )
        #expect(FocusedActivityRunButtons.readAgainDisabledReason(ended) == nil)
        #expect(FocusedActivityRunButtons.readAgainTitle(ended) == "Read the 3 pages that failed")
    }

    @Test("the Project menu has an Activity section rendering the focused buttons")
    func projectMenuHasActivitySection() throws {
        let menus = try Self.appSource("App/Menus/ReadKnowledgeMenuCommands.swift")
        let project = try #require(menus.range(of: "CommandMenu(\"Project\")"))
        let activity = try #require(menus.range(of: "Section(\"Activity\") {\n                FocusedActivityRunButtons()"))
        #expect(project.lowerBound < activity.lowerBound, "Activity's section belongs to the Project menu")
    }

    @Test("the row's buttons, its context menu and the menu bar render the same two items")
    func oneComponentEverywhere() throws {
        let buttons = try Self.appSource("App/Menus/FocusedCommands/FocusedCommandButtons+Activity.swift")
        #expect(buttons.contains("ActivityStopMenuItem(target: target)"))
        #expect(buttons.contains("ActivityReadAgainMenuItem(target: target)"))
        let window = try Self.appSource("Views/Activity/Window/ActivityMonitorWindow.swift")
        // Context menu, on the clicked row's target.
        #expect(window.contains("if target.canStop { ActivityStopMenuItem(target: target) }"))
        #expect(window.contains("if target.readAgainLabel != nil { ActivityReadAgainMenuItem(target: target) }"))
        // The row's own buttons, on the same row's target.
        #expect(window.contains("run: runMenuTarget(for: row)"))
        #expect(window.contains("ActivityStopMenuItem(target: run)"))
        #expect(window.contains("ActivityReadAgainMenuItem(target: run)"))
        // No second Stop or Read Again in the window.
        #expect(!window.contains("Button(\"Stop\")"))
        #expect(!window.contains("Button(action: readAgain)"))
        #expect(!window.contains("func readAgain("))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }
}
