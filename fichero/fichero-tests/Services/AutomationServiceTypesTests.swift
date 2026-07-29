@testable import Fichero
import XCTest

/// Tests for the Automation (Schedules + Triggers) DTO surface.
/// Locks every snake_case key the Python backend sends, the
/// schedule/trigger status icon/color maps, and the human-readable
/// description helpers rendered in the sidebar / detail views.
final class AutomationServiceTypesTests: XCTestCase {

    // MARK: - ScheduleConfigRequest / CreateScheduleRequest

    func testScheduleConfigRequestSnakeCase() throws {
        let req = ScheduleConfigRequest(
            scheduleType: "cron",
            cronExpression: "0 9 * * *",
            intervalSeconds: nil, runAt: nil,
            timezone: "UTC",
            startDate: "2026-05-11T00:00:00Z",
            endDate: nil, maxRuns: 10
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["schedule_type"] as? String, "cron")
        XCTAssertEqual(json?["cron_expression"] as? String, "0 9 * * *")
        XCTAssertEqual(json?["start_date"] as? String, "2026-05-11T00:00:00Z")
        XCTAssertEqual(json?["max_runs"] as? Int, 10)
    }

    func testCreateScheduleRequestSnakeCase() throws {
        let config = ScheduleConfigRequest(
            scheduleType: "interval", cronExpression: nil,
            intervalSeconds: 3600, runAt: nil, timezone: "UTC",
            startDate: nil, endDate: nil, maxRuns: nil
        )
        let req = CreateScheduleRequest(
            name: "Hourly", workflowId: "wf-1",
            config: config, inputs: [:],
            useBatch: false, batchItems: [],
            maxConcurrent: 1
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["workflow_id"] as? String, "wf-1")
        XCTAssertEqual(json?["use_batch"] as? Bool, false)
        XCTAssertEqual(json?["max_concurrent"] as? Int, 1)
        XCTAssertNotNil(json?["batch_items"])
    }

    // MARK: - TriggerConfigRequest / CreateTriggerRequest

    func testTriggerConfigRequestSnakeCase() throws {
        let req = TriggerConfigRequest(
            watchPath: "/tmp/watch", recursive: true,
            events: ["created", "modified"],
            filterMode: "extension", filterPattern: nil,
            filterExtensions: ["pdf", "md"],
            excludePatterns: [".DS_Store"],
            debounceSeconds: 0.5, batchDelaySeconds: 1.0
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["watch_path"] as? String, "/tmp/watch")
        XCTAssertEqual(json?["filter_mode"] as? String, "extension")
        XCTAssertEqual(json?["filter_extensions"] as? [String], ["pdf", "md"])
        XCTAssertEqual(json?["exclude_patterns"] as? [String], [".DS_Store"])
        XCTAssertEqual(json?["debounce_seconds"] as? Double, 0.5)
        XCTAssertEqual(json?["batch_delay_seconds"] as? Double, 1.0)
    }

    func testCreateTriggerRequestSnakeCase() throws {
        let config = TriggerConfigRequest(
            watchPath: "/x", recursive: false,
            events: ["created"],
            filterMode: "glob", filterPattern: "*.pdf",
            filterExtensions: [], excludePatterns: [],
            debounceSeconds: 0, batchDelaySeconds: 0
        )
        let req = CreateTriggerRequest(
            name: "PDF watcher", workflowId: "wf-1",
            config: config, inputsTemplate: ["key": "value"],
            useBatch: true, maxConcurrent: 4
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["workflow_id"] as? String, "wf-1")
        XCTAssertNotNil(json?["inputs_template"])
        XCTAssertEqual(json?["use_batch"] as? Bool, true)
        XCTAssertEqual(json?["max_concurrent"] as? Int, 4)
    }

    // MARK: - ScheduleInfo decode + status maps

    func testScheduleInfoDecodesSnakeCase() throws {
        let json = """
        {
            "schedule_id": "s-1", "name": "Daily",
            "workflow_id": "wf-1",
            "schedule_type": "cron",
            "cron_expression": "0 9 * * *",
            "interval_seconds": null,
            "run_at": null,
            "timezone": "UTC",
            "status": "active",
            "inputs": null,
            "use_batch": false,
            "batch_items": null,
            "max_concurrent": 1,
            "created_at": "2026-05-11T08:00:00Z",
            "updated_at": "2026-05-11T08:00:00Z",
            "last_run_at": null,
            "next_run_at": "2026-05-12T09:00:00Z",
            "run_count": 0,
            "error_message": null
        }
        """.data(using: .utf8)!
        let info = try JSONDecoder().decode(ScheduleInfo.self, from: json)
        XCTAssertEqual(info.id, "s-1")
        XCTAssertEqual(info.workflowId, "wf-1")
        XCTAssertEqual(info.cronExpression, "0 9 * * *")
        XCTAssertEqual(info.nextRunAt, "2026-05-12T09:00:00Z")
        XCTAssertEqual(info.runCount, 0)
    }

