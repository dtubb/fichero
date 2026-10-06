//
//  ActivityDetailsTests.swift
//  FicheroTests
//
//  #5561: the details of an Activity row are one view read from the record
//  the table reads (the row's node of `GET /api/activity/jobs/{id}`) and one
//  filtered log read. It follows the row: the table's tree re-read is its
//  update, with no stream or poll of its own.
//
//  Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md,
//  "The details view (#5561)": `activity.details.one-record`,
//  `activity.details.follows-the-row`, `activity.details.heading-names-not-ids`,
//  `activity.details.state-says-why`, `activity.details.progress-counts`,
//  `activity.details.failed-pages-by-name`, `activity.details.log-filtered-newest-last`,
//  `activity.details.resources`, `activity.details.actions-are-the-rows`,
//  `activity.details.open-in-the-app`, `activity.details.one-mount`.
//  Written from those lines, not from the code.
//
//  Through the real `ActivityStore`, its real `ActivityService` and the
//  generated client's real decoding: only the transport is stubbed. The tree
//  below has the shape `fichero-server/tests/unit/jobs/test_activity_details_5561.py`
//  pins on the engine's route (a three-page transcription run).
//
//  Not covered: a real window drawing the view (no mounted-view harness in
//  this target); what it draws is `ActivityDetails`, built here as it builds it.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

@MainActor
final class ActivityDetailsTests: XCTestCase {

    // MARK: - Mock transport (copied, not shared: ActivityTableTests' pattern)

    private struct Stub {
        let pathSuffix: String
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
            let stub = Self.stubs.first { path.hasSuffix($0.pathSuffix) && $0.method == method }
            Self.lock.unlock()

