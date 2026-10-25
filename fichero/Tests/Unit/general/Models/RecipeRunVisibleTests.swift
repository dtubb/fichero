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

    // MARK: - built in is never a warning (#5816)

    func testReady_listsABuiltInStepAsBuiltIn_neverAmongTheSkipped() async throws {
        // WHY: the engine put a deliberate built-in step (Find where the readers disagree, worked out when a page is
        // opened) in `skipped`, which Ready draws under "Will not run" as a problem. Owner ruling: built in is never a
        // warning. The plan now carries `built_in`; the store reads it apart from `skipped`.
        var plan = try Self.object(try Self.recorded("start_plan_skips_and_downloads"))
        plan["built_in"] = [["step": "doubt", "sentence": "built in: worked out when you open a page, from the readers above; there is nothing to run"]]
        let store = RecipeSetupStore(client: Self.client())
        MockTransportURLProtocol.reset([
            Stub(path: "/api/recipes/project/start", method: "GET", status: 200,
                 body: try JSONSerialization.data(withJSONObject: plan))
        ])
        await store.loadStartPlan()

        XCTAssertEqual(store.builtInSteps.map(\.step), ["doubt"])
        XCTAssertTrue(store.builtInSteps[0].sentence.contains("worked out when you open a page"))
        XCTAssertFalse(store.skippedSteps.contains { $0.step == "doubt" }, "built in is not a skipped step")
        XCTAssertEqual(RecipeBuiltInRows.heading, "Built in")
    }

    // MARK: - source.onboard.train-path: the count, said early

    func testReady_saysHowManyCorrectedLinesTrainingNeeds_perJob_beforeAnyOffer() async throws {
        // WHY: the plan carries `train_ahead` (one sentence per trainable step not ready yet); the store hands a stage
        // page the sentences of its own jobs only, decoded through the generated client (trainAhead).
        var plan = try Self.object(try Self.recorded("start_plan_skips_and_downloads"))
        let sentence = "Training a model of your own for Read a line is offered once the project has the corrected work. It needs 2,000 corrected lines; 0 on 0 pages so far."
        plan["train_ahead"] = [["step": "read", "job": "read-a-line", "sentence": sentence]]
        let store = RecipeSetupStore(client: Self.client())
        MockTransportURLProtocol.reset([
            Stub(path: "/api/recipes/project/start", method: "GET", status: 200,
                 body: try JSONSerialization.data(withJSONObject: plan))
        ])
        await store.loadStartPlan()

        XCTAssertEqual(store.trainAhead(forJobs: ["read-a-line"]), [sentence])
        XCTAssertEqual(store.trainAhead(forJobs: ["find-lines", "find-names-tag-words"]), [], "another stage's jobs: nothing")
        XCTAssertEqual(store.trainAhead(forJobs: []), [])
    }

    // MARK: - source.onboard.auto.plan-shows-what-will-not-run (#5573)

    func testReady_showsEverySkippedStepWithWhyAndFix_andWhatStartWillFetch() async throws {
        // WHY: the app read only the plan's refusals, so a person pressed Start never seeing that names
        // would not run (no model) or that a check would not (the project keeps its pages here). Since #5664
        // (ruled 2026-10-11) nobody downloads in setup: Start fetches the model the names step needs, and Ready
        // says so in the engine's sentence, with no Download button and Start not held for it.
        let store = RecipeSetupStore(client: Self.client())
        MockTransportURLProtocol.reset([
            Stub(path: "/api/recipes/project/start", method: "GET", status: 200,
                 body: try Self.recorded("start_plan_skips_and_downloads"))
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
        XCTAssertFalse(RecipeDownloadRows.isUnderWay(download), "not started: Start will fetch it")
        XCTAssertEqual(RecipeDownloadRows.sentence(store), "Start downloads the spaCy pipeline es_core_news_sm (16 MB).",
                       "Ready says what Start will fetch, by name and size")
        XCTAssertTrue(store.canStart, "Start is not held for a model it fetches itself")
        XCTAssertTrue(MockTransportURLProtocol.recorded().allSatisfy { $0.httpMethod != "POST" },
                      "reading the plan downloads nothing")
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

    func testStart_keepsReadysStepMenusWhenItsAnswerCarriesNone() async throws {
        // WHY: Start's answer carries `step_choices: []` (the menus are for before Start, #5707); taking it as the plan
        // emptied Ready's menus the moment the run started.
        let store = RecipeSetupStore(client: Self.client())
        MockTransportURLProtocol.reset([
            Stub(path: "/api/recipes/project/start", method: "GET", status: 200,
                 body: try Self.recorded("start_plan_skips_and_downloads"))
        ])
        await store.loadStartPlan()
        let before = try XCTUnwrap(store.startPlan?.stepChoices?.count)
        XCTAssertGreaterThan(before, 0, "the recorded plan lists step menus")

        var answer = try Self.object(try Self.recorded("start_runs_the_proposed_jobs"))
        answer["step_choices"] = []
        MockTransportURLProtocol.reset([
            Stub(path: "/api/recipes/project/start", method: "POST", status: 200,
                 body: try JSONSerialization.data(withJSONObject: answer))
        ])
        let didStart = await store.start()

        XCTAssertTrue(didStart)
        XCTAssertEqual(store.startPlan?.stepChoices?.count, before, "Ready's menus stay after Start")
        XCTAssertNotNil(store.startedRunJobId, "the answer's own started run is still taken")
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

    func testDetails_aFailedTreeReadSaysSoInWordsAndTheNextGoodReadClearsIt() async throws {
        // WHY: with the loading words gone (`activity.window.no-empty-prose`) a nil `ActivityDetails` could mean "failed";
        // the details say why, never a pane that stays blank.
        let store = ActivityStore(service: ActivityService(ficheroClient: Self.client()))
        let tree = try Self.recorded("recipe_run_tree")
        let jobId = try XCTUnwrap(Self.object(tree)["id"] as? String)
        let body = Data(#"{"detail":"The project is busy"}"#.utf8)
        MockTransportURLProtocol.reset([Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 500, body: body)])
        await store.loadDetails(jobId: jobId)
        XCTAssertNil(ActivityDetails(store: store, selection: ActivitySelection(jobId: jobId, libraryId: Self.libraryId)))
        let failure = try XCTUnwrap(store.detailsReadFailure(forJobId: jobId))
        XCTAssertEqual(failure, "Couldn't read this row: The project is busy", "the engine's own words, not the client's")
        XCTAssertNotNil(store.detailsReadFailure(forJobId: jobId + ":step"), "a step's details say why its run's read failed")

        MockTransportURLProtocol.reset([Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200, body: tree)])
        await store.loadDetails(jobId: jobId)
        XCTAssertNil(store.detailsReadFailure(forJobId: jobId), "a read that works clears it")
        XCTAssertNotNil(ActivityDetails(store: store, selection: ActivitySelection(jobId: jobId, libraryId: Self.libraryId)))
    }

    func testActivityService_aRefusalWithABodySaysTheEnginesWordsOnEveryUndocumentedBranch() async throws {
        // WHY (#6109): each `.undocumented` branch threw `unexpectedResponse(500)` and dropped `{"detail": ...}`;
        // they share `ActivityServiceError.failure`, so the run list stands for them all.
        let body = Data(#"{"detail":"The project is busy"}"#.utf8)
        MockTransportURLProtocol.reset([Stub(path: "/api/workflow-execution/runs", method: "GET", status: 500, body: body)])
        let service = ActivityService(ficheroClient: Self.client())
        do {
            _ = try await service.listWorkflowRuns()
            XCTFail("a 500 must throw")
        } catch {
            XCTAssertEqual(error.localizedDescription, "The project is busy")
        }
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
        let engineLines = try XCTUnwrap((tree["summary"] as? [String: Any])?["lines"] as? [String])
        XCTAssertEqual(summary.lines, engineLines, "the summary's lines are the engine's words, as given")
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

    func testRecipeRunSummary_showsTheEnginesLinesAsGiven_andNoneWhenItSendsNone() async throws {
        // WHY: the app built its own summary lines ("Read 2 of 2 pages") from the counts; the engine now
        // says them (#5577), so a changed word in the engine shows, and no lines means no hand-built line.
        for lines in [["Read 3 of 5 pages, two left to read"], nil] as [[String]?] {
            let store = ActivityStore(service: ActivityService(ficheroClient: Self.client()))
            var tree = try Self.object(Self.recorded("recipe_run_tree"))
            var summary = try Self.object(Self.recorded("recipe_run_summary_failed"))
            if let lines { summary["lines"] = lines } else { summary.removeValue(forKey: "lines") }
            tree["summary"] = summary
            let jobId = try XCTUnwrap(tree["id"] as? String)
            MockTransportURLProtocol.reset([
                Stub(path: "/api/activity/jobs/\(jobId)", method: "GET", status: 200,
                     body: try JSONSerialization.data(withJSONObject: tree))
            ])
            await store.loadDetails(jobId: jobId)
            let details = try XCTUnwrap(ActivityDetails(store: store, selection: ActivitySelection(jobId: jobId, libraryId: Self.libraryId)))
            let shown = try XCTUnwrap(details.summary, "an ended run says what it made")
            XCTAssertEqual(shown.lines, lines ?? [], "the engine's lines as given; none when it sends none")
        }
    }
}
