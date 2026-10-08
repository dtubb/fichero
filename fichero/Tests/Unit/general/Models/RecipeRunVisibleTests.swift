//
//  RecipeRunVisibleTests.swift
//  FicheroTests
//
//  Everything automatic after Start, seen by the person (review 2026-10-07; spec
//  docs/contributor_manual/specs/source/models-chains-and-projects.md §7b, "Everything automatic after
//  Start"): `source.onboard.auto.plan-shows-what-will-not-run` (#5573), `source.onboard.auto.lands-on-the-run`
//  (#5576), `source.onboard.auto.results-summary` (#5577). Written from those lines.
//
//  Through the real `RecipeSetupStore` and `ActivityStore` over the generated client: only the transport is
//  stubbed, and it answers with what the engine's own routes answered, recorded by
//  `fichero-server/tests/unit/recipes/test_run_visible_to_spec.py` into `Tests/Fixtures/recipes/*.route.json`.
//
//  Not covered: a window drawing the views (no mounted-view harness in this target); what Ready and the
//  details draw is the store's and `ActivityDetails`' words, checked here.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

@MainActor
final class RecipeRunVisibleTests: XCTestCase {

    // MARK: - Mock transport (copied, not shared: ActivityDetailsTests' pattern)

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

    private static func client() -> FicheroClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        return FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/RecipeRunVisibleTests.fichero",
            session: URLSession(configuration: configuration)
        )
    }

    /// The engine's answer, as `test_run_visible_to_spec.py` recorded it.
    private static func recorded(_ name: String) throws -> Data {
        // Tests/Unit/general/Models/<this file> → Tests/Fixtures/recipes
        let tests = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let url = tests.appendingPathComponent("Fixtures/recipes/\(name).route.json")
        let record = try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        return try JSONSerialization.data(withJSONObject: XCTUnwrap(record["response"]))
    }

    private static func object(_ data: Data) throws -> [String: Any] {
        try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private static let libraryId = UUID(uuidString: "55765576-5576-5576-5576-557655765576")!

    // MARK: - source.onboard.auto.plan-shows-what-will-not-run (#5573)

    func testReady_showsEverySkippedStepWithWhyAndFix_andEveryDownloadWithSizeAndDownload() async throws {
        // WHY: the app read only the plan's refusals, so a person pressed Start never seeing that names
        // would not run (no model) or that a check would not (the project keeps its pages here), and with
        // no way to fetch the spaCy model the names step needed.
        let store = RecipeSetupStore(client: Self.client())
        MockTransportURLProtocol.reset([
            Stub(path: "/api/recipes/project/start", method: "GET", status: 200,
                 body: try Self.recorded("start_plan_skips_and_downloads")),
            Stub(path: "/api/local-models/download/spacy/es_core_news_sm", method: "POST", status: 200,
                 body: Data(#"{"status":"queued","model_type":"spacy","model_id":"es_core_news_sm","job_id":"j-1"}"#.utf8))
        ])
        await store.loadStartPlan()

        let fixes = Dictionary(uniqueKeysWithValues: store.skippedSteps.map { ($0.step, $0.fix) })
        XCTAssertEqual(fixes["check"], .some("allow-cloud"), "a cloud step here: let pages leave this Mac")
        XCTAssertEqual(fixes["nameless"], .some("choose-model"), "a step with no model: choose one")
        XCTAssertEqual(fixes["authorities"], .some(nil), "no card runs it yet: no fix button")
        XCTAssertTrue(store.skippedSteps.allSatisfy { !$0.why.isEmpty }, "each says why")
        XCTAssertEqual(RecipeStepRow.fixTitle("allow-cloud"), "Let pages leave this Mac")

        let download = try XCTUnwrap(store.downloads.first { $0.model == "es_core_news_sm" })
        XCTAssertEqual(download.steps, ["names"])
        XCTAssertTrue(RecipeDownloadRows.words(download, store: store).hasPrefix("spaCy model es_core_news_sm"))
        XCTAssertFalse(store.canStart, "Start waits for the download")

        await store.download(download)
        let posted = MockTransportURLProtocol.recorded().filter { $0.httpMethod == "POST" }.compactMap(\.url?.path)
        XCTAssertEqual(posted, ["/api/local-models/download/spacy/es_core_news_sm"], "the one download route")
        XCTAssertTrue(store.downloading.contains("es_core_news_sm"), "Ready says it is downloading")
        XCTAssertNil(store.errorMessage)
    }

    // MARK: - source.onboard.auto.lands-on-the-run (#5576)

    func testStart_landsOnTheRecipeRunItQueued() async throws {
        // WHY: Start closed setup and nothing pointed to the run: the person did not know anything ran.
        let store = RecipeSetupStore(client: Self.client())
        let started = try Self.recorded("start_runs_the_proposed_jobs")
        MockTransportURLProtocol.reset([Stub(path: "/api/recipes/project/start", method: "POST", status: 200, body: started)])
        XCTAssertNil(FirstRunWindow.startedRunSelection(jobId: store.startedRunJobId, projectId: Self.libraryId),
                     "nothing to land on before Start")

        let didStart = await store.start()
        XCTAssertTrue(didStart)

        let jobId = try XCTUnwrap((Self.object(started)["started"] as? [String: Any])?["job_id"] as? String)
        XCTAssertEqual(store.startedRunJobId, jobId)
        XCTAssertEqual(FirstRunWindow.startedRunSelection(jobId: store.startedRunJobId, projectId: Self.libraryId),
                       ActivitySelection(jobId: jobId, libraryId: Self.libraryId),
                       "setup opens the recipe run's Activity details in its project")
    }

    func testRecipeRunDetails_showEachStageWithItsPagesAndState() async throws {
        // WHY: the recipe run's row said "Done" with no stages; its pages were summed across steps.
        let store = ActivityStore(service: ActivityService(ficheroClient: Self.client()))
        let tree = try Self.recorded("recipe_run_tree")
        let jobId = try XCTUnwrap(Self.object(tree)["id"] as? String)
        MockTransportURLProtocol.reset([Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: tree)])
        await store.loadDetails(jobId: jobId)

        let details = try XCTUnwrap(ActivityDetails(store: store, selection: ActivitySelection(jobId: jobId, libraryId: Self.libraryId)))
        XCTAssertEqual(details.stages.map(\.title), ["Transcribe (Kraken)", "Check on the pages", "Write the synced folder"],
                       "each stage by name, never an id")
        XCTAssertEqual(details.stages.map(\.steps), ["Steps lines, read", "Step check", "Step export"])
        XCTAssertEqual(details.stages.map(\.state), ["Done", "Done", "Done"])
        XCTAssertEqual(details.stages.first?.counts, "2 done · 0 failed · 0 left", "the stage's run account")
        XCTAssertNil(details.counts, "pages are counted stage by stage, never summed across stages")
    }

    func testRecipeRunDetails_aStageRunsChangeRereadsTheRecipeRun() async throws {
        // WHY: the details follow the row (`activity.details.follows-the-row`): a stage's pages done and left
        // must move while the recipe run's details are open, though the change names the stage's run.
        let store = ActivityStore(service: ActivityService(ficheroClient: Self.client()))
        let tree = try Self.recorded("recipe_run_tree")
        let jobId = try XCTUnwrap(Self.object(tree)["id"] as? String)
        MockTransportURLProtocol.reset([Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: tree)])
        await store.loadDetails(jobId: jobId)
        let stageRun = try XCTUnwrap(store.runTrees[jobId]?.stages.first?.childId)
        XCTAssertEqual(store.recipeRunTrees(holdingStage: stageRun), [jobId])

        store.applyActivityEvent(ActivityItem(
            id: "act-5576", type: "workflow_completed", level: "info",
            timestamp: "2026-10-07T12:00:00Z", message: "Transcribe done", threadId: stageRun
        ))
        func reads() -> Int {
            MockTransportURLProtocol.recorded().compactMap(\.url?.path).filter { $0 == "/api/activity/jobs/\(jobId)" }.count
        }
        let deadline = Date().addingTimeInterval(5)
        while reads() < 2, Date() < deadline {
            try await Task.sleep(for: .milliseconds(50))
        }
        XCTAssertEqual(reads(), 2, "the recipe run's tree is read again when its stage's run changes")
    }

    // MARK: - source.onboard.auto.results-summary (#5577)

    func testRecipeRunDetails_whenItEnds_sayWhatItMade() async throws {
        // WHY: the recipe row said "Done" even when pages failed inside its steps, with no account of what
        // was found and no way to read the failed pages again.
        let store = ActivityStore(service: ActivityService(ficheroClient: Self.client()))
        var tree = try Self.object(Self.recorded("recipe_run_tree"))
        tree["summary"] = try Self.object(Self.recorded("recipe_run_summary_failed"))
        let jobId = try XCTUnwrap(tree["id"] as? String)
        let failed = try XCTUnwrap(((tree["summary"] as? [String: Any])?["failed"] as? [[String: Any]])?.first)
        let threadId = try XCTUnwrap(failed["thread_id"] as? String)
        MockTransportURLProtocol.reset([
            Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200,
                 body: try JSONSerialization.data(withJSONObject: tree)),
            Stub(path: "/api/workflow-execution/threads/\(threadId)/read-again", method: "POST", status: 202, body: Data("""
                {"thread_id":"thread-again","from_thread_id":"\(threadId)","workflow_id":"w","workflow_name":"Transcribe (Kraken)",
                 "pages":2,"stream_url":"https://127.0.0.1:8765/api/workflow-execution/stream/thread-again"}
                """.utf8))
        ])
        await store.loadDetails(jobId: jobId)

        let details = try XCTUnwrap(ActivityDetails(store: store, selection: ActivitySelection(jobId: jobId, libraryId: Self.libraryId)))
        let summary = try XCTUnwrap(details.summary, "an ended run says what it made")
        XCTAssertEqual(summary.lines.first, "Read 2 of 2 pages")
        XCTAssertTrue(summary.lines.contains("Names: 1 People · 1 Places"), "\(summary.lines)")
        XCTAssertTrue(summary.lines.contains("1 date · 1 statement"), "\(summary.lines)")
        let stage = try XCTUnwrap(summary.failed.first)
        XCTAssertEqual(stage.offer, "Read the 2 pages that failed")
        XCTAssertEqual(stage.threadId, threadId)
        XCTAssertTrue(summary.skipped.contains { $0.id == "check" && $0.hasFix }, "a skipped step with its fix")
        XCTAssertTrue(summary.skipped.contains { $0.id == "signs" && !$0.hasFix })

        let readAgainError = await store.readPagesAgain(runThreadId: stage.threadId)
        XCTAssertNil(readAgainError, "Read Again is the run's own route")
        XCTAssertTrue(MockTransportURLProtocol.recorded().contains {
            $0.httpMethod == "POST" && $0.url?.path == "/api/workflow-execution/threads/\(threadId)/read-again"
        })
    }
}
