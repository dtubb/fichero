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

    func testStrip_aStageWithNoRunYetIsNamedInWords_neverByJobIds() async throws {
        // WHY: the line read "find-lines, read-a-line · stage 1 of 3" (`activity.run.stage-named-in-words`): the stage's
        // jobs joined by their ids. The engine now sends the title from the job registry's names.
        let store = Self.store()
        var tree = try Self.runningTree()
        var stages = try XCTUnwrap(tree["stages"] as? [[String: Any]])
        stages[0]["child_id"] = NSNull()
        stages[0]["steps"] = ["find-lines", "read-a-line"]
        stages[0]["card"] = "lines"
        stages[0]["title"] = "Find lines and Read each line"
        tree["stages"] = stages
        let jobId = try XCTUnwrap(tree["id"] as? String)
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsList(Self.recipeRow(jobId))),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(tree))
        ])
        await store.refreshBackgroundJobs()
        let strip = try XCTUnwrap(ProjectRunStrip(store: store))
        XCTAssertEqual(strip.title, "Find lines and Read each line · stage 1 of 3")
    }

    // MARK: - source.onboard.auto.lands-on-the-run (#5576)

    func testStrip_aRunOnFewerPagesThanTheProject_saysStartsCountOfWhatWasDone() async throws {
        // WHY: Start said 95 pages and the run went on 58, with no reason on the strip (#6091, dogfood B12).
        let store = Self.store()
        var tree = try Self.runningTree()
        var stages = try XCTUnwrap(tree["stages"] as? [[String: Any]])
        stages[0]["note"] = "already done on 37 of 95 pages; runs on the other 58"
        tree["stages"] = stages
        let jobId = try XCTUnwrap(tree["id"] as? String)
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsList(Self.recipeRow(jobId))),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(tree))
        ])

        await store.refreshBackgroundJobs()

        let strip = try XCTUnwrap(ProjectRunStrip(store: store))
        XCTAssertEqual(strip.detail, "1 done · 0 failed · 1 left · already done on 37 of 95 pages; runs on the other 58 · "
                       + "\(ActivityMonitorRow.duration(120)) left · Waiting: memory is tight")
    }

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
        // What it missed and its one action, as the engine words them (#6170): plain Start on the run's folder.
        let missed = try XCTUnwrap((failed["summary"] as? [String: Any])?["missed"] as? [String: Any])
        XCTAssertEqual(strip.missed?.words, missed["words"] as? String)
        XCTAssertEqual(strip.missed?.offer, "Run again on what was missed")
        XCTAssertNil(strip.missed?.folderId, "an import-scoped run's Start is the whole project")
        // The recipe's setup page offers the same action beside Start (#6170).
        XCTAssertEqual(RecipeReadyFields.missed(in: store)?.words, strip.missed?.words)

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
        // The recorded summary says where lines and regions were found first (58baaff4e, #5668).
        XCTAssertEqual(strip.detail, "Lines on 2 of 2 pages · regions on 0 of 2 pages · Read 2 of 2 pages · "
                       + "Names: 1 People · 1 Places · 1 page dated · 1 date named · 1 statement")
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

    // MARK: - activity.run.progress-per-folder (#5540)

    func testFolderWords_sayHowFarInFolders_onlyForARunOverSeveral() {
        // WHY: at archive scale one page figure for 800 folders says nothing; a run over one folder
        // (an import's one batch) would only repeat what its stage says.
        XCTAssertEqual(RecipeRunFolders(done: 3, total: 800).words, "3 of 800 folders")
        XCTAssertEqual(RecipeRunFolders(done: 0, total: 2).words, "0 of 2 folders")
        XCTAssertNil(RecipeRunFolders(done: 0, total: 1).words)
        XCTAssertNil(RecipeRunFolders(done: 0, total: 0).words)
    }

    func testStrip_aRunOverManyFolders_saysHowManyAreDone_fromItsStatus() async throws {
        // WHY: the engine counts folders done on the run's status (`folders_done`, `folders_total`); the strip
        // must say them after the stage, through the store, read with the run's tree.
        let store = Self.store()
        var tree = try Self.runningTree()
        // The run's own reason is now its progress; it must never read as a wait.
        tree["reason"] = "Running the recipe: 3 of 800 folders done"
        let jobId = try XCTUnwrap(tree["id"] as? String)
        XCTAssertEqual(tree["kind"] as? String, ActivityStore.recipeRunKind, "the recorded tree is a recipe run")
        let status: [String: Any] = [
            "job_id": jobId, "state": "running", "steps": [Any](), "skipped": [Any](),
            "folders_done": 3, "folders_total": 800,
            "reason": "Running the recipe: 3 of 800 folders done"
        ]
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsList(Self.recipeRow(jobId))),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(tree)),
            Stub(path: "/api/recipes/project/runs/\(jobId)", method: "GET", status: 200, body: try Self.json(status))
        ])

        await store.refreshBackgroundJobs()

        XCTAssertEqual(store.recipeRunFolders[jobId], RecipeRunFolders(done: 3, total: 800))
        let strip = try XCTUnwrap(ProjectRunStrip(store: store))
        XCTAssertEqual(strip.title, "Transcribe (Kraken) · stage 1 of 3 · 3 of 800 folders")
        XCTAssertFalse(strip.detail.contains("Waiting: Running"), "the run's progress is not a wait: \(strip.detail)")
    }

    func testEachFolder_saysWhichStepsAreDoneOnIt_fromTheRunsStatus() async throws {
        // WHY (`activity.run.folder-steps-done`, #5642): "3 of 800 folders" says nothing about which steps a folder
        // still needs; the engine counts each step's pages per folder on the run's status, named by its stage title.
        let store = Self.store()
        let tree = try Self.runningTree()
        let jobId = try XCTUnwrap(tree["id"] as? String)
        let step: [String: Any] = ["steps": ["lines", "read"], "card": "workflow", "state": "running",
                                   "title": "Find lines and Read each line"]
        let status: [String: Any] = [
            "job_id": jobId, "state": "running", "steps": [step], "skipped": [Any](),
            "folders_done": 0, "folders_total": 2,
            "folder_steps": [
                ["folder_id": "A", "steps": [["steps": ["lines", "read"], "done": 12, "of": 20],
                                             ["steps": ["names"], "done": 1, "of": 1]]],
                ["folder_id": "B", "steps": [["steps": ["lines", "read"], "done": 20, "of": 20],
                                             ["steps": ["export"], "done": NSNull(), "of": 3]]]
            ]
        ]
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsList(Self.recipeRow(jobId))),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(tree)),
            Stub(path: "/api/recipes/project/runs/\(jobId)", method: "GET", status: 200, body: try Self.json(status))
        ])

        await store.refreshBackgroundJobs()

        let a = try XCTUnwrap(store.recipeFolderSteps["A"])
        XCTAssertFalse(a.allDone)
        XCTAssertEqual(a.words, "Find lines and Read each line: 12 of 20 pages\nnames: done",
                       "a step the status has no stage for is named by its step ids")
        let b = try XCTUnwrap(store.recipeFolderSteps["B"])
        XCTAssertFalse(b.allDone, "a step that cannot tell is not done")
        XCTAssertEqual(b.words, "Find lines and Read each line: done\nexport: cannot tell")
        XCTAssertTrue(RecipeFolderSteps(steps: [.init(name: "Read", done: 1, of: 1)]).allDone)
    }

    func testStrip_aRunOverOneFolder_saysNothingMoreThanItsStage() async throws {
        let store = Self.store()
        let tree = try Self.runningTree()
        let jobId = try XCTUnwrap(tree["id"] as? String)
        let status: [String: Any] = [
            "job_id": jobId, "state": "running", "steps": [Any](), "skipped": [Any](),
            "folders_done": 0, "folders_total": 1
        ]
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs", method: "GET", status: 200, body: Self.jobsList(Self.recipeRow(jobId))),
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: try Self.json(tree)),
            Stub(path: "/api/recipes/project/runs/\(jobId)", method: "GET", status: 200, body: try Self.json(status))
        ])

        await store.refreshBackgroundJobs()

        XCTAssertEqual(store.recipeRunFolders[jobId], RecipeRunFolders(done: 0, total: 1))
        XCTAssertEqual(ProjectRunStrip(store: store)?.title, "Transcribe (Kraken) · stage 1 of 3")
    }
}