    func testScheduleStatusIconCoversAllCases() {
        let cases: [(String, String)] = [
            ("active", "play.circle.fill"),
            ("paused", "pause.circle.fill"),
            ("completed", "checkmark.circle.fill"),
            ("error", "exclamationmark.circle.fill"),
            ("garbage", "questionmark.circle")
        ]
        for (status, expected) in cases {
            XCTAssertEqual(makeSchedule(status: status).statusIcon, expected, "status=\(status)")
        }
    }

    func testScheduleStatusColorCoversAllCases() {
        let cases: [(String, String)] = [
            ("active", "green"),
            ("paused", "yellow"),
            ("completed", "gray"),
            ("error", "red"),
            ("garbage", "primary")
        ]
        for (status, expected) in cases {
            XCTAssertEqual(makeSchedule(status: status).statusColor, expected, "status=\(status)")
        }
    }

    // MARK: - scheduleDescription branches

    func testScheduleDescriptionCron() {
        let s = makeSchedule(scheduleType: "cron", cron: "0 9 * * *")
        XCTAssertEqual(s.scheduleDescription, "0 9 * * *")
    }

    func testScheduleDescriptionCronMissingExpression() {
        let s = makeSchedule(scheduleType: "cron", cron: nil)
        XCTAssertEqual(s.scheduleDescription, "No expression")
    }

    func testScheduleDescriptionIntervalSeconds() {
        let s = makeSchedule(scheduleType: "interval", interval: 30)
        XCTAssertEqual(s.scheduleDescription, "Every 30 seconds")
    }

    func testScheduleDescriptionIntervalMinutes() {
        let s = makeSchedule(scheduleType: "interval", interval: 120)
        XCTAssertEqual(s.scheduleDescription, "Every 2 minutes")
    }

    func testScheduleDescriptionIntervalHours() {
        let s = makeSchedule(scheduleType: "interval", interval: 7200)
        XCTAssertEqual(s.scheduleDescription, "Every 2 hours")
    }

    func testScheduleDescriptionIntervalMissing() {
        let s = makeSchedule(scheduleType: "interval", interval: nil)
        XCTAssertEqual(s.scheduleDescription, "Unknown interval")
    }

    func testScheduleDescriptionOnce() {
        let s = makeSchedule(scheduleType: "once", runAt: "2026-05-12T10:00:00Z")
        XCTAssertEqual(s.scheduleDescription, "2026-05-12T10:00:00Z")
    }

    func testScheduleDescriptionOnceMissingDate() {
        let s = makeSchedule(scheduleType: "once", runAt: nil)
        XCTAssertEqual(s.scheduleDescription, "No date set")
    }

    func testScheduleDescriptionUnknownType() {
        let s = makeSchedule(scheduleType: "weird")
        XCTAssertEqual(s.scheduleDescription, "weird")  // passthrough
    }

    // MARK: - ScheduleRunInfo

    func testScheduleRunInfoSnakeCase() throws {
        let json = """
        {
            "run_id": "r-1",
            "schedule_id": "s-1",
            "started_at": "2026-05-11T08:00:00Z",
            "completed_at": "2026-05-11T08:01:00Z",
            "status": "completed",
            "batch_id": "b-1",
            "error": null
        }
        """.data(using: .utf8)!
        let info = try JSONDecoder().decode(ScheduleRunInfo.self, from: json)
        XCTAssertEqual(info.id, "r-1")
        XCTAssertEqual(info.scheduleId, "s-1")
        XCTAssertEqual(info.batchId, "b-1")
    }

    // MARK: - TriggerInfo

    func testTriggerInfoDecodesSnakeCase() throws {
        let json = """
        {
            "trigger_id": "t-1",
            "name": "Watch Inbox",
            "workflow_id": "wf-1",
            "watch_path": "/Inbox",
            "recursive": true,
            "events": ["created"],
            "filter_mode": "extension",
            "filter_pattern": null,
            "filter_extensions": ["pdf"],
            "exclude_patterns": [],
            "debounce_seconds": 0.25,
            "batch_delay_seconds": 1.0,
            "inputs_template": null,
            "status": "active",
            "use_batch": false,
            "max_concurrent": 2,
            "created_at": "2026-05-11T00:00:00Z",
            "updated_at": "2026-05-11T00:00:00Z",
            "last_triggered_at": null,
            "trigger_count": 0,
            "error_message": null
        }
        """.data(using: .utf8)!
        let info = try JSONDecoder().decode(TriggerInfo.self, from: json)
        XCTAssertEqual(info.id, "t-1")
        XCTAssertEqual(info.watchPath, "/Inbox")
        XCTAssertEqual(info.filterExtensions, ["pdf"])
        XCTAssertEqual(info.debounceSeconds, 0.25)
        XCTAssertEqual(info.triggerCount, 0)
    }

