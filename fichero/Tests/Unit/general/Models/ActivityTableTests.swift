//
//  ActivityTableTests.swift
//  FicheroTests
//
//  #5415: the Activity window is a table of runs with disclosure triangles
//  (run → step → page), its columns the measures that matter, sortable, with
//  Pause and Stop on a row and a failed row's reason shown; it updates ONE row
//  in place from the change stream. The toolbar popover is a summary.
//
//  Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md,
//  `activity.window.table`, `activity.window.expand`, `activity.window.working-on`,
//  `activity.window.cost`, `activity.window.measures`,
//  `activity.window.row-shows-lane-state-reason`, `activity.window.grouped-by-project`,
//  `activity.popover.summary`. Written from those lines, not from the code.
//
//  Through the real `ActivityStore`, its real `ActivityService` and the
//  generated client's real decoding: only the transport is stubbed. The run
//  tree below was recorded from the engine's own route on 2026-10-04
//  (`GET /api/activity/jobs/{run}` after a real entity-extraction run whose
//  model refused one letter, the run in `fichero-server/tests/unit/jobs/
//  test_run_tree_rolls_up.py`), so its shape is the engine's, not a guess.
//
//  Not covered: a real window drawing the table (no mounted-view harness in
//  this target); the rows it would draw are built here by the same functions.
//

// swiftlint:disable file_length
// One suite per spec slice (#5415), with the recorded engine fixtures beside
// the tests that read them.

@testable import Fichero
import FicheroAPIClient
import XCTest

@MainActor
// swiftlint:disable:next type_body_length
final class ActivityTableTests: XCTestCase {

    // MARK: - Mock transport (copied, not shared: ActivityStoreRunsTests' pattern)

    private struct Stub {
        let pathContains: String
        let method: String
        let status: Int
        let body: Data
    }

    private final class MockTransportURLProtocol: URLProtocol {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var stubs: [Stub] = []
        nonisolated(unsafe) private static var requests: [URLRequest] = []

        static func reset(_ stubs: [Stub]) {
            lock.lock()
            self.stubs = stubs
            requests = []
            lock.unlock()
        }

        static func recorded() -> [URLRequest] {
            lock.lock()
            defer { lock.unlock() }
            return requests
        }

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.host == "127.0.0.1" && request.url?.path.hasPrefix("/api/") == true
        }

        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest {
            request
        }

        override func startLoading() {
            let path = request.url?.path ?? ""
            let method = request.httpMethod ?? ""
            Self.lock.lock()
            Self.requests.append(request)
            let stub = Self.stubs.first {
                !$0.pathContains.isEmpty && path.hasSuffix($0.pathContains) && $0.method == method
            }
            Self.lock.unlock()

            let resolved = stub ?? Stub(pathContains: "", method: "", status: 404, body: Data(#"{"detail":"no stub"}"#.utf8))
            guard let url = request.url,
                  let response = HTTPURLResponse(
                      url: url,
                      statusCode: resolved.status,
                      httpVersion: "HTTP/1.1",
                      headerFields: ["Content-Type": "application/json"]
                  ) else {
                client?.urlProtocol(self, didFailWithError: URLError(.badURL))
                return
            }
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: resolved.body)
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}
    }

    override func setUp() {
        super.setUp()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        MockTransportURLProtocol.reset([])
    }