            let resolved = stub ?? Stub(pathSuffix: "", method: "", status: 404, body: Data(#"{"detail":"no stub"}"#.utf8))
            guard let url = request.url,
                  let response = HTTPURLResponse(
                      url: url, statusCode: resolved.status, httpVersion: "HTTP/1.1",
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
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ActivityDetailsTests.fichero",
            session: URLSession(configuration: configuration)
        )
        return ActivityStore(service: ActivityService(ficheroClient: client))
    }

    // MARK: - Fixtures

    private static let runId = "thread-5561aa"
    private static let stepId = "thread-5561aa:transcribe"
    private static let libraryId = UUID(uuidString: "55615561-5561-5561-5561-556155615561")!
    private static let selection = ActivitySelection(jobId: runId, libraryId: libraryId)

    private static func pageJSON(_ index: Int, state: String, reason: String? = nil) -> String {
        let finished = state == "running" ? "null" : "\"2026-10-06T12:0\(index + 1):00+00:00\""
        let reasonJSON = reason.map { "\"\($0)\"" } ?? "null"
        return """
        {
          "id": "page-\(index)", "kind": "read-a-page", "name": "Read a page", "subject": "doc-\(index)",
          "document_id": "doc-\(index)", "display_name": "p\(index).png", "model": "openai:gpt-5",
          "state": "\(state)", "reason": \(reasonJSON), "parent_id": "\(stepId)",
          "started_at": "2026-10-06T12:00:30+00:00", "finished_at": \(finished),
          "started_by": "workflow", "working_on": null,
          "done": \(state == "done" ? 1 : 0), "total": 1, "failed": \(state == "failed" ? 1 : 0),
          "seconds": 2.5, "tokens": 1100, "cost_usd": 0.00225, "unpriced_models": [], "children": []
        }
        """
    }

    /// The run's node as the engine serves it (#5561): times, who started it,
    /// what it works on, names on every node, the account beside the counts.
    private static func treeJSON(
        runState: String,
        pageStates: [String],
        runReason: String? = nil,
        workingOn: String? = nil,
        account: String = "null"
    ) -> Data {
        let pages = pageStates.enumerated().map { index, state in
            pageJSON(index, state: state, reason: state == "failed" ? "the provider refused this letter" : nil)
        }
        let done = pageStates.filter { $0 == "done" }.count
        let failed = pageStates.filter { $0 == "failed" }.count
        let finished = runState == "running" ? "null" : "\"2026-10-06T12:04:00+00:00\""
        let reasonJSON = runReason.map { "\"\($0)\"" } ?? "null"
        let workingJSON = workingOn.map { "\"\($0)\"" } ?? "null"
        let stepState = runState == "running" ? "running" : "done"
        return Data("""
        {
          "id": "\(runId)", "kind": "workflow", "name": "Workflow run", "subject": "\(runId)",
          "document_id": null, "display_name": "Transcribe", "model": null, "state": "\(runState)",
          "reason": \(reasonJSON), "parent_id": null,
          "started_at": "2026-10-06T12:00:00+00:00", "finished_at": \(finished),
          "started_by": "automatic", "working_on": \(workingJSON),
          "done": \(done), "total": \(pageStates.count), "failed": \(failed), "seconds": 240.0,
          "tokens": \(1100 * pageStates.count), "cost_usd": \(0.00225 * Double(pageStates.count)),
          "unpriced_models": [], "account": \(account),
          "children": [
            {
              "id": "\(stepId)", "kind": "workflow-step", "name": "Step", "subject": "\(stepId)",
              "document_id": null, "display_name": "Transcribe", "model": null, "state": "\(stepState)",
              "reason": null, "parent_id": "\(runId)",
              "started_at": "2026-10-06T12:00:10+00:00", "finished_at": \(finished),
              "started_by": "workflow", "working_on": \(workingJSON == "null" ? "null" : "\"p1.png\""),
              "done": \(done), "total": \(pageStates.count), "failed": \(failed), "seconds": 230.0,
              "tokens": \(1100 * pageStates.count), "cost_usd": \(0.00225 * Double(pageStates.count)),
              "unpriced_models": [],
              "children": [\(pages.joined(separator: ","))]
            }
          ]
        }
        """.utf8)
    }

    private static let failedAccount = """
    {
      "state": "done", "pages_total": 3, "pages_done": 2, "pages_failed": 1, "pages_left": 0,
      "failures": [{"page": "p1.png", "document_id": "doc-1", "reason": "the provider refused this letter",
                    "retried": false}],
      "retried": 0, "waiting_reason": null, "reason": null, "interrupted": false,
      "estimate_seconds_left": null, "engine_peak_memory_bytes": 2147483648,
      "model_server_peak_memory_bytes": 3758096384,
      "offer": {"action": "read-again", "pages": 1, "label": "Read the 1 page that failed"}
    }
    """

    private static let runningStub = Stub(
        pathSuffix: "/api/activity/jobs/\(runId)", method: "GET", status: 200,
        body: treeJSON(runState: "running", pageStates: ["done", "running", "waiting"],
                       workingOn: "Transcribe, p1.png")
    )

    private static let failedStub = Stub(
        pathSuffix: "/api/activity/jobs/\(runId)", method: "GET", status: 200,
        body: treeJSON(runState: "done", pageStates: ["done", "failed", "done"], account: failedAccount)
    )

    private func details(
        _ store: ActivityStore,
        _ selection: ActivitySelection = ActivityDetailsTests.selection
    ) throws -> ActivityDetails {
        try XCTUnwrap(ActivityDetails(store: store, selection: selection), "the store holds the row's record")
    }

    private func waitUntil(_ condition: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(3)
        while !condition(), Date() < deadline {
            try await Task.sleep(for: .milliseconds(50))
        }
    }

    // MARK: - activity.details.follows-the-row

    func testActivityDetailsFollowsTheRow_theTablesTreeRereadUpdatesTheDetailsWithoutReopening() async throws {
        // WHY: the old window froze at open: its status was copied from the row
        // when it was double-clicked. The details read the store's record, so the
        // table's re-read of that row, on the change stream, is their update.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([Self.runningStub])
        await store.loadDetails(jobId: Self.runId)

        let running = try details(store)
        XCTAssertEqual(running.row.phase, .running)
        XCTAssertTrue(running.stateText.hasPrefix("Running: Transcribe"), running.stateText)
        XCTAssertEqual(running.counts?.text, "1 done · 0 failed · 2 left")

        MockTransportURLProtocol.reset([Self.failedStub])
        store.applyActivityEvent(ActivityItem(
            id: "act-1", type: "workflow_completed", level: "info",
            timestamp: "2026-10-06T12:04:00Z", message: "Transcribe done", threadId: Self.runId
        ))
        try await waitUntil { store.runTrees[Self.runId]?.state == "done" }

        let finished = try details(store)  // the same selection, not reopened
        XCTAssertNotEqual(finished.row.phase, .running, "the details follow the row to its end")
        XCTAssertEqual(finished.counts?.text, "2 done · 1 failed · 0 left")
        XCTAssertEqual(finished.failedPages.map(\.name), ["p1.png"])
        let paths = MockTransportURLProtocol.recorded().compactMap(\.url?.path)
        XCTAssertEqual(paths, ["/api/activity/jobs/\(Self.runId)"],
                       "the details open no stream or poll of their own: the table's one tree read")
    }

    // MARK: - A run started elsewhere shows live

    func testActivityDetailsOneRecord_aRunStartedElsewhereShowsLive() async throws {
        // WHY: a run started from another window, the CLI or a schedule was
        // treated as history ("isLive" meant "this window started it"). The
        // store's run list has not read it yet; its tree alone makes it live.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([Self.runningStub])
        XCTAssertTrue(store.runs.isEmpty)
        await store.loadDetails(jobId: Self.runId)

        let live = try details(store)
        XCTAssertTrue(live.isLive)
        XCTAssertEqual(live.row.kind, .run)
        XCTAssertEqual(live.heading, "Transcribe · 3 pages")
        XCTAssertTrue(live.actions.contains(.control(.pause)) && live.actions.contains(.control(.stop)),
                      "Pause and Stop are the row's own job routes")
        XCTAssertTrue(live.subheading.contains("Started automatically"))
    }

    // MARK: - activity.details.heading-names-not-ids

    func testActivityDetailsHeading_namesNotIds() async throws {
        // WHY: rows fell back to node ids and pages to their subject; a page is
        // named by its file, and no thread id, node id or temp name appears.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([Self.runningStub])
        await store.loadDetails(jobId: Self.runId)

        let page = try details(store, ActivitySelection(jobId: "page-1", libraryId: Self.libraryId))
        XCTAssertEqual(page.row.kind, .page)
        XCTAssertEqual(page.heading, "Read a page · p1.png")
        XCTAssertNil(page.counts, "a single page shows no counts, never 0 of 0")
        XCTAssertTrue(page.actions.contains(.openPage(documentId: "doc-1")), "a page row offers Open the page")
        let step = try details(store, ActivitySelection(jobId: Self.stepId, libraryId: Self.libraryId))
        XCTAssertEqual(step.heading, "Transcribe · 3 pages")
        XCTAssertTrue(step.actions.contains(.showPages(documentIds: ["doc-0", "doc-1", "doc-2"])),
                      "a step row offers Show the pages")
        XCTAssertFalse(step.actions.contains { if case .showTrace = $0 { return true } else { return false } },
                       "the trace is a run's, absent on a step")
        let run = try details(store)
        for shown in [page, step, run] {
            let words = ([shown.heading, shown.stateText] + shown.subheading).joined(separator: " ")
            XCTAssertFalse(words.contains(Self.runId), "no thread id: \(words)")
            XCTAssertFalse(words.contains("page-1"), "no job id: \(words)")
            XCTAssertFalse(words.contains("doc-1"), "no document id: \(words)")
        }
    }

    // MARK: - activity.details.failed-pages-by-name + the retry action

    func testActivityDetailsFailedPages_byNameWithWhyAndTheOfferToReadThemAgain() async throws {
        // WHY: failed pages had to be found by hand; they are listed by name
        // with their reason, and "Read the N pages that failed again" is one
        // call to the engine's read-again route for the run.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([Self.failedStub])
        await store.loadDetails(jobId: Self.runId)

        let failed = try details(store)
        XCTAssertEqual(failed.failedPages, [
            ActivityDetails.FailedPage(id: "0", name: "p1.png", reason: "the provider refused this letter")
        ])
        XCTAssertTrue(failed.actions.contains(.readAgain(label: "Read the 1 page that failed again")))
        XCTAssertFalse(failed.actions.contains(.control(.pause)), "a finished run has no Pause: absent, not disabled")
        // Resources: absolute times, elapsed, tokens, cost as the table shows it, peak memory.
        let labels = failed.resources.map(\.label)
        XCTAssertEqual(labels, ["Started", "Finished", "Elapsed", "Tokens", "Cost",
                                "Peak memory, engine", "Peak memory, model server"])
        XCTAssertEqual(failed.resources.first { $0.label == "Cost" }?.value, failed.row.costText)
        XCTAssertEqual(failed.resources.first { $0.label == "Peak memory, engine" }?.value, "2.0 GB")

        MockTransportURLProtocol.reset([
            Stub(pathSuffix: "/api/workflow-execution/threads/\(Self.runId)/read-again", method: "POST", status: 202,
                 body: Data("""
                 {"thread_id": "thread-new", "from_thread_id": "\(Self.runId)", "workflow_id": "wf",
                  "workflow_name": "Transcribe", "pages": 1, "stream_url": "https://127.0.0.1:8765/api/x"}
                 """.utf8))
        ])
        let threadId = try XCTUnwrap(failed.runThreadId)
        let failure = await store.readPagesAgain(runThreadId: threadId)
        XCTAssertNil(failure)
        XCTAssertEqual(MockTransportURLProtocol.recorded().last?.url?.path,
                       "/api/workflow-execution/threads/\(Self.runId)/read-again")
    }

    // MARK: - activity.details.log-filtered-newest-last

    func testActivityDetailsLog_readByTheRowsJobIdAndKeptNewestLast() async throws {
        // WHY: the log was one string per run, or streamed lines that could not
        // be copied. It is read by the row's own job id, the engine's lines for
        // it and the rows under it, kept in the order served (newest last).
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathSuffix: "/api/activity/jobs/page-1/log", method: "GET", status: 200, body: Data("""
            {"job_id": "page-1", "lines": [
              {"timestamp": "2026-10-06T12:00:30+00:00", "level": "info", "message": "Started p1.png", "job_id": "page-1"},
              {"timestamp": "2026-10-06T12:02:00+00:00", "level": "error",
               "message": "Failed: p1.png: the provider refused this letter", "job_id": "page-1"}
            ]}
            """.utf8))
        ])