    func testTriggerStatusIconAndColor() {
        let cases: [(String, String, String)] = [
            ("active", "eye.fill", "green"),
            ("paused", "pause.circle.fill", "yellow"),
            ("error", "exclamationmark.circle.fill", "red"),
            ("garbage", "questionmark.circle", "primary")
        ]
        for (status, icon, color) in cases {
            let t = makeTrigger(status: status)
            XCTAssertEqual(t.statusIcon, icon, "status=\(status)")
            XCTAssertEqual(t.statusColor, color, "status=\(status)")
        }
    }

    // MARK: - eventsDescription

    func testEventsDescriptionAnyShortCircuits() {
        let t = makeTrigger(events: ["any", "created"])
        XCTAssertEqual(t.eventsDescription, "All events")
    }

    func testEventsDescriptionJoins() {
        let t = makeTrigger(events: ["created", "modified"])
        XCTAssertEqual(t.eventsDescription, "created, modified")
    }

    // MARK: - filterDescription

    func testFilterDescriptionGlob() {
        let t = makeTrigger(filterMode: "glob", filterPattern: "*.pdf")
        XCTAssertEqual(t.filterDescription, "*.pdf")
    }

    func testFilterDescriptionGlobDefault() {
        let t = makeTrigger(filterMode: "glob", filterPattern: nil)
        XCTAssertEqual(t.filterDescription, "*.*")
    }

    func testFilterDescriptionRegex() {
        let t = makeTrigger(filterMode: "regex", filterPattern: "^doc-")
        XCTAssertEqual(t.filterDescription, "^doc-")
    }

    func testFilterDescriptionRegexDefault() {
        let t = makeTrigger(filterMode: "regex", filterPattern: nil)
        XCTAssertEqual(t.filterDescription, ".*")
    }

    func testFilterDescriptionExtensionList() {
        let t = makeTrigger(filterMode: "extension", filterExtensions: ["pdf", "md"])
        XCTAssertEqual(t.filterDescription, "pdf, md")
    }

    func testFilterDescriptionExtensionEmpty() {
        let t = makeTrigger(filterMode: "extension", filterExtensions: [])
        XCTAssertEqual(t.filterDescription, "All files")
    }

    func testFilterDescriptionUnknownPassthrough() {
        let t = makeTrigger(filterMode: "weird")
        XCTAssertEqual(t.filterDescription, "weird")
    }

    // MARK: - TriggerExecutionInfo

    func testTriggerExecutionInfoSnakeCase() throws {
        let json = """
        {
            "execution_id": "e-1",
            "trigger_id": "t-1",
            "triggered_at": "2026-05-11T08:00:00Z",
            "file_paths": ["/Inbox/a.pdf"],
            "batch_id": null,
            "status": "completed",
            "error": null,
            "completed_at": "2026-05-11T08:00:30Z"
        }
        """.data(using: .utf8)!
        let exec = try JSONDecoder().decode(TriggerExecutionInfo.self, from: json)
        XCTAssertEqual(exec.id, "e-1")
        XCTAssertEqual(exec.triggerId, "t-1")
        XCTAssertEqual(exec.filePaths, ["/Inbox/a.pdf"])
    }

    // MARK: - AutomationServiceError

    func testAutomationServiceErrorDescription() {
        XCTAssertEqual(
            AutomationServiceError.invalidInput("bad").errorDescription,
            "Invalid input: bad"
        )
    }

    // MARK: - Helpers

    private func makeSchedule(
        status: String = "active",
        scheduleType: String = "cron",
        cron: String? = "0 9 * * *",
        interval: Int? = nil,
        runAt: String? = nil
    ) -> ScheduleInfo {
        ScheduleInfo(
            scheduleId: "s", name: "n", workflowId: "wf",
            scheduleType: scheduleType, cronExpression: cron,
            intervalSeconds: interval, runAt: runAt,
            timezone: "UTC", status: status,
            inputs: nil, useBatch: false, batchItems: nil,
            maxConcurrent: 1,
            createdAt: "", updatedAt: "",
            lastRunAt: nil, nextRunAt: nil,
            runCount: 0, errorMessage: nil
        )
    }

    private func makeTrigger(
        status: String = "active",
        events: [String] = ["created"],
        filterMode: String = "glob",
        filterPattern: String? = "*.*",
        filterExtensions: [String] = []
    ) -> TriggerInfo {
        TriggerInfo(
            triggerId: "t", name: "n", workflowId: "wf",
            watchPath: "/", recursive: false,
            events: events,
            filterMode: filterMode, filterPattern: filterPattern,
            filterExtensions: filterExtensions, excludePatterns: [],
            debounceSeconds: 0, batchDelaySeconds: 0,
            inputsTemplate: nil, status: status,
            useBatch: false, maxConcurrent: 1,
            createdAt: "", updatedAt: "",
            lastTriggeredAt: nil, triggerCount: 0,
            errorMessage: nil
        )
    }
}
