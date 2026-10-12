import FicheroAPIClient
import Foundation
@testable import Fichero
import Testing

/// The engine for these tests: it records each request and refuses it, so a test sees which route a verb reached
/// without decoding a reply. Only the transport is stubbed; the services and the generated client are the real ones.
private final class AutomationEngine: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var paths: [String] = []

    static func reset() {
        lock.lock()
        paths = []
        lock.unlock()
    }

    static func recorded() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return paths
    }

    override static func canInit(with request: URLRequest) -> Bool { request.url?.host == "automation.test" }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lock.lock()
        Self.paths.append("\(request.httpMethod ?? "") \(request.url?.path ?? "")")
        Self.lock.unlock()
        let response = HTTPURLResponse(url: request.url!, statusCode: 409, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"detail":"refused in the test"}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

/// #5712 (and #5652 slice 4): a schedule's, trigger's and batch's verbs were offered with no action behind them. Each
/// is now the engine's own action, offered by the row's state, one item in the row's menu and in Project ›
/// Workflows ▸. What breaks without these: a verb offered where it cannot act (Resume on a running schedule, Cancel
/// on a finished batch), or a press that reaches the wrong route.
@MainActor
@Suite("An automation row's verbs (#5712)", .serialized)
struct AutomationVerbsMenuTests {
    private func schedule(_ status: String) -> SidebarItem.ItemType {
        .schedule(ScheduleInfo(
            scheduleId: "s-1", name: "Daily", workflowId: "wf", scheduleType: "cron", cronExpression: "0 9 * * *",
            intervalSeconds: nil, runAt: nil, timezone: "UTC", status: status, inputs: nil, useBatch: false,
            batchItems: nil, maxConcurrent: 1, createdAt: "", updatedAt: "", lastRunAt: nil, nextRunAt: nil,
            runCount: 0, errorMessage: nil
        ))
    }

    private func trigger(_ status: String) -> SidebarItem.ItemType {
        .trigger(TriggerInfo(
            triggerId: "t-1", name: "Watch Inbox", workflowId: "wf", watchPath: "/", recursive: false,
            events: ["created"], filterMode: "glob", filterPattern: nil, filterExtensions: [], excludePatterns: [],
            debounceSeconds: 0, batchDelaySeconds: 0, inputsTemplate: nil, status: status, useBatch: false,
            maxConcurrent: 1, createdAt: "", updatedAt: "", lastTriggeredAt: nil, triggerCount: 0, errorMessage: nil
        ))
    }

    private func batch(_ status: String) -> SidebarItem.ItemType {
        .batch(BatchInfo(
            batchId: "b-1", workflowId: "wf", status: status, totalItems: 10, completedItems: 2, failedItems: 0,
            maxConcurrent: 1, createdAt: "", startedAt: nil, completedAt: nil, errorMessage: nil, items: nil
        ))
    }

    private func services() -> (AutomationAPIService, BatchService) {
        AutomationEngine.reset()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AutomationEngine.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://automation.test")!, libraryPath: "/tmp/automation.fichero",
            session: URLSession(configuration: configuration)
        )
        return (AutomationAPIService(ficheroClient: client), BatchService(ficheroClient: client))
    }

    @Test("each row offers what its state allows")
    func offeredByState() {
        #expect(AutomationVerbs.offered(for: schedule("active")) == [.pause, .runNow])
        #expect(AutomationVerbs.offered(for: schedule("paused")) == [.resume])
        #expect(AutomationVerbs.offered(for: trigger("active")) == [.pause])
        #expect(AutomationVerbs.offered(for: trigger("paused")) == [.resume])
        #expect(AutomationVerbs.offered(for: batch("running")) == [.pause, .cancel])
        #expect(AutomationVerbs.offered(for: batch("paused")) == [.resume, .cancel])
        #expect(AutomationVerbs.offered(for: batch("completed")).isEmpty)
        #expect(AutomationVerbs.offered(for: .document(Document(id: "p1", name: "0970.jpg"))).isEmpty)
    }

    @Test("the menu bar says why a verb cannot act")
    func reasons() {
        #expect(AutomationVerbs.reason(.pause, nil) == "Select a schedule, trigger or batch in the sidebar")
        let paused = AutomationVerbsTarget(rowId: "schedule:s-1", kind: "schedule", offered: [.resume]) { _ in }
        #expect(AutomationVerbs.reason(.resume, paused) == nil)
        #expect(AutomationVerbs.reason(.pause, paused) == "This schedule cannot pause now")
    }

    @Test("each verb reaches the engine's own route for its row")
    func routes() async {
        let (automation, batches) = services()
        let presses: [(AutomationVerb, SidebarItem.ItemType)] = [
            (.pause, schedule("active")), (.resume, schedule("paused")), (.runNow, schedule("active")),
            (.pause, trigger("active")), (.resume, trigger("paused")),
            (.pause, batch("running")), (.resume, batch("paused")), (.cancel, batch("running")),
        ]
        for (verb, row) in presses {
            await #expect(throws: (any Error).self, "the stub refuses every press") {
                try await AutomationVerbs.perform(verb, on: row, automation: automation, batches: batches)
            }
        }
        #expect(AutomationEngine.recorded() == [
            "POST /api/schedules/s-1/pause", "POST /api/schedules/s-1/resume", "POST /api/schedules/s-1/trigger",
            "POST /api/triggers/t-1/pause", "POST /api/triggers/t-1/resume",
            "POST /api/batches/b-1/pause", "POST /api/batches/b-1/resume", "POST /api/batches/b-1/cancel",
        ])
    }

    /// The sidebar's list and rename reach the engine too (#5712): the service used to answer with nothing, so no
    /// schedule or trigger was ever listed.
    @Test("the sidebar's list and rename go through the project's generated client")
    func listAndRenameReachTheEngine() async {
        let (automation, _) = services()
        await #expect(throws: (any Error).self) { _ = try await automation.listSchedules(limit: 100) }
        await #expect(throws: (any Error).self) { _ = try await automation.listTriggers(limit: 100) }
        await #expect(throws: AutomationAPIServiceError.self) {
            try await automation.updateSchedule(scheduleId: "s-1", newName: "Weekly")
        }
        await #expect(throws: AutomationAPIServiceError.self) {
            try await automation.updateTrigger(triggerId: "t-1", newName: "Watch Letters")
        }
        #expect(AutomationEngine.recorded() == [
            "GET /api/schedules", "GET /api/triggers", "PUT /api/schedules/s-1", "PUT /api/triggers/t-1",
        ])
    }

    @Test("a verb the row does not have is refused before any request")
    func notOffered() async {
        let (automation, batches) = services()
        await #expect(throws: AutomationVerbError.notOffered(.runNow)) {
            try await AutomationVerbs.perform(.runNow, on: trigger("active"), automation: automation, batches: batches)
        }
        #expect(AutomationEngine.recorded().isEmpty)
    }

    @Test("a press reaches the row's own action")
    func pressReachesTheRow() {
        var pressed: [AutomationVerb] = []
        let target = AutomationVerbsTarget(rowId: "batch:b-1", kind: "batch", offered: [.pause, .cancel]) {
            pressed.append($0)
        }
        target.perform(.cancel)
        #expect(pressed == [.cancel])
        #expect(AutomationVerb.cancel.title == "Cancel Batch")
    }
}