    private static func storeWithMockTransport() -> ActivityStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ActivityTableTests.fichero",
            session: session
        )
        return ActivityStore(service: ActivityService(ficheroClient: client))
    }

    // MARK: - Fixtures

    private static let runId = "thread-1fa195a132b2"
    private static let libraryId = UUID(uuidString: "33333333-3333-3333-3333-333333333333")!

    /// Recorded from `GET /api/activity/jobs/{run}` (see the header). `state`
    /// of the Entities step and of the run are parameters so a test can show
    /// the same run while it is still running.
    private static func treeJSON(
        id: String = runId,
        runState: String = "failed",
        stepState: String = "running",
        failedPageReason: String = "the provider refused this letter",
        runCost: Double = 0.0022500000000000003
    ) -> Data {
        Data("""
        {
          "id": "\(id)", "kind": "workflow", "name": "Workflow run", "subject": "\(id)",
          "model": null, "state": "\(runState)",
          "reason": "Step 'Entities' failed: the provider refused this letter",
          "parent_id": null, "done": 1, "total": 2, "failed": 1, "seconds": 0.187989,
          "tokens": 1100, "cost_usd": \(runCost), "unpriced_models": [],
          "children": [
            {
              "id": "\(id):Files", "kind": "workflow-step", "name": "Step", "subject": "\(id):Files",
              "model": null, "state": "done", "reason": null, "parent_id": "\(id)",
              "done": 0, "total": 0, "failed": 0, "seconds": 0.049228, "tokens": 0,
              "cost_usd": null, "unpriced_models": [], "children": []
            },
            {
              "id": "\(id):Entities", "kind": "workflow-step", "name": "Step", "subject": "\(id):Entities",
              "model": null, "state": "\(stepState)", "reason": null, "parent_id": "\(id)",
              "done": 1, "total": 2, "failed": 1, "seconds": 0.129743, "tokens": 1100,
              "cost_usd": 0.0022500000000000003, "unpriced_models": [],
              "children": [
                {
                  "id": "9098cf58-c175-4e14-8568-0c64b0940578", "kind": "ask-a-model", "name": "ask-a-model",
                  "subject": "Entities", "model": "openai:gpt-5", "state": "done", "reason": null,
                  "parent_id": "\(id):Entities", "done": 1, "total": 1, "failed": 0, "seconds": 0.003531,
                  "tokens": 1100, "cost_usd": 0.0022500000000000003, "unpriced_models": [], "children": []
                },
                {
                  "id": "e3a1c445-72a4-4bb7-8135-05dacc6ca483", "kind": "ask-a-model", "name": "ask-a-model",
                  "subject": "Entities", "model": "openai:gpt-5", "state": "failed",
                  "reason": "\(failedPageReason)",
                  "parent_id": "\(id):Entities", "done": 0, "total": 1, "failed": 1, "seconds": 0.001541,
                  "tokens": 0, "cost_usd": null, "unpriced_models": [], "children": []
                }
              ]
            }
          ]
        }
        """.utf8)
    }

    private static func run(
        threadId: String = runId,
        status: ActivityRunStatus = .failed,
        started: Date? = Date(timeIntervalSince1970: 1_790_000_000),
        failureReason: String? = "Step 'Entities' failed: the provider refused this letter",
        library: UUID = libraryId,
        libraryName: String = "Marshall Diaries"
    ) -> ActivityRun {
        ActivityRun(
            id: "\(library.uuidString)|\(threadId)",
            runId: threadId,
            workflowId: "wf-entities",
            threadId: threadId,
            workflowName: "Entities",
            timestamp: started,
            status: status,
            progress: nil,
            currentStep: nil,
            errorCount: failureReason == nil ? 0 : 1,
            fileCount: 2,
            isLive: false,
            libraryId: library,
            libraryName: libraryName,
            failureReason: failureReason
        )
    }

    private func loadedTree(_ store: ActivityStore, _ threadId: String = runId) async throws -> ActivityJobNode {
        await store.loadRunTree(threadId: threadId)
        return try XCTUnwrap(store.runTrees[threadId], "the store holds the run's tree after loading it")
    }

    // MARK: - activity.window.expand: run → step → page, from the engine's tree

    func testActivityWindowExpand_aRunRowOpensIntoItsStepsAndTheirPages() async throws {
        // WHY: the spec's row "expands, with a disclosure triangle, into its
        // children": the window used to be a flat list with nothing under a run.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/\(Self.runId)", method: "GET", status: 200, body: Self.treeJSON())
        ])

        let row = ActivityMonitorRow.run(Self.run(), tree: try await loadedTree(store))

        let steps = try XCTUnwrap(row.children, "a run with a tree has a disclosure triangle")
        XCTAssertEqual(steps.map(\.name), ["Files", "Entities"], "steps are named as the person named them, not by run id")
        XCTAssertEqual(steps.map(\.kind), [.step, .step])
        XCTAssertNil(steps[0].children, "a step that handed nothing to a lane is a leaf")
        let pages = try XCTUnwrap(steps[1].children)
        XCTAssertEqual(pages.count, 2)
        XCTAssertEqual(pages.map(\.kind), [.page, .page])
        XCTAssertEqual(Set(([row] + steps + pages).map(\.id)).count, 5, "every row of the tree has its own id")
    }

    func testActivityWindowExpand_aRunTheEngineHasNoTreeForStillHasItsRowAndIsNotAskedAgain() async {
        // WHY: runs recorded before the jobs table have no tree (404); the row
        // must still show, and the window must not ask on every redraw.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([])  // every route answers 404

        await store.loadRunTree(threadId: "old-run")
        await store.loadRunTree(threadId: "old-run")

        XCTAssertNil(store.runTrees["old-run"])
        XCTAssertEqual(MockTransportURLProtocol.recorded().count, 1, "a run with no tree is asked once")
        let row = ActivityMonitorRow.run(Self.run(threadId: "old-run"), tree: nil)
        XCTAssertNil(row.children, "no tree, no disclosure triangle")
        XCTAssertEqual(row.name, "Entities")
    }

    // MARK: - activity.window.measures / activity.window.cost

    func testActivityWindowMeasures_theColumnsCarryTimeCostErrorsAndModelRolledUp() async throws {
        // WHY: "the measures that matter, per run, step and page, rolled up the
        // tree, are the table's main columns"; cost is null unless every call
        // under it is priced, and must never read as zero.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/\(Self.runId)", method: "GET", status: 200, body: Self.treeJSON())
        ])
        let row = ActivityMonitorRow.run(Self.run(), tree: try await loadedTree(store))

        XCTAssertEqual(row.costUsd ?? 0, 0.00225, accuracy: 1e-9, "the run's cost is the engine's roll-up")
        XCTAssertEqual(row.costText, "$0.00225")
        XCTAssertEqual(row.seconds ?? 0, 0.187989, accuracy: 1e-6)
        XCTAssertEqual(row.errors, 1, "the failed page counts on its run")
        XCTAssertEqual(row.model, "openai:gpt-5", "a run shows the model its pages used")
        XCTAssertEqual(row.progressText, "1 of 2")

        let failedPage = try XCTUnwrap(row.children?[1].children?.first { $0.phase == .failed })
        XCTAssertNil(failedPage.costUsd)
        XCTAssertEqual(failedPage.costText, "", "a call that used no tokens has no cost, never \"$0\"")
        let filesStep = try XCTUnwrap(row.children?.first)
        XCTAssertEqual(filesStep.costText, "", "a step with no model calls shows no cost")
    }

    // MARK: - activity.window.row-shows-lane-state-reason

    func testActivityWindowRowShowsReason_aFailedRowSaysWhy() async throws {
        // WHY: a failure that reads as silent is what made the maintainer re-run
        // Kraken three times; the spec puts the reason on the failed row itself.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/\(Self.runId)", method: "GET", status: 200, body: Self.treeJSON())
        ])
        let row = ActivityMonitorRow.run(Self.run(), tree: try await loadedTree(store))

        XCTAssertEqual(row.stateText, "Failed: Step 'Entities' failed: the provider refused this letter")
        let failedPage = try XCTUnwrap(row.children?[1].children?.first { $0.phase == .failed })
        XCTAssertEqual(failedPage.stateText, "Failed: the provider refused this letter")
    }

    func testActivityWindowRowShowsReason_aWaitingJobSaysWhatItWaitsFor() {
        // WHY: "while it waits, why": a queued job held by the throttle names
        // the throttle's reason, not just "Waiting".
        let job = ActivityJob(id: "kraken", taskType: "kraken-page", name: "Kraken pages", total: 12,
                              state: .waiting, reason: "Waiting: memory is tight")
        let row = ActivityMonitorRow.job(job, libraryId: Self.libraryId, projectName: "Marshall Diaries")
        XCTAssertEqual(row.stateText, "Waiting: memory is tight")
        XCTAssertEqual(row.progressText, "0 of 12")
    }

    // MARK: - activity.window.working-on

    func testActivityWindowWorkingOn_aRunningRowSaysWhatItIsOnAndHowLongRemains() async throws {
        // WHY: "a running row says what it is working on now and how long
        // remains"; the engine's tree names the running step.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/\(Self.runId)", method: "GET", status: 200,
                 body: Self.treeJSON(runState: "running"))
        ])
        let row = ActivityMonitorRow.run(
            Self.run(status: .running, failureReason: nil),
            tree: try await loadedTree(store)
        )

        XCTAssertEqual(row.stateText, "Running: Entities")
        // One of two pages done in 0.19 s: about 0.19 s more at that pace.
        XCTAssertEqual(row.remainingSeconds ?? 0, 0.187989, accuracy: 1e-6)
        XCTAssertTrue(row.progressText.hasPrefix("1 of 2, "), row.progressText)
        XCTAssertTrue(row.progressText.hasSuffix(" left"), row.progressText)
        XCTAssertEqual(row.controls, [.pause, .stop], "a running row offers Pause and Stop")
    }

    // MARK: - One row updated in place, from the change stream

    func testActivityWindowTable_aChangeEventRereadsOnlyItsOwnRunsTree() async throws {
        // WHY: the table "updates one row in place (no wholesale re-render),
        // driven by the engine's change stream": an event naming one run must
        // re-read that run's tree and leave every other row's value untouched.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/run-a", method: "GET", status: 200,
                 body: Self.treeJSON(id: "run-a", runState: "running", runCost: 0.001)),
            Stub(pathContains: "/api/activity/jobs/run-b", method: "GET", status: 200,
                 body: Self.treeJSON(id: "run-b", runState: "done"))
        ])
        _ = try await loadedTree(store, "run-a")
        let untouched = try await loadedTree(store, "run-b")
        let tokenBefore = store.refreshToken

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/run-a", method: "GET", status: 200,
                 body: Self.treeJSON(id: "run-a", runState: "running", runCost: 0.004))
        ])
        store.applyActivityEvent(ActivityItem(
            id: "act-1", type: "node_completed", level: "info",
            timestamp: "2026-10-04T12:00:00Z", message: "Entities done", threadId: "run-a"
        ))

        let deadline = Date().addingTimeInterval(3)
        while store.runTrees["run-a"]?.costUsd != 0.004, Date() < deadline {
            try await Task.sleep(for: .milliseconds(50))
        }
        XCTAssertEqual(store.runTrees["run-a"]?.costUsd, 0.004, "the named run's row now shows the new cost")
        XCTAssertEqual(store.runTrees["run-b"], untouched, "the other run's row is the same value")
        let paths = MockTransportURLProtocol.recorded().compactMap(\.url?.path)
        XCTAssertEqual(paths, ["/api/activity/jobs/run-a"], "one read, of the named run's tree only")
        // The run frame's own debounced `refreshToken` bump (the existing run
        // list patch, `activityEventsRouteThroughTheDebouncer`) still fires once
        // for the burst; the tree read adds none of its own.
        XCTAssertLessThanOrEqual(store.refreshToken, tokenBefore + 1)
    }

    // MARK: - Pause and Stop on a row (activity.pause.per-job)

    func testActivityWindowTable_pauseOnAStepRowSetsThatOneRowsState() async throws {
        // WHY: "Pause and Stop go on a row", through the one audited job route,
        // and the answer lands on that row in place.
        let store = Self.storeWithMockTransport()
        let stepId = "\(Self.runId):Entities"
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/\(Self.runId)", method: "GET", status: 200,
                 body: Self.treeJSON(runState: "running")),
            Stub(pathContains: "/api/activity/jobs/\(stepId)/paused", method: "PUT", status: 200,
                 body: Data(#"{"id":"\#(stepId)","state":"paused"}"#.utf8))
        ])
        let before = try await loadedTree(store)

        let failure = await store.setJobPaused(jobId: stepId, paused: true, runThreadId: Self.runId)

        XCTAssertNil(failure)
        let request = try XCTUnwrap(MockTransportURLProtocol.recorded().last)
        XCTAssertEqual(request.httpMethod, "PUT")
        let after = try XCTUnwrap(store.runTrees[Self.runId])
        XCTAssertEqual(after.children[1].state, "paused")
        XCTAssertEqual(after.children[0], before.children[0], "the sibling step is untouched")
        let row = ActivityMonitorRow.run(Self.run(status: .running, failureReason: nil), tree: after)
        XCTAssertEqual(row.children?[1].controls, [.resume, .stop], "a paused row offers Resume and Stop")
        XCTAssertEqual(row.children?[0].controls, [], "a finished row offers nothing")
    }

    // MARK: - Sortable columns

    func testActivityWindowTable_rowsSortByAColumnAndTheirChildrenToo() {
        // WHY: the columns are "sortable"; a sort must order every level, or the
        // pages under a step stay in arrival order while the runs move.
        func row(_ id: String, cost: Double?, started: TimeInterval, children: [ActivityMonitorRow]? = nil,
                 phase: ActivityMonitorRow.Phase = .done) -> ActivityMonitorRow {
            ActivityMonitorRow(
                id: id, kind: children == nil ? .page : .run, libraryId: nil, runRowID: nil, runThreadId: nil,
                jobId: id, name: id, projectName: nil, phase: phase, reason: nil, workingOn: nil,
                done: 0, total: 0, started: Date(timeIntervalSince1970: started), seconds: nil,
                costUsd: cost, tokens: 0, errors: 0, model: nil, isLive: false, children: children
            )
        }
        let cheapRun = row("cheap", cost: 0.01, started: 300, children: [
            row("p-low", cost: 0.001, started: 1), row("p-high", cost: 0.009, started: 2)
        ])
        let dearRun = row("dear", cost: 0.50, started: 100)
        let unpriced = row("unpriced", cost: nil, started: 200)
        let running = row("running", cost: nil, started: 50, phase: .running)

        let byCost = ActivityMonitorRow.sorted(
            [cheapRun, unpriced, dearRun], using: [KeyPathComparator(\.costKey, order: .reverse)]
        )
        XCTAssertEqual(byCost.map(\.id), ["dear", "cheap", "unpriced"], "unpriced sorts below any price")
        XCTAssertEqual(byCost[1].children?.map(\.id), ["p-high", "p-low"])

        let byDefault = ActivityMonitorRow.sorted([cheapRun, dearRun, running, unpriced], using: ActivityMonitorRow.defaultSort)
        XCTAssertEqual(byDefault.map(\.id), ["running", "cheap", "unpriced", "dear"],
                       "what is working now first, then the newest")
    }

    // MARK: - activity.window.table: every job of its own is a row too

    func testActivityWindowTable_aJobOfItsOwnIsARowAndAPageOfARunIsNot() async throws {
        // WHY: "a table of every job of every kind": the jobs read carries queued
        // work beside runs; a page already under its run must not appear twice.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsJSON())
        ])
        await store.refreshBackgroundJobs()
        XCTAssertTrue(store.backgroundJobs.contains { $0.parentId != nil }, "the read does carry a run's page")

        let group = ActivityMonitorRow.group(
            libraryId: Self.libraryId, libraryName: "Marshall Diaries", isMac: false,
            runRows: [.run(Self.run(threadId: "run-1"), tree: nil)], jobs: store.backgroundJobs
        )

        XCTAssertEqual(group.rows.filter { $0.kind == .run }.map(\.name), ["Entities"])
        XCTAssertEqual(group.rows.filter { $0.kind == .job }.map(\.name).sorted(),
                       ["Embedding", "Kraken pages", "Read a page"],
                       "queued work is a row; a run's page and the runs the read also lists are not")
    }

    // MARK: - activity.window.grouped-by-project

    func testActivityWindowGroupedByProject_eachLibraryIsAGroupAndTheGlobalOneIsTheMacs() async throws {
        // WHY: "the window can group its rows by project; the Mac's own work is a
        // group of its own", with each group's run keeping its tree under it.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/\(Self.runId)", method: "GET", status: 200, body: Self.treeJSON())
        ])
        let tree = try await loadedTree(store)
        let macId = UUID(uuidString: "44444444-4444-4444-4444-444444444444")!

        let project = ActivityMonitorRow.group(
            libraryId: Self.libraryId, libraryName: "Marshall Diaries", isMac: false,
            runRows: [.run(Self.run(), tree: store.runTrees[Self.runId])], jobs: []
        )
        let mac = ActivityMonitorRow.group(
            libraryId: macId, libraryName: "Global", isMac: true, runRows: [],
            jobs: [ActivityJob(id: "dl", taskType: "model-download", name: "Downloading a model",
                                           current: 3, total: 10)]
        )

        XCTAssertEqual(project.title, "Marshall Diaries")
        XCTAssertEqual(project.rows.first?.children?.count, tree.children.count, "a grouped run still expands")
        XCTAssertEqual(mac.title, "This Mac", "the global library's work is the Mac's own group")
        XCTAssertTrue(mac.isMac)
        XCTAssertEqual(mac.rows.map(\.name), ["Downloading a model"])
        XCTAssertNotEqual(project.id, mac.id)
    }

    // MARK: - activity.popover.summary

    /// `GET /api/activity/jobs` in the engine's shape (`BackgroundJobsResponse`):
    /// one running queue, one kind waiting on memory (12 jobs), a page under a
    /// run, four failures, background work not paused.
    private static let idleMachine =
        #"{"memory_pressure":"normal","thermal_state":"nominal","on_battery":false,"in_use":false,"why_wait":null}"#

    private static func jobsJSON(paused: Bool = false, machine: String = idleMachine) -> Data {
        func job(_ id: String, _ type: String, _ name: String, _ state: String, current: Int = 0, total: Int = 0,
                 reason: String? = nil, parent: String? = nil) -> String {
            let reasonJSON = reason.map { "\"\($0)\"" } ?? "null"
            let parentJSON = parent.map { "\"\($0)\"" } ?? "null"
            return """
            {"id":"\(id)","task_type":"\(type)","name":"\(name)","library":"/tmp/x","current":\(current),\
            "total":\(total),"percent":0,"state":"\(state)","reason":\(reasonJSON),"parent_id":\(parentJSON)}
            """
        }
        let jobs = [
            job("embed", "embedding", "Embedding", "running", current: 42, total: 100),
            job("kraken", "kraken-page", "Kraken pages", "waiting", total: 12, reason: "Waiting: memory is tight"),
            job("read", "read-page", "Read a page", "waiting", total: 1, reason: "Waiting for Kraken"),
            job("page-1", "ask-a-model", "ask-a-model", "running", parent: "run-x:Entities"),
            job("run-1", "workflow", "Detect Regions", "failed", current: 1, total: 1, reason: "Kraken not installed"),
            job("run-2", "workflow", "Transcribe", "failed", current: 1, total: 1, reason: "the provider refused"),
            job("run-3", "workflow", "Names", "failed", current: 1, total: 1, reason: "no model chosen"),
            job("run-4", "workflow", "Statements", "failed", current: 1, total: 1, reason: "oldest failure")
        ]
        return Data("""
        {"jobs":[\(jobs.joined(separator: ","))],"count":\(jobs.count),"process_cpu_percent":142.0,\
        "cpu_count":8,"paused":\(paused),\
        "machine":\(machine)}
        """.utf8)
    }

    func testActivityPopoverSummary_saysWhatRunsWhatWaitsAndWhyAndTheLastThreeErrors() async throws {
        // WHY: the popover "is a summary, not a list: what is running, what is
        // waiting and the main reason why, the last three errors", read from the
        // engine through the same store the window reads.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsJSON())
        ])
        await store.refreshBackgroundJobs()

        let summary = ActivityPopoverSummary(
            jobs: store.backgroundJobs,
            paused: store.backgroundPaused,
            liveRuns: [.init(id: "live-1", name: "Transcribe Ensemble", step: "Review")]
        )

        XCTAssertEqual(summary.running.map(\.name), ["Transcribe Ensemble", "Embedding"],
                       "a page under a run is not said again beside its run")
        XCTAssertEqual(summary.running.first { $0.name == "Embedding" }?.detail, "42 of 100")
        XCTAssertEqual(summary.waitingCount, 13, "a waiting row stands for every job of its kind that waits")
        XCTAssertEqual(summary.waitingReason, "Waiting: memory is tight", "the reason most of them give")
        XCTAssertEqual(summary.recentErrors.map(\.name), ["Detect Regions", "Transcribe", "Names"],
                       "the newest three, no more")
        XCTAssertEqual(summary.recentErrors.first?.detail, "Kraken not installed", "each error says why")
        XCTAssertEqual(summary.heldBack, "Heavy work is held back: memory is tight")
        XCTAssertEqual(store.processCpuPercent, 142, "the CPU line reads the same jobs read")
    }

    func testActivityPopoverSummary_pausedBackgroundWorkIsSaidFirst() async throws {
        // WHY: "whether heavy work is held back and why": a person's pause is
        // the reason that overrides the machine's.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsJSON(paused: true))
        ])
        await store.refreshBackgroundJobs()

        XCTAssertTrue(store.backgroundPaused, "the store reads `paused` from the engine")
        let summary = ActivityPopoverSummary(jobs: store.backgroundJobs, paused: store.backgroundPaused)
        XCTAssertEqual(summary.heldBack, "Background work is paused. Work you start still runs.")
    }

    func testActivityPopoverSummary_theThrottlesReasonIsSaidOnce() {
        // WHY: the engine's why_wait can carry the same "Waiting: " a job's reason does; without
        // stripping it the popover read "Heavy work is held back: Waiting: the Mac is hot".
        let summary = ActivityPopoverSummary(
            jobs: [],
            paused: false,
            machine: Components.Schemas.MachineState(memoryPressure: nil, thermalState: .serious, onBattery: false,
                                                     inUse: false, whyWait: "Waiting: the Mac is hot")
        )
        XCTAssertEqual(summary.heldBack, "Heavy work is held back: the Mac is hot")
    }

    func testActivityPopoverSummary_nothingHeldBackWhenNothingWaitsOnTheMac() {
        // WHY: a job waiting for Kraken waits on a lane, not on the Mac; saying
        // "held back" for it would send the person looking at memory for nothing.
        let summary = ActivityPopoverSummary(
            jobs: [ActivityJob(id: "r", name: "Read a page", total: 3, state: .waiting, reason: "Waiting for Kraken")],
            paused: false
        )
        XCTAssertNil(summary.heldBack)
        XCTAssertEqual(summary.waitingCount, 3)
        XCTAssertEqual(summary.waitingReason, "Waiting for Kraken")
    }

    func testActivityPopoverSummary_saysThisMacsStateAndHidesAReadingTheEngineCouldNotTake() async throws {
        // WHY: the popover says "the Mac's state (memory pressure, heat,
        // battery, in use), read from the engine", and why heavy work waits in
        // the throttle's own words. Decoded from a recorded `machine` through
        // the real client and store, so a renamed field fails here rather than
        // silently showing nothing; a null reading (heat unreadable) is left
        // out rather than shown as a guess.
        let store = Self.storeWithMockTransport()
        let machine = #"{"memory_pressure":"warn","thermal_state":null,"on_battery":true,"in_use":true,"#
            + #""why_wait":"the Mac is on battery"}"#
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs", method: "GET", status: 200,
                 body: Self.jobsJSON(machine: machine))
        ])
        await store.refreshBackgroundJobs()

        XCTAssertEqual(store.machine, Components.Schemas.MachineState(memoryPressure: .warn, thermalState: nil, onBattery: true,
                                                                     inUse: true, whyWait: "the Mac is on battery"))
        let summary = ActivityPopoverSummary(jobs: store.backgroundJobs, paused: store.backgroundPaused,
                                             machine: store.machine)
        XCTAssertEqual(summary.macState, ["Memory pressure: warn", "On battery", "In use"],
                       "heat the engine could not read is not shown")
        XCTAssertEqual(summary.heldBack, "Heavy work is held back: the Mac is on battery",
                       "the throttle's own reason wins over a waiting job's")
    }

    // MARK: - activity.run.account (#5555): the run's row is its account

    /// A run's node as `GET /api/activity/jobs/{run}` returns it since #5555: its
    /// counts are its account's pages, and the account rides beside them
    /// (shape: `fichero-server/tests/unit/jobs/test_run_account_5555.py`).
    private static func accountTreeJSON(runState: String, reason: String?, account: String) -> Data {
        let reasonJSON = reason.map { "\"\($0)\"" } ?? "null"
        return Data("""
        {
          "id": "\(runId)", "kind": "workflow", "name": "Workflow run", "subject": "\(runId)",
          "model": null, "state": "\(runState)", "reason": \(reasonJSON), "parent_id": null,
          "done": 2, "total": 3, "failed": 1, "seconds": 61.5, "tokens": 0, "cost_usd": null,
          "unpriced_models": [], "account": \(account), "children": []
        }
        """.utf8)
    }

    private static let failedRunAccount = """
    {
      "state": "done", "pages_total": 3, "pages_done": 2, "pages_failed": 1, "pages_left": 0,
      "failures": [{"page": "p1.png", "document_id": "doc-1", "reason": "the provider refused this letter",
                    "retried": true}],
      "retried": 1, "waiting_reason": null, "reason": null, "interrupted": false,
      "estimate_seconds_left": null, "engine_peak_memory_bytes": 2147483648,
      "model_server_peak_memory_bytes": 3758096384,
      "offer": {"action": "read-again", "pages": 1, "label": "Read the 1 page that failed"}
    }
    """

    func testActivityRunAccount_aFinishedRunShowsItsFailuresPeakMemoryAndItsOffer() async throws {
        // WHY: Activity showed a ten-page run as "running, total 0" with no
        // counts and no reasons; the run's row is now its account, and a run
        // with failed pages offers to read them as one action.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/\(Self.runId)", method: "GET", status: 200,
                 body: Self.accountTreeJSON(runState: "done", reason: nil, account: Self.failedRunAccount))
        ])
        let row = ActivityMonitorRow.run(Self.run(status: .completed, failureReason: nil),
                                         tree: try await loadedTree(store))

        XCTAssertEqual(row.progressText, "2 of 3", "the run counts its pages from its account")
        XCTAssertEqual(row.errors, 1)
        XCTAssertEqual(row.peakMemoryText, "Peak memory: engine 2.0 GB, model server 3.5 GB")
        XCTAssertEqual(row.accountDetail,
                       "p1.png: the provider refused this letter (read twice)\nPeak memory: engine 2.0 GB, model server 3.5 GB")
        XCTAssertEqual(row.readAgainLabel, "Read the 1 page that failed")
    }

    func testActivityRunAccount_anInterruptedRunSaysWhenTheEngineStopped() async throws {
        // WHY: after an engine restart a run said "running" for good; the
        // engine now marks it interrupted, and the row says so in its words.
        let why = "Interrupted: the engine stopped at 14:05, before this run finished"
        let account = """
        {"state": "interrupted", "pages_total": 10, "pages_done": 6, "pages_failed": 0, "pages_left": 4,
         "failures": [], "retried": 0, "waiting_reason": null, "reason": "\(why)", "interrupted": true,
         "estimate_seconds_left": null, "engine_peak_memory_bytes": null, "model_server_peak_memory_bytes": null,
         "offer": {"action": "read-again", "pages": 4, "label": "Read the 4 pages not done"}}
        """
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/\(Self.runId)", method: "GET", status: 200,
                 body: Self.accountTreeJSON(runState: "failed", reason: why, account: account))
        ])
        let row = ActivityMonitorRow.run(Self.run(status: .failed, failureReason: why), tree: try await loadedTree(store))

        XCTAssertEqual(row.stateText, why, "not 'Failed: Interrupted: …'")
        XCTAssertEqual(row.readAgainLabel, "Read the 4 pages not done")
        XCTAssertNil(row.peakMemoryText, "a peak never measured is not shown")
    }

    func testActivityRunAccount_aRunningRunSaysWhatItWaitsForAndTheEnginesEstimate() {
        // WHY: a page waiting for memory (#5537) looked like a stuck run; the
        // row says what it waits for, and the estimate is the engine's.
        let waiting = "Waiting: memory is tight: Qwen needs about 3.9 GB, this Mac has about 1.8 GB free"
        let account = ActivityRunAccount(state: "running", pagesTotal: 4, pagesDone: 1, pagesLeft: 3,
                                         waitingReason: waiting, estimateSecondsLeft: 180)
        let row = ActivityMonitorRow(
            id: "run", kind: .run, libraryId: nil, runRowID: "run", runThreadId: Self.runId, jobId: Self.runId,
            name: "Read", projectName: nil, phase: .running, reason: nil, workingOn: "Transcribe",
            done: 1, total: 4, started: nil, seconds: 60, costUsd: nil, tokens: 0, errors: 0, model: nil,
            isLive: true, children: nil, account: account
        )
        XCTAssertEqual(row.stateText, waiting)
        XCTAssertEqual(row.remainingSeconds, 180)
        XCTAssertEqual(row.progressText, "1 of 4, \(ActivityMonitorRow.duration(180)) left")
        XCTAssertNil(row.readAgainLabel, "a run still going offers nothing to read again")
    }

    // MARK: - #5560: icons, pages by file name, ⓘ

    func testActivityWindowIcons_aPageIsNamedByItsFileAndEachRowHasKindAndStateIcons() async throws {
        // WHY: the maintainer watched pages listed as long ids, with no icon to
        // tell a run from a page or a failure from a wait.
        let pageId = "4d2286cef90f41819cea3295d7c7197a"
        let tree = Data("""
        {
          "id": "\(Self.runId)", "kind": "workflow", "name": "Workflow run", "subject": "\(Self.runId)",
          "display_name": null, "model": null, "state": "running", "reason": null, "parent_id": null,
          "done": 0, "total": 1, "failed": 0, "seconds": 3.0, "tokens": 0, "cost_usd": null,
          "unpriced_models": [], "account": null,
          "children": [
            {
              "id": "\(Self.runId):Transcribe", "kind": "workflow-step", "name": "Step",
              "subject": "\(Self.runId):Transcribe", "display_name": null, "model": null, "state": "running",
              "reason": null, "parent_id": "\(Self.runId)", "done": 0, "total": 1, "failed": 0, "seconds": 3.0,
              "tokens": 0, "cost_usd": null, "unpriced_models": [],
              "children": [
                {
                  "id": "page-row", "kind": "read-a-page", "name": "read-a-page", "subject": "\(pageId)",
                  "document_id": "\(pageId)", "display_name": "SM_NPQ_C01_004.jpg", "model": "mlx:qwen", "state": "waiting",
                  "reason": "Waiting: memory is tight", "parent_id": "\(Self.runId):Transcribe",
                  "done": 0, "total": 1, "failed": 0, "seconds": null, "tokens": 0, "cost_usd": null,
                  "unpriced_models": [], "children": []
                }
              ]
            }
          ]
        }
        """.utf8)
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs/\(Self.runId)", method: "GET", status: 200, body: tree)
        ])
        let row = ActivityMonitorRow.run(Self.run(status: .running, failureReason: nil), tree: try await loadedTree(store))
        let step = try XCTUnwrap(row.children?.first)
        let page = try XCTUnwrap(step.children?.first)

        XCTAssertEqual(page.name, "SM_NPQ_C01_004.jpg", "a page is named by its file, never its id")
        XCTAssertEqual([row.kindSymbol, step.kindSymbol, page.kindSymbol], ["flowchart", "list.bullet.indent", "doc.text"])
        XCTAssertEqual([row.kindWord, step.kindWord, page.kindWord], ["Run", "Step", "Page"])
        XCTAssertEqual(page.phase.symbol, "clock")
        XCTAssertEqual(ActivityMonitorRow.Phase.failed.symbol, "xmark.circle.fill")
        XCTAssertEqual(ActivityMonitorRow.Phase.done.symbol, "checkmark.circle.fill")
        XCTAssertTrue(row.opensDetails && page.opensDetails, "ⓘ on every row of a run opens the run's log")
    }

    func testActivityWindowIcons_trainingAndAModelLoadHaveTheirOwnIcons() {
        let training = ActivityMonitorRow.job(
            ActivityJob(id: "t", taskType: "train-a-model", name: "Train a model", state: .running),
            libraryId: Self.libraryId, projectName: nil)
        let download = ActivityMonitorRow.job(
            ActivityJob(id: "d", taskType: "model-download", name: "Download a model", state: .running),
            libraryId: Self.libraryId, projectName: nil)
        XCTAssertEqual(training.kindSymbol, "graduationcap")
        XCTAssertEqual(download.kindSymbol, "arrow.down.circle")
        XCTAssertFalse(training.opensDetails, "a job of its own has no run log for ⓘ to open")
    }

    func testActivityRunAccount_readTheFailedPagesAgainIsOneCallToTheEngine() async throws {
        // WHY: failed pages had to be found and re-run by hand; the offer is
        // one action, the engine's `read-again` route.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/workflow-execution/threads/\(Self.runId)/read-again", method: "POST", status: 202,
                 body: Data("""
                 {"thread_id": "thread-new", "from_thread_id": "\(Self.runId)", "workflow_id": "wf",
                  "workflow_name": "Read", "pages": 1, "stream_url": "https://127.0.0.1:8765/api/x"}
                 """.utf8))
        ])

        let failure = await store.readPagesAgain(runThreadId: Self.runId)

        XCTAssertNil(failure)
        let request = try XCTUnwrap(MockTransportURLProtocol.recorded().last)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.path, "/api/workflow-execution/threads/\(Self.runId)/read-again")
    }
}
