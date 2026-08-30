@testable import Fichero
import Foundation
import XCTest

/// Tests for SidebarItem+MoreFactories — factory methods for chain /
/// comparison / schedule / trigger / batch / activityRun sidebar items.
/// Locks the id-prefix scheme (memory entry #144) + per-kind defaults.
final class SidebarItemMoreFactoriesTests: XCTestCase {

    private let libId = UUID()

    // MARK: - fromChain

    func testFromChainIdPrefix() {
        let chain = WorkflowChain(id: "c-1", name: "My Chain")
        let item = SidebarItem.fromChain(chain, libraryId: libId)
        XCTAssertEqual(item.id, "chain:c-1")
        XCTAssertEqual(item.name, "My Chain")
        XCTAssertEqual(item.icon, "link")
        XCTAssertEqual(item.category, .workflow)
        XCTAssertFalse(item.isFolder)
        XCTAssertEqual(item.folderPath, "/")
    }

    // MARK: - fromComparison

    func testFromComparisonShortPromptName() {
        let comp = ComparisonSummary(
            prompt: "Short prompt", modelsCompared: [],
            totalCostUsd: 0, comparisonId: "comp-1", timestamp: "t"
        )
        let item = SidebarItem.fromComparison(comp, libraryId: libId)
        XCTAssertEqual(item.id, "comparison:comp-1")
        XCTAssertEqual(item.name, "Short prompt")
        XCTAssertEqual(item.icon, "arrow.left.arrow.right")
        XCTAssertEqual(item.category, .chat)
    }

    func testFromComparisonTruncatesLongPrompt() {
        let long = String(repeating: "x", count: 80)
        let comp = ComparisonSummary(
            prompt: long, modelsCompared: [],
            totalCostUsd: 0, comparisonId: "c", timestamp: "t"
        )
        let item = SidebarItem.fromComparison(comp, libraryId: libId)
        // First 40 chars + "..."
        XCTAssertEqual(item.name, String(repeating: "x", count: 40) + "...")
    }

    // MARK: - fromSchedule

    func testFromScheduleUsesStatusIcon() {
        let schedule = ScheduleInfo(
            scheduleId: "s-1", name: "Daily",
            workflowId: "wf", scheduleType: "cron",
            cronExpression: "0 9 * * *",
            intervalSeconds: nil, runAt: nil,
            timezone: "UTC", status: "active",
            inputs: nil, useBatch: false, batchItems: nil,
            maxConcurrent: 1,
            createdAt: "", updatedAt: "",
            lastRunAt: nil, nextRunAt: nil,
            runCount: 0, errorMessage: nil
        )
        let item = SidebarItem.fromSchedule(schedule, libraryId: libId)
        XCTAssertEqual(item.id, "schedule:s-1")
        XCTAssertEqual(item.icon, "play.circle.fill")  // active → play
        XCTAssertEqual(item.category, .automation)
    }

    // MARK: - fromTrigger

    func testFromTriggerIdPrefix() {
        let trigger = TriggerInfo(
            triggerId: "t-1", name: "Watch Inbox", workflowId: "wf",
            watchPath: "/", recursive: false,
            events: ["created"], filterMode: "glob",
            filterPattern: nil, filterExtensions: [],
            excludePatterns: [], debounceSeconds: 0,
            batchDelaySeconds: 0, inputsTemplate: nil,
            status: "active", useBatch: false,
            maxConcurrent: 1, createdAt: "", updatedAt: "",
            lastTriggeredAt: nil, triggerCount: 0,
            errorMessage: nil
        )
        let item = SidebarItem.fromTrigger(trigger, libraryId: libId)
        XCTAssertEqual(item.id, "trigger:t-1")
        XCTAssertEqual(item.icon, "eye.fill")  // active → eye.fill from TriggerInfo
        XCTAssertEqual(item.category, .automation)
    }

    // MARK: - fromBatch

    func testFromBatchProgressFraction() {
        let batch = BatchInfo(
            batchId: "b-1", workflowId: "wf", status: "running",
            totalItems: 100, completedItems: 25, failedItems: 0,
            maxConcurrent: 1, createdAt: "", startedAt: nil,
            completedAt: nil, errorMessage: nil, items: nil
        )
        let item = SidebarItem.fromBatch(batch, libraryId: libId)
        XCTAssertEqual(item.id, "batch:b-1")
        XCTAssertEqual(item.progress, 0.25)
        XCTAssertTrue(item.showProgress)  // running → show progress
        XCTAssertEqual(item.icon, "play.circle.fill")
    }

    func testFromBatchZeroTotalGuardsAgainstNaN() {
        let batch = BatchInfo(
            batchId: "b-2", workflowId: "wf", status: "pending",
            totalItems: 0, completedItems: 0, failedItems: 0,
            maxConcurrent: 1, createdAt: "", startedAt: nil,
            completedAt: nil, errorMessage: nil, items: nil
        )
        let item = SidebarItem.fromBatch(batch, libraryId: libId)
        XCTAssertEqual(item.progress, 0)  // explicit 0 not NaN
        XCTAssertFalse(item.showProgress)  // pending != running
        XCTAssertEqual(item.icon, "checkmark.circle")  // not "running" → checkmark
    }

    // MARK: - fromActivityRun

    func testFromActivityRunProgressOnRunning() {
        let activity = ActivityItem(
            id: "a-1", type: "workflow_started",
            level: "info", timestamp: "2026-05-11T08:00:00Z",
            message: "Run started"
        )
        let item = SidebarItem.fromActivityRun(activity, libraryId: libId)
        XCTAssertEqual(item.id, "activity:a-1")
        // activity.status is computed from type — "workflow_started" → "running"
        XCTAssertTrue(item.showProgress)
        XCTAssertEqual(item.category, .activity)
    }

    // MARK: - supportsSidebarReorder

    /// Only kinds `handleUnifiedRowsMove` dispatches allow reorder drag; the
    /// rest disable it so they don't show a snap-back insertion indicator.
    func testSupportsSidebarReorderMatchesHandledKinds() {
        // Reorderable: workflows / chains (documents / folders / searches
        // covered in SidebarItemTests).
        XCTAssertTrue(SidebarItem.fromChain(WorkflowChain(id: "c-1", name: "C"), libraryId: libId)
            .supportsSidebarReorder)

        // Non-reorderable: schedule, trigger, batch, comparison, activityRun.
        let schedule = ScheduleInfo(
            scheduleId: "s-1", name: "Daily", workflowId: "wf", scheduleType: "cron",
            cronExpression: "0 9 * * *", intervalSeconds: nil, runAt: nil, timezone: "UTC",
            status: "active", inputs: nil, useBatch: false, batchItems: nil, maxConcurrent: 1,
            createdAt: "", updatedAt: "", lastRunAt: nil, nextRunAt: nil, runCount: 0, errorMessage: nil
        )
        XCTAssertFalse(SidebarItem.fromSchedule(schedule, libraryId: libId).supportsSidebarReorder)

        let batch = BatchInfo(
            batchId: "b-1", workflowId: "wf", status: "running", totalItems: 1, completedItems: 0,
            failedItems: 0, maxConcurrent: 1, createdAt: "", startedAt: nil, completedAt: nil,
            errorMessage: nil, items: nil
        )
        XCTAssertFalse(SidebarItem.fromBatch(batch, libraryId: libId).supportsSidebarReorder)
    }
}