/// `activity.run.strip-tells-the-truth` (day goal 3): a run that has ended or stalled is not shown as running because its tree
/// read failed. Pure, over the state words. Not run on the Pro; the builder/M4 runs it.
final class ProjectRunStripStateTests: XCTestCase {
    func testAnEndedNodeStandsWhateverTheListSays() {
        for ended in ["done", "failed", "cancelled"] {
            XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: ended, jobState: .running), ended)
        }
    }

    func testAnEndInTheListWinsOverATreeThatHasNotCaughtUp() {
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: "running", jobState: .completed), "done")
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: "running", jobState: .failed), "failed")
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: nil, jobState: .failed), "failed")
    }

    func testAStallInTheListShowsAsStalled() {
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: "running", jobState: .stalled), "stalled")
    }

    func testAPauseInTheListShowsAsPaused_neverAsASpinningRun() {
        // WHY (review LOW, 2026-10-28): a tree read that has not caught up still says running while the polled list says
        // the run is paused; the strip spun for a paused run, which is what the owner sees.
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: "running", jobState: .paused), "paused")
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: nil, jobState: .paused), "paused")
    }

    func testOtherwiseTheNodeThenTheListDecide() {
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: "paused", jobState: .running), "paused")
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: nil, jobState: .running), "running")
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: nil, jobState: .waiting), "waiting")
        XCTAssertEqual(ProjectRunStrip.effectiveState(nodeState: nil, jobState: nil), "waiting")
    }

    // MARK: - activity.spinner-reflects-process-liveness (#4346)

    private static func node(state: String) throws -> ActivityJobNode {
        let json = """
            {"id":"r1","kind":"run-a-recipe","name":"Recipe","subject":"r1","state":"\(state)","done":0,"total":0,"children":[]}
            """
        return ActivityJobNode(try JSONDecoder().decode(Components.Schemas.JobTree.self, from: Data(json.utf8)))
    }

    func testOnlyARunningRunSpins_aPausedWaitingOrStalledOneStaysOnTheStripStill() throws {
        // WHY: the strip spun for any run that had not ended, so a paused run, one waiting for memory and one the
        // engine no longer moves all looked alive and working.
        XCTAssertTrue(ProjectRunStrip(jobId: "r1", node: try Self.node(state: "running"), job: nil).spins)
        for still in ["paused", "waiting", "stalled"] {
            let strip = ProjectRunStrip(jobId: "r1", node: try Self.node(state: still), job: nil)
            XCTAssertTrue(strip.isLive, "\(still): not ended, so not closable")
            XCTAssertFalse(strip.spins, "\(still): no spinner")
        }
        XCTAssertFalse(ProjectRunStrip(jobId: "r1", node: nil, job: nil).spins, "nothing read yet: waiting, still")
        XCTAssertFalse(ProjectRunStrip(jobId: "r1", node: try Self.node(state: "done"), job: nil).spins)
    }
}
