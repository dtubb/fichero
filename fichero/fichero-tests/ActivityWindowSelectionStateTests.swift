@testable import Fichero
import XCTest

@MainActor
final class ActivityWindowSelectionStateTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
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
            isLive: true
        )

        state.select(run)

        XCTAssertEqual(state.selectedRun?.id, "run-1")
        XCTAssertEqual(state.selectedRun?.threadId, "thread-1")
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
        let appSource = try Self.appSource("FicheroApp.swift")
        let monitorSource = try Self.appSource("Views/Activity/ActivityMonitorWindow.swift")
        let helpersSource = try Self.appSource("Views/Activity/ActivityViewHelpers.swift")

        XCTAssertTrue(appSource.contains("ActivityWindowMenuButton()"))
        XCTAssertTrue(appSource.contains("WindowGroup(\"Activity\", id: ActivityWindowSelectionState.monitorWindowID)"))
        XCTAssertTrue(appSource.contains("WindowGroup(\"Activity Detail\", id: ActivityWindowSelectionState.detailWindowID)"))
        XCTAssertTrue(monitorSource.contains("opensDetailWindow: true"))
        XCTAssertFalse(monitorSource.contains("ActivityDetailView(selectedRun: selectedRun)"))
        XCTAssertTrue(helpersSource.contains("openWindow(id: ActivityWindowSelectionState.detailWindowID)"))
        XCTAssertTrue(helpersSource.contains(".onTapGesture(count: 2)"))
    }

    func testActivityWindowDoesNotRepeatTitleOrCenterEmptyPlaceholder() throws {
        let helpersSource = try Self.appSource("Views/Activity/ActivityViewHelpers.swift")

        XCTAssertFalse(helpersSource.contains("Text(\"Activity\")"))
        XCTAssertFalse(helpersSource.contains("ContentUnavailableView(\n                    \"No Runs Yet\""))
        XCTAssertTrue(helpersSource.contains("Text(\"No runs yet\")"))
    }

    func testActivityIsRemovedFromSidebarEntryPoints() throws {
        let viewMenuSource = try Self.appSource("Views/Menu/ViewMenuCommands.swift")
        let modeBarSource = try Self.appSource("Views/Sidebar/SidebarModeBar.swift")
        let pinnedRowsSource = try Self.appSource("Views/Sidebar/SidebarView+PinnedNavigationRows.swift")

        XCTAssertFalse(viewMenuSource.contains("mode: .activity"))
        XCTAssertFalse(modeBarSource.contains("modeIcon(.activity)"))
        XCTAssertFalse(modeBarSource.contains("modes.append(.activity)"))
        XCTAssertFalse(pinnedRowsSource.contains("activityNavigationRow()"))
        XCTAssertFalse(pinnedRowsSource.contains("Activity Unavailable"))
    }
}
