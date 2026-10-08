//
//  ProjectRunStripTests.swift
//  FicheroTests
//
//  The project window shows its recipe run (review 2026-10-07; spec
//  docs/contributor_manual/specs/source/models-chains-and-projects.md §7b, "Everything automatic after
//  Start"): `source.onboard.auto.lands-on-the-run` (#5576) — a strip while the run goes: its stage by name,
//  pages done and left, time left, what it waits for; `source.onboard.auto.results-summary` (#5577) — when
//  it ends, what it made in one line, with Read Again for the failed pages. Written from those lines.
//
//  Through the real `ActivityStore` over the generated client: only the transport is stubbed, and the job
//  tree it answers is the one `fichero-server/tests/unit/recipes/test_run_visible_to_spec.py` recorded
//  (`Tests/Fixtures/recipes/recipe_run_tree.route.json`, `recipe_run_summary_failed.route.json`); the
//  running tree is that recording with its first stage set running.
//
//  Not covered: a window drawing the strip (no mounted-view harness in this target); what the strip draws
//  is `ProjectRunStrip`'s words, checked here.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

@MainActor
final class ProjectRunStripTests: XCTestCase {

    // MARK: - Mock transport (copied, not shared: RecipeRunVisibleTests' pattern)

    private struct Stub {
        let path: String
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
            let stub = Self.stubs.first { path == $0.path && $0.method == method }
            Self.lock.unlock()

            let resolved = stub ?? Stub(path: "", method: "", status: 404, body: Data(#"{"detail":"no stub"}"#.utf8))
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

    private static func store(defaults: UserDefaults? = nil) -> ActivityStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ProjectRunStripTests.fichero",
            session: URLSession(configuration: configuration)
        )
        let service = ActivityService(ficheroClient: client)
        guard let defaults else { return ActivityStore(service: service) }
        return ActivityStore(service: service, defaults: defaults, projectKey: "project-under-test")
    }

    /// The app's defaults for one test: a suite of its own, emptied when the test ends.
    private func scratchDefaults() throws -> UserDefaults {
        let suite = "ProjectRunStripTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        addTeardownBlock { defaults.removePersistentDomain(forName: suite) }
        return defaults
    }

    /// `GET /api/recipes/project/runs`: the project's recipe runs, newest first, as (id, state).
    private static func recipeRuns(_ runs: [(id: String, state: String)]) throws -> Data {
        try json(["items": runs.map { ["job_id": $0.id, "state": $0.state, "steps": [Any](), "skipped": [Any]()] as [String: Any] }])
    }

    /// The engine's answer, as `test_run_visible_to_spec.py` recorded it.
    private static func recorded(_ name: String) throws -> [String: Any] {
        // Tests/Unit/general/Models/<this file> → Tests/Fixtures/recipes
        let tests = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let url = tests.appendingPathComponent("Fixtures/recipes/\(name).route.json")
        let record = try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        return try XCTUnwrap(record["response"] as? [String: Any])
    }

    private static func json(_ object: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: object)
    }

    /// The recorded recipe run, still going: its first stage (Transcribe) running with one page done and one
    /// left, two minutes left at its pace, its pages waiting for memory; the stages after it waiting.
    private static func runningTree() throws -> [String: Any] {
        var tree = try recorded("recipe_run_tree")
        tree["state"] = "running"
        tree["finished_at"] = NSNull()
        tree["summary"] = NSNull()
        var stages = try XCTUnwrap(tree["stages"] as? [[String: Any]])
        var account = try XCTUnwrap(stages[0]["account"] as? [String: Any])
        account["state"] = "running"
        account["pages_done"] = 1
        account["pages_left"] = 1
        account["estimate_seconds_left"] = 120.0
        account["waiting_reason"] = "memory is tight"
        stages[0]["state"] = "running"
        stages[0]["account"] = account
        stages[1]["state"] = "waiting"
        stages[2]["state"] = "waiting"
        tree["stages"] = stages
        return tree
    }

    /// The recorded recipe run once it ended with failed pages: its summary on its node, as the engine sends it.
    private static func failedTree() throws -> [String: Any] {
        var tree = try recorded("recipe_run_tree")
        tree["state"] = "failed"
        tree["summary"] = try recorded("recipe_run_summary_failed")
        return tree
    }

    /// `GET /api/activity/jobs` listing `jobs`.
    private static func jobsList(_ jobs: String) -> Data {
        Data("""
        {"jobs": [\(jobs)], "count": 1, "process_cpu_percent": null, "cpu_count": 8, "paused": false,
         "machine": {"memory_pressure": "warn", "thermal_state": null, "on_battery": false, "in_use": false,
                     "why_wait": null}}
        """.utf8)
    }

