//
//  ActivityWindowIsAPaneTests.swift — `activity.window.is-the-pane-plus-inspector`, `activity.one-window`,
//  `activity.pane.inspector-shows-the-selected-row` and `activity.pane.commands-through-the-table` (#6441): one window,
//  the pane plus the Inspector; the details mounted once; the verbs in Project › Activity from one definition.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ActivityWindowIsAPaneTests {
    @Test("one Activity Window scene; no detail window; nothing opens a second Activity window")
    func oneWindow() throws {
        let app = try AppSource.code("FicheroApp.swift")
        #expect(app.components(separatedBy: "Window(\"Activity").count - 1 == 1)
        #expect(!app.contains("ActivityDetailWindow"))
        let root = try AppSource.root()
        #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent(
            "Views/Activity/Window/ActivityDetailWindow.swift").path))
    }

    @Test("the details view is mounted in the Inspector section and the compact push, nowhere else")
    func detailsMountedOnce() throws {
        let root = try AppSource.root()
        let files = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)?
            .compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" } ?? []
        let mounts = try files.filter { url in
            try String(contentsOf: url, encoding: .utf8).contains("ActivityDetailsView(selection:")
        }.map(\.lastPathComponent).sorted()
        #expect(mounts == ["ActivityDetailsView.swift", "ActivityInspectorSection.swift", "ContentView+Navigation.swift"])
    }

    @Test("the main window's Inspector shows the Activity section while the Activity pane holds the focus")
    func mainInspector() throws {
        let layout = try AppSource.code("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift")
        #expect(layout.contains("if let pick = windowState.activityPick, inspectsActivity {"))
        #expect(layout.contains("if paneFocusHint == .activity { return true }"))
    }

    @Test("Show in Activity selects its row in the one window")
    func showInActivity() {
        let state = ActivityWindowSelectionState()
        state.select(ActivitySelection(jobId: "run-1", libraryId: nil))
        #expect(state.reveal?.jobId == "run-1")
    }

    @Test("Project › Activity lists the one verb list once, enabled by the pane's selection")
    func commands() throws {
        #expect(FocusedActivityVerbButtons.verbs == [.pause, .resume, .retry, .archive, .putBack, .delete])
        #expect(Set(FocusedActivityVerbButtons.verbs).count == FocusedActivityVerbButtons.verbs.count)
        let menus = try AppSource.code("App/Menus/PageAndProjectMenuCommands.swift")
        #expect(menus.components(separatedBy: "FocusedActivityVerbButtons()").count - 1 == 1)
    }

    @Test("less is more: one status bar, no footer notice, no section rows, no stage bar in the pane")
    func lessIsMore() throws {
        let pane = try AppSource.code("Views/Activity/Pane/ActivityPaneView.swift")
        let table = try AppSource.code("Views/Activity/Pane/ActivityPaneView+Table.swift")
        #expect(pane.contains("accessibilityIdentifier(\"activity.statusbar\")"))
        #expect(!pane.contains("ActivityFooterLine") && !table.contains("ActivityStageBar"))
        #expect(!pane.contains("Section(") && !table.contains("Section("))
        #expect(!pane.contains("ActivityModeButton"), "Run Automatically is the setting")
    }
}