        await store.loadJobLog(jobId: "page-1")

        let lines = try XCTUnwrap(store.jobLogs["page-1"])
        XCTAssertEqual(lines.map(\.message), ["Started p1.png", "Failed: p1.png: the provider refused this letter"])
        XCTAssertEqual(lines.last?.level, "error", "newest last")
        XCTAssertTrue(lines[1].plainText.contains("error  Failed: p1.png"), "copied as plain text")
        XCTAssertEqual(MockTransportURLProtocol.recorded().compactMap(\.url?.path),
                       ["/api/activity/jobs/page-1/log"], "one read, filtered to the row by the engine")
        XCTAssertNil(store.jobLogs[Self.runId], "another row's log is not touched")
    }

    // MARK: - activity.details.one-mount: a job of its own has details

    func testActivityDetailsOneMount_aJobOfItsOwnHasDetailsLikeAnyRun() async throws {
        // WHY: only runs had details; a job of its own (an embedding queue)
        // had none. Its details read the jobs poll's row, the table's.
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathSuffix: "/api/activity/jobs", method: "GET", status: 200, body: Data("""
            {"jobs": [{"id": "embed-1", "task_type": "embedding", "name": "Embedding queue", "library": "",
                       "current": 4, "total": 10, "percent": 40.0, "state": "waiting",
                       "reason": "Waiting: memory is tight"}],
             "count": 1, "process_cpu_percent": null, "cpu_count": 8, "paused": false,
             "machine": {"memory_pressure": "warn", "thermal_state": null, "on_battery": false, "in_use": false,
                         "why_wait": null}}
            """.utf8))
        ])
        await store.refreshBackgroundJobs()

        let job = try details(store, ActivitySelection(jobId: "embed-1", libraryId: Self.libraryId))
        XCTAssertEqual(job.row.kind, .job)
        XCTAssertEqual(job.heading, "Embedding queue")
        XCTAssertEqual(job.stateText, "Waiting: memory is tight")
        XCTAssertEqual(job.machineText, "This Mac: memory pressure warn", "a waiting row names the Mac's reading")
        XCTAssertEqual(job.counts?.text, "4 done · 0 failed · 6 left")
    }
}