    private static func recipeRow(_ id: String, state: String = "running") -> String {
        """
        {"id": "\(id)", "task_type": "run-a-recipe", "name": "Run a recipe", "library": "",
         "current": 0, "total": 1, "percent": 0.0, "state": "\(state)", "reason": null, "parent_id": null}
        """
    }

    private static func treeReads(_ jobId: String) -> Int {
        MockTransportURLProtocol.recorded().compactMap(\.url?.path).filter { $0 == "/api/activity/jobs/\(jobId)" }.count
    }

    // MARK: - source.onboard.auto.lands-on-the-run (#5576)

    func testStrip_whileTheRunGoes_saysItsStagePagesTimeLeftAndWhatItWaitsFor() async throws {
        // WHY: after Start the project window said nothing; the run was only in the Activity window.
        let store = Self.store()
        let tree = try Self.runningTree()
        let jobId = try XCTUnwrap(tree["id"] as? String)
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsList(Self.recipeRow(jobId))),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(tree))
        ])
        XCTAssertNil(ProjectRunStrip(store: store), "no strip before a recipe run")

        await store.refreshBackgroundJobs()

        XCTAssertEqual(store.projectRunId, jobId, "the jobs poll's recipe run is the project's run")
        let strip = try XCTUnwrap(ProjectRunStrip(store: store))
        XCTAssertTrue(strip.isLive)
        XCTAssertEqual(strip.title, "Transcribe (Kraken) · stage 1 of 3", "the running stage by name, never an id")
        XCTAssertEqual(strip.detail, "1 done · 0 failed · 1 left · \(ActivityMonitorRow.duration(120)) left · "
                       + "Waiting: memory is tight", "the stage's run account, in the engine's words")
        XCTAssertTrue(strip.failed.isEmpty)

        await store.refreshBackgroundJobs()
        XCTAssertEqual(Self.treeReads(jobId), 1, "an unchanged row reads the tree once: no poll of its own")
    }

    func testStrip_aRowStandingForSeveralWaitingRuns_isNotTheProjectsRun() async throws {
        // WHY: the jobs list folds waiting runs of a kind into one row ("waiting:<kind>"), which has no tree.
        let store = Self.store()
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs", method: "GET", status: 200,
                 body: Self.jobsList(Self.recipeRow("waiting:run-a-recipe", state: "waiting")))
        ])
        await store.refreshBackgroundJobs()

        XCTAssertNil(store.projectRunId)
        XCTAssertNil(ProjectRunStrip(store: store))
        XCTAssertEqual(Self.treeReads("waiting:run-a-recipe"), 0)
    }

    // MARK: - source.onboard.auto.results-summary (#5577)

    func testStrip_whenTheRunEnds_saysWhatItMadeAndReadsTheFailedPagesAgain() async throws {
        // WHY: the run ended with nothing in the project window to say what it made or that pages failed.
        let store = Self.store()
        let running = try Self.runningTree()
        let jobId = try XCTUnwrap(running["id"] as? String)
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsList(Self.recipeRow(jobId))),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(running))
        ])
        await store.refreshBackgroundJobs()
        XCTAssertEqual(ProjectRunStrip(store: store)?.isLive, true)

        // It ends: it leaves the jobs list, and its tree, read once more, carries what it made.
        let failed = try Self.failedTree()
        // The failed stage's run, as the recorded summary names it (re-recorded fixtures get new ids).
        let threadId = try XCTUnwrap(((failed["summary"] as? [String: Any])?["failed"] as? [[String: Any]])?
            .first?["thread_id"] as? String)
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsList("")),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(failed)),
            Stub(path: "/api/workflow-execution/threads/\(threadId)/read-again", method: "POST", status: 202, body: Data("""
                {"thread_id":"thread-again","from_thread_id":"\(threadId)","workflow_id":"w","workflow_name":"Transcribe (Kraken)",
                 "pages":2,"stream_url":"https://127.0.0.1:8765/api/workflow-execution/stream/thread-again"}
                """.utf8))
        ])
        await store.refreshBackgroundJobs()
        let deadline = Date().addingTimeInterval(5)
        while ProjectRunStrip(store: store)?.isLive == true, Date() < deadline {
            try await Task.sleep(for: .milliseconds(50))
        }

        let strip = try XCTUnwrap(ProjectRunStrip(store: store), "the ended run stays on the strip")
        XCTAssertFalse(strip.isLive)
        XCTAssertEqual(strip.title, "Recipe run failed")
        let engineLines = try XCTUnwrap((failed["summary"] as? [String: Any])?["lines"] as? [String])
        XCTAssertEqual(strip.detail, engineLines.joined(separator: " · "), "one line, the summary's own words")
        let stage = try XCTUnwrap(strip.failed.first)
        XCTAssertEqual(stage.offer, "Read the 2 pages that failed")
        XCTAssertEqual(stage.threadId, threadId)

        let readAgainError = await store.readPagesAgain(runThreadId: stage.threadId)
        XCTAssertNil(readAgainError, "Read Again is the stage run's own route, through the store")
        XCTAssertTrue(MockTransportURLProtocol.recorded().contains {
            $0.httpMethod == "POST" && $0.url?.path == "/api/workflow-execution/threads/\(threadId)/read-again"
        })

        store.putAwayProjectRun()
        XCTAssertNil(ProjectRunStrip(store: store), "put away, the strip is gone")
    }

    // MARK: - source.onboard.auto.lands-on-the-run after a relaunch (#5576)

    func testRelaunch_aRunStillGoing_isBackOnTheStrip() async throws {
        // WHY: after a relaunch the strip came back only for a run the app saw start; one still running said nothing.
        let store = Self.store(defaults: try scratchDefaults())
        let tree = try Self.runningTree()
        let jobId = try XCTUnwrap(tree["id"] as? String)
        MockTransportURLProtocol.reset([
            Stub(path: "/api/recipes/project/runs", method: "GET", status: 200,
                 body: try Self.recipeRuns([("newer-ended-run", "done"), (jobId, "running")])),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(tree))
        ])

        await store.restoreProjectRun()

        XCTAssertEqual(store.projectRunId, jobId, "the run still going wins over a newer one that ended")
        let strip = try XCTUnwrap(ProjectRunStrip(store: store))
        XCTAssertTrue(strip.isLive)
        XCTAssertEqual(strip.title, "Transcribe (Kraken) · stage 1 of 3")
        XCTAssertEqual(Self.treeReads("newer-ended-run"), 0, "only the adopted run's tree is read")
    }

    func testRelaunch_aRunThatEndedWhileClosed_showsItsSummary() async throws {
        // WHY: a run that ended while the app was closed never said what it made in the project window.
        let store = Self.store(defaults: try scratchDefaults())
        let failed = try Self.failedTree()
        let jobId = try XCTUnwrap(failed["id"] as? String)
        MockTransportURLProtocol.reset([
            Stub(path: "/api/recipes/project/runs", method: "GET", status: 200,
                 body: try Self.recipeRuns([(jobId, "failed"), ("older-run", "done")])),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(failed))
        ])

        await store.restoreProjectRun()

        let strip = try XCTUnwrap(ProjectRunStrip(store: store), "the newest ended run's summary is on the strip")
        XCTAssertEqual(strip.jobId, jobId)
        XCTAssertFalse(strip.isLive)
        XCTAssertEqual(strip.title, "Recipe run failed")
        XCTAssertEqual(strip.detail, "Read 2 of 2 pages · Names: 1 People · 1 Places · 1 date · 1 statement")
    }

    func testRelaunch_aSummaryThePersonClosed_staysClosed() async throws {
        // WHY: a summary the person closed must not come back on every launch.
        let defaults = try scratchDefaults()
        let failed = try Self.failedTree()
        let jobId = try XCTUnwrap(failed["id"] as? String)
        MockTransportURLProtocol.reset([
            Stub(path: "/api/recipes/project/runs", method: "GET", status: 200,
                 body: try Self.recipeRuns([(jobId, "failed"), ("older-run", "done")])),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(failed))
        ])
        let before = Self.store(defaults: defaults)
        await before.restoreProjectRun()
        XCTAssertEqual(before.projectRunId, jobId)
        before.putAwayProjectRun()

        // Relaunch: a new store over the same project's defaults.
        let after = Self.store(defaults: defaults)
        await after.restoreProjectRun()

        XCTAssertNil(after.projectRunId, "closed stays closed; an older ended run does not take its place")
        XCTAssertNil(ProjectRunStrip(store: after))
        XCTAssertEqual(Self.treeReads("older-run"), 0)
        XCTAssertEqual(Self.treeReads(jobId), 1, "only the first launch read the closed run's tree")
    }
}
