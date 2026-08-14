@testable import Fichero
import XCTest

@MainActor
final class ActivityWindowSelectionStateTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = try AppSource.root()
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }

    func testSelectReplacesSharedSelection() {
        let state = ActivityWindowSelectionState()
        let run = SelectedActivityRun(
            id: "run-1",
            name: "Workflow",
            workflowId: "wf-1",
            threadId: "thread-1",
            timestamp: Date(timeIntervalSince1970: 1_700_000_000),
            status: .running,
            isLive: true,
            libraryId: UUID(uuidString: "11111111-1111-1111-1111-111111111111")
        )

        state.select(run)

        XCTAssertEqual(state.selectedRun?.id, "run-1")
        XCTAssertEqual(state.selectedRun?.threadId, "thread-1")
        XCTAssertEqual(state.libraryId, run.libraryId)
    }

    func testSelectCanClearSelection() {
        let state = ActivityWindowSelectionState()
        state.select(SelectedActivityRun(
            id: "run-1",
            name: "Workflow",
            workflowId: "wf-1",
            threadId: "thread-1",
            timestamp: Date(timeIntervalSince1970: 1_700_000_000),
            status: .running,
            isLive: true
        ))

        state.select(nil)

        XCTAssertNil(state.selectedRun)
    }

    func testActivityWindowIDsStayStable() {
        XCTAssertEqual(ActivityWindowSelectionState.monitorWindowID, "activity-monitor")
        XCTAssertEqual(ActivityWindowSelectionState.detailWindowID, "activity-detail")
    }

    func testActivityUsesStandaloneMonitorAndDetailWindows() throws {
        // ActivityDetailWindow now lives in its own file (Views/Activity/Window/ActivityDetailWindow.swift),
        // so ActivityMonitorWindow.swift no longer contains the inlined detail view.
        let appSource = try Self.appSource("FicheroApp.swift")
        let monitorSource = try Self.appSource("Views/Activity/Window/ActivityMonitorWindow.swift")
        let detailSource = try Self.appSource("Views/Activity/Window/ActivityDetailWindow.swift")
        let helpersSource = try Self.appSource("Views/Activity/ActivityViewHelpers.swift")

        // #4524: the Window menu entry is the Activity scene's AUTOMATIC item
        // (SwiftUI lists every `Window` scene's title in the Windows menu), so
        // no hand-rolled CommandGroup button may exist — it was the duplicate.
        // The shortcut rides the scene; the detail scene suppresses its item.
        XCTAssertFalse(appSource.contains("ActivityWindowMenuButton()"))
        XCTAssertFalse(monitorSource.contains("struct ActivityWindowMenuButton"))
        XCTAssertTrue(appSource.contains(
            ".keyboardShortcut(\"a\", modifiers: [.option, .command])"
        ))
        // Windows-menu + command hygiene, tightened by #4331: EVERY scene
        // except the main WindowGroup, the SEED WindowGroup and the Activity
        // monitor suppresses its automatic commands wholesale — SwiftUI
        // synthesizes NewItemCommands for each scene without it, and
        // demangling that keypath crashed on scenesDidChange. The exceptions
        // replace only `.newItem`: the two library groups with the real File
        // menu (a `.commandsRemoved()` seed scene dropped the whole File menu
        // whenever a restored window was key — Daniel 2026-08-13, "no file
        // menu?"), Activity with an empty group so it keeps its automatic
        // Windows-menu item + ⌥⌘A (#4524). Counted on TRIMMED lines so a
        // comment mentioning the modifier can never satisfy the pin.
        let sceneCount = appSource.components(separatedBy: "\n").filter {
            let line = $0.trimmingCharacters(in: .whitespaces)
            return line.hasPrefix("Window(\"") || line.hasPrefix("WindowGroup(\"")
        }.count
        let removedCount = appSource.components(separatedBy: "\n").filter {
            $0.trimmingCharacters(in: .whitespaces) == ".commandsRemoved()"
        }.count
        let newItemReplaced = appSource
            .components(separatedBy: "CommandGroup(replacing: .newItem)").count - 1
        XCTAssertEqual(
            removedCount, sceneCount - 3,
            "every scene but main, seed and Activity monitor removes its commands (#4331)"
        )
        XCTAssertEqual(
            newItemReplaced, 3,
            "the three surviving scenes replace the default new-item commands instead (#4331/#4524)"
        )
        // The replacements MERGE with one winner app-wide, so every one of
        // them must supply the SAME File menu — an empty `{}` replacement won
        // the merge and hid the File menu entirely (Daniel 2026-08-13/14,
        // "still no file menu"; regression source: the first #4331 fix).
        let fileMenuMounts = appSource
            .components(separatedBy: "FileMenuCommands()").count - 1
        XCTAssertEqual(
            fileMenuMounts, newItemReplaced,
            "every .newItem replacement supplies FileMenuCommands — an empty one hides the File menu app-wide"
        )
        // `Window`, not `WindowGroup` — see testActivityScenesAreSingletonWindowsNotGroups.
        XCTAssertTrue(appSource.contains(
            "Window(\"Activity\", id: ActivityWindowSelectionState.monitorWindowID)"
        ))
        XCTAssertTrue(appSource.contains(
            "Window(\"Activity Detail\", id: ActivityWindowSelectionState.detailWindowID)"
        ))
        XCTAssertTrue(monitorSource.contains("opensDetailWindow: true"))
        XCTAssertTrue(monitorSource.contains("Label(library.displayName"))
        XCTAssertTrue(detailSource.contains(".environment(library.documentStore)"))
        XCTAssertTrue(detailSource.contains("selectionState.selectedRun?.libraryId"))
        XCTAssertTrue(helpersSource.contains("@Environment(WorkflowExecutionStore.self)"))
        XCTAssertFalse(helpersSource.contains("@Environment(WorkflowExecutionObserver.self) private var executionObserver"))
        XCTAssertFalse(monitorSource.contains("ActivityDetailView(selectedRun: selectedRun)"))
        XCTAssertTrue(helpersSource.contains("openWindow(id: ActivityWindowSelectionState.detailWindowID)"))
        XCTAssertTrue(helpersSource.contains(".onTapGesture(count: 2)"))
    }

    /// The Activity scenes are `Window`, not `WindowGroup` — singleton by
    /// construction, not by convention.
    ///
    /// `WindowGroup` lets the user open unlimited copies and RESTORES every one
    /// of them at launch (five had accumulated in a real session). It also
    /// breaks `openWindow(id:)`, which targets a GROUP rather than an instance,
    /// so the Activity menu item raised whichever copy AppKit happened to pick
    /// instead of the one holding the selection — and the shared
    /// `ActivityWindowSelectionState` singleton only makes sense against
    /// exactly one monitor and one detail.
    ///
    /// Asserted both ways on purpose: the positive alone would still pass if a
    /// second `WindowGroup` declaration for the same id were added beside it.
    func testActivityScenesAreSingletonWindowsNotGroups() throws {
        let appSource = try Self.appSource("FicheroApp.swift")

        for id in ["ActivityWindowSelectionState.monitorWindowID",
                   "ActivityWindowSelectionState.detailWindowID"] {
            XCTAssertFalse(
                appSource.contains("WindowGroup(\"Activity\", id: \(id))"),
                "\(id) must not be a WindowGroup — the user could open unlimited copies"
            )
            XCTAssertFalse(
                appSource.contains("WindowGroup(\"Activity Detail\", id: \(id))"),
                "\(id) must not be a WindowGroup — the user could open unlimited copies"
            )
            // Exactly one scene claims each id; a second declaration is how a
            // singleton quietly stops being one.
            XCTAssertEqual(
                appSource.components(separatedBy: "id: \(id))").count - 1,
                1,
                "\(id) is claimed by more than one scene"
            )
        }
    }

    func testActivityWindowDoesNotRepeatTitleOrCenterEmptyPlaceholder() throws {
        let helpersSource = try Self.appSource("Views/Activity/ActivityViewHelpers.swift")

        XCTAssertFalse(helpersSource.contains("Text(\"Activity\")"))
        XCTAssertFalse(helpersSource.contains("ContentUnavailableView(\n                    \"No Runs Yet\""))
        XCTAssertTrue(helpersSource.contains("Text(\"No runs yet\")"))
    }

    func testActivityIsRemovedFromSidebarEntryPoints() throws {
        let viewMenuSource = try Self.appSource("App/Menus/ViewMenuCommands.swift")
        let pinnedRowsSource = try Self.appSource("Views/Sidebar/Sections/SidebarView+PinnedNavigationRows.swift")

        XCTAssertFalse(viewMenuSource.contains("mode: .activity"))
        // The mode bar itself was deleted (2026-08-10, Daniel: old UI
        // approach) — its absence IS the strongest "no activity entry point".
        let modeBarURL = try AppSource.root()
            .appendingPathComponent("Views/Sidebar/Modes/SidebarModeBar.swift")
        XCTAssertFalse(FileManager.default.fileExists(atPath: modeBarURL.path))
        XCTAssertFalse(pinnedRowsSource.contains("activityNavigationRow()"))
        XCTAssertFalse(pinnedRowsSource.contains("Activity Unavailable"))
    }
}
