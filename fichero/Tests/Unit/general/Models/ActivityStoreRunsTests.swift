//
//  ActivityStoreRunsTests.swift
//  FicheroTests
//
//  #4960 app half: the window/browser now read the engine's `workflow_runs`
//  table (`GET /workflow-execution/runs`) through `ActivityStore`, the SAME
//  record the toolbar popover already reads, instead of the old lossy
//  7-day/100-event activity log — which is the verified cause of the two
//  surfaces disagreeing (`agent-work/reviews/
//  activity-system-review-2026-09-20.md` §2). Pure store tests with the
//  client stubbed the way `ArtifactStoreTests` does it (mock transport
//  copied, not shared — a new suite file, per team-lead, rather than adding
//  to the already-large `ActivityStoreTests`).
//
//  Not covered here (no mounted-view harness exists in this target): that
//  the window/popover actually RENDER a Delete affordance, or that a
//  keyboard Delete/context-menu click reaches `ActivityStore.deleteRuns` —
//  only the store's own behaviour is testable this way.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

@MainActor
final class ActivityStoreRunsTests: XCTestCase {

    // MARK: - Mock transport (copied, not shared — ArtifactStoreTests' pattern)

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
                !$0.pathContains.isEmpty && path.contains($0.pathContains) && $0.method == method
            }
            Self.lock.unlock()

            let resolved = stub ?? Stub(pathContains: "", method: "", status: 200, body: Data("{}".utf8))
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

    private static func storeWithMockTransport(library: LibraryManager.LibraryReference? = nil) -> ActivityStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ActivityStoreRunsTests.fichero",
            session: session
        )
        let service = ActivityService(ficheroClient: client)
        return ActivityStore(service: service, library: library)
    }

    /// `rebuildRuns`/`loadMoreRuns` read only `.id`/`.displayName` off this —
    /// the network call goes through the STORE's own (mock-transported)
    /// `activityService`, never `library.activityService` — so this
    /// reference's own (real, unmocked) transport is never exercised.
    private static func testLibrary() -> LibraryManager.LibraryReference {
        LibraryManager.LibraryReference(
            url: FileManager.default.temporaryDirectory.appendingPathComponent("ActivityStoreRunsTests.fichero"),
            document: FicheroDocument(),
            displayName: "Test Library",
            id: UUID(uuidString: "22222222-2222-2222-2222-222222222222")
        )
    }

    private static func runSummaryJSON(
        threadId: String,
        status: String = "completed",
        startedAt: String = "2026-09-20T10:00:00Z"
    ) -> [String: Any] {
        [
            "thread_id": threadId,
            "workflow_id": "wf-1",
            "workflow_name": "Transcribe",
            "status": status,
            "started_at": startedAt
        ]
    }

    private static func listResponseJSON(_ summaries: [[String: Any]]) -> Data {
        try! JSONSerialization.data(withJSONObject: ["items": summaries, "count": summaries.count])
    }

    // MARK: - rebuildRuns: reads the runs table, not the event log

    func testRebuildRunsPatchesEachFreshRowIntoRuns() async {
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs", method: "GET", status: 200,
                body: Self.listResponseJSON([
                    Self.runSummaryJSON(threadId: "t1"),
                    Self.runSummaryJSON(threadId: "t2", status: "failed")
                ])
            )
        ])

        await store.rebuildRuns(activeExecutions: [], library: Self.testLibrary())

        XCTAssertEqual(store.runs.count, 2)
        XCTAssertTrue(store.runs.contains { $0.runId == "t1" && $0.status == .completed })
        XCTAssertTrue(store.runs.contains { $0.runId == "t2" && $0.status == .failed })
        // No stray call to the old event-log endpoint.
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertTrue(requests.allSatisfy { $0.url?.path == "/api/workflow-execution/runs" })
    }

    // MARK: - loadMoreRuns: appends, never replaces

    func testLoadMoreRunsAppendsWithoutDisturbingExistingRows() async {
        let store = Self.storeWithMockTransport()
        // A FULL first page (the store's page size is 50): a short page means
        // "no more", and then loadMoreRuns is rightly a no-op.
        let firstPage = (1...50).map { Self.runSummaryJSON(threadId: "t\($0)") }
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs", method: "GET", status: 200,
                body: Self.listResponseJSON(firstPage)
            )
        ])
        await store.rebuildRuns(activeExecutions: [], library: Self.testLibrary())
        let firstPageRun = try! XCTUnwrap(store.runs.first { $0.runId == "t1" })

        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs", method: "GET", status: 200,
                body: Self.listResponseJSON([Self.runSummaryJSON(threadId: "t51")])
            )
        ])
        await store.loadMoreRuns(library: Self.testLibrary())

        XCTAssertEqual(store.runs.count, 51, "the second page's row is APPENDED, not a replacement")
        XCTAssertTrue(store.runs.contains { $0.runId == "t1" }, "the first page's row is untouched")
        XCTAssertTrue(store.runs.contains { $0.runId == "t51" }, "the second page's row is now present")
        // The first page's row is still the identical value: nothing re-fetched it.
        let stillThere = try! XCTUnwrap(store.runs.first { $0.runId == "t1" })
        XCTAssertEqual(stillThere.timestamp, firstPageRun.timestamp)
    }

    func testLoadMoreRunsIsANoOpWhenTheLastPageWasShort() async {
        let store = Self.storeWithMockTransport()
        // A page shorter than the page size (1 row) means `runsHasMore` goes false.
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs", method: "GET", status: 200,
                body: Self.listResponseJSON([Self.runSummaryJSON(threadId: "t1")])
            )
        ])
        await store.rebuildRuns(activeExecutions: [], library: Self.testLibrary())
        XCTAssertFalse(store.runsHasMore)

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/workflow-execution/runs", method: "GET", status: 200,
                 body: Self.listResponseJSON([Self.runSummaryJSON(threadId: "t2")]))
        ])
        await store.loadMoreRuns(library: Self.testLibrary())

        XCTAssertEqual(store.runs.count, 1, "no further page is fetched once runsHasMore is false")
        XCTAssertTrue(MockTransportURLProtocol.recorded().isEmpty, "loadMoreRuns made no request")
    }

    // MARK: - patchRun: ONE row, in place

    func testPatchRunReplacesOnlyTheMatchingRowInPlace() {
        let store = Self.storeWithMockTransport()
        let first = ActivityRun(
            id: "lib|t1", runId: "t1", workflowId: "wf", threadId: "t1",
            workflowName: "Transcribe", timestamp: Date(), status: .running,
            progress: 0.2, currentStep: "OCR", errorCount: 0, fileCount: 10, isLive: true,
            libraryId: nil, libraryName: nil
        )
        let second = ActivityRun(
            id: "lib|t2", runId: "t2", workflowId: "wf", threadId: "t2",
            workflowName: "Translate", timestamp: Date(), status: .running,
            progress: nil, currentStep: nil, errorCount: 0, fileCount: 3, isLive: true,
            libraryId: nil, libraryName: nil
        )
        store.patchRun(first)
        store.patchRun(second)
        XCTAssertEqual(store.runs.map(\.id), ["lib|t1", "lib|t2"])

        let updatedFirst = ActivityRun(
            id: "lib|t1", runId: "t1", workflowId: "wf", threadId: "t1",
            workflowName: "Transcribe", timestamp: first.timestamp, status: .completed,
            progress: 1.0, currentStep: nil, errorCount: 0, fileCount: 10, isLive: false,
            libraryId: nil, libraryName: nil
        )
        store.patchRun(updatedFirst)

        XCTAssertEqual(store.runs.count, 2, "patching an existing id never changes the count")
        XCTAssertEqual(store.runs.map(\.id), ["lib|t1", "lib|t2"], "the OTHER row keeps its position")
        XCTAssertEqual(store.runs[0].status, .completed, "the matching row's fields are updated")
        XCTAssertEqual(store.runs[1].status, .running, "the other row is completely untouched")
    }

    func testPatchRunAppendsARunNotYetPresent() {
        let store = Self.storeWithMockTransport()
        let run = ActivityRun(
            id: "lib|t9", runId: "t9", workflowId: "wf", threadId: "t9",
            workflowName: "Catalogue", timestamp: Date(), status: .running,
            progress: nil, currentStep: nil, errorCount: 0, fileCount: 0, isLive: true,
            libraryId: nil, libraryName: nil
        )
        store.patchRun(run)
        XCTAssertEqual(store.runs.map(\.id), ["lib|t9"])
    }

    // MARK: - deleteRuns: exactly deletedIds removed, skippedIds kept and reported

    func testDeleteRunsRemovesExactlyTheDeletedIdsAndKeepsSkipped() async {
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs", method: "GET", status: 200,
                body: Self.listResponseJSON([
                    Self.runSummaryJSON(threadId: "t1", status: "failed"),
                    Self.runSummaryJSON(threadId: "t2", status: "running")
                ])
            )
        ])
        await store.rebuildRuns(activeExecutions: [], library: Self.testLibrary())
        XCTAssertEqual(store.runs.count, 2)

        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs/delete", method: "POST", status: 200,
                body: try! JSONSerialization.data(withJSONObject: [
                    "deleted_ids": ["t1"], "skipped_ids": ["t2"], "count": 1
                ])
            )
        ])
        let outcome = await store.deleteRuns(threadIds: ["t1", "t2"])

        XCTAssertEqual(outcome.deletedIds, ["t1"])
        XCTAssertEqual(outcome.skippedIds, ["t2"], "a still-running run is reported skipped, not silently kept")
        XCTAssertFalse(store.runs.contains { $0.runId == "t1" }, "the deleted run leaves the list")
        XCTAssertTrue(store.runs.contains { $0.runId == "t2" }, "the skipped run keeps its row")
    }

    func testClearFailedSendsTheStatusFormNotExplicitIds() async {
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs/delete", method: "POST", status: 200,
                body: try! JSONSerialization.data(withJSONObject: [
                    "deleted_ids": ["t1", "t3"], "skipped_ids": [], "count": 2
                ])
            )
        ])

        _ = await store.deleteRuns(statuses: ["failed"])

        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1)
        let body = try! XCTUnwrap(requests.first?.httpBodyOrStream())
        let decoded = try! JSONSerialization.jsonObject(with: body) as? [String: Any]
        XCTAssertEqual(decoded?["statuses"] as? [String], ["failed"], "Clear Failed is the status form")
        XCTAssertNil(decoded?["thread_ids"], "never sends explicit ids for Clear Failed")
    }

    // MARK: - activity.window.absolute-times (#5432)

    /// WHY: the engine sends `started_at` as aware UTC with microseconds. The
    /// store read it with a default `ISO8601DateFormatter`, which refuses
    /// fractional seconds, and substituted `Date()` — so every row said "just
    /// now". If this goes red, a day-old run is being stamped with the moment
    /// the list loaded.
    func testActivityWindowAbsoluteTimes_theEngineTimeShapeIsReadNotReplacedByNow() async {
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs", method: "GET", status: 200,
                body: Self.listResponseJSON([
                    Self.runSummaryJSON(threadId: "t1", startedAt: "2026-09-20T10:00:00.123456+00:00"),
                    Self.runSummaryJSON(threadId: "t2", startedAt: "not a time")
                ])
            )
        ])

        await store.rebuildRuns(activeExecutions: [], library: Self.testLibrary())

        let read = store.runs.first { $0.runId == "t1" }?.timestamp
        let expected = Date(timeIntervalSince1970: 1_789_898_400.123456)
        XCTAssertEqual(read?.timeIntervalSince1970 ?? 0, expected.timeIntervalSince1970, accuracy: 0.001)
        let unreadable = store.runs.first { $0.runId == "t2" }
        XCTAssertNotNil(unreadable, "a run whose time can't be read still has its row")
        XCTAssertNil(unreadable?.timestamp, "an unreadable time is unknown, never now")
    }

    // MARK: - activity.window.honest-state (#5431)

    /// WHY: #5431. One 401 (an engine respawn's token change) left "Couldn't
    /// load activity from Local" up for good. The footer must name the cause,
    /// and the next good load must clear it; if this goes red, a transient
    /// refusal is reported as a standing failure.
    func testActivityWindowHonestState_aFailedLoadNamesItsCauseAndClearsOnTheNextSuccess() async {
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs", method: "GET", status: 401,
                body: Data(#"{"detail": "bootstrap token mismatch"}"#.utf8)
            )
        ])
        await store.rebuildRuns(activeExecutions: [], library: Self.testLibrary())
        XCTAssertEqual(store.runLoadFailures.count, 1)
        XCTAssertTrue(
            store.runLoadFailures.first?.contains("refused the app's credentials") == true,
            "the footer names the cause: \(store.runLoadFailures)"
        )

        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/workflow-execution/runs", method: "GET", status: 200,
                body: Self.listResponseJSON([Self.runSummaryJSON(threadId: "t1")])
            )
        ])
        await store.rebuildRuns(activeExecutions: [], library: Self.testLibrary())
        XCTAssertEqual(store.runLoadFailures, [], "a successful load clears the failure")
    }

    // MARK: - A refusal names its cause (#5469)

    /// The engine's 403 for a project outside every location it may open, as
    /// `_rejected_library_path_payload` writes it (api/main.py, the roots check).
    private static let rootsRefusalBody = Data(
        #"{"detail": "'/Users/me/Elsewhere/Diaries.fichero' is a .fichero package, but it is outside every location this engine may open (allowed roots and security-scoped grants). Open it from the app so access can be granted, or move it into an allowed location such as Documents.", "code": "library_outside_allowed_locations"}"#.utf8
    )

    /// The engine's 403 for a request it refuses on credentials (api/auth.py: a
    /// non-loopback caller): no machine code, just the refusal.
    private static let credentialsRefusalBody = Data(#"{"detail": "loopback only"}"#.utf8)

    /// A good, idle `GET /api/activity/jobs` (its required fields only, plus an empty list).
    private static let emptyJobsBody = Data(
        #"{"jobs":[],"count":0,"cpu_count":8,"paused":false,"machine":{"memory_pressure":"normal","thermal_state":"nominal","on_battery":false,"in_use":false,"why_wait":null}}"#.utf8
    )

    private static let locationLine =
        "Couldn't load activity from Test Library: the engine isn't allowed to open the project from where it's saved"

    /// WHY: #5469. A project refused for its LOCATION (failed_check=roots) read
    /// "the engine refused the app's credentials", sending the user after a token
    /// that was fine. If this goes red, the footer guesses the cause again.
    func testRunListRootsRefusalSaysTheProjectsLocation() async {
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/workflow-execution/runs", method: "GET", status: 403, body: Self.rootsRefusalBody)
        ])
        await store.rebuildRuns(activeExecutions: [], library: Self.testLibrary())
        XCTAssertEqual(store.runLoadFailures, [Self.locationLine])
    }

    /// WHY: #5469's other half. A credentials refusal must still read as one, or
    /// the location sentence would be a new guess in the other direction.
    func testRunListCredentialsRefusalSaysCredentials() async {
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/workflow-execution/runs", method: "GET", status: 403, body: Self.credentialsRefusalBody)
        ])
        await store.rebuildRuns(activeExecutions: [], library: Self.testLibrary())
        XCTAssertEqual(
            store.runLoadFailures,
            ["Couldn't load activity from Test Library: the engine refused the app's credentials"]
        )
    }

    /// WHY: #5469. The jobs poll dropped the 403 body and logged at debug, so a
    /// refused project showed NOTHING. It feeds the same footer, with the same
    /// cause, and its next good poll clears its line (as #5431). If this goes
    /// red, a refused project is silent again, or its line never leaves.
    func testJobsPollRefusalReachesTheFooterAndClearsOnTheNextGoodPoll() async {
        let library = Self.testLibrary()
        let store = Self.storeWithMockTransport(library: library)
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs", method: "GET", status: 403, body: Self.rootsRefusalBody)
        ])
        await store.refreshBackgroundJobs()
        XCTAssertEqual(store.runLoadFailures, [Self.locationLine])

        // The run list refused for the same reason: one line, not two.
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs", method: "GET", status: 403, body: Self.rootsRefusalBody),
            Stub(pathContains: "/api/workflow-execution/runs", method: "GET", status: 403, body: Self.rootsRefusalBody)
        ])
        await store.rebuildRuns(activeExecutions: [], library: library)
        XCTAssertEqual(store.runLoadFailures, [Self.locationLine], "the same cause says it once")

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/activity/jobs", method: "GET", status: 200, body: Self.emptyJobsBody),
            Stub(
                pathContains: "/api/workflow-execution/runs", method: "GET", status: 200,
                body: Self.listResponseJSON([Self.runSummaryJSON(threadId: "t1")])
            )
        ])
        await store.refreshBackgroundJobs()
        await store.rebuildRuns(activeExecutions: [], library: library)
        XCTAssertEqual(store.runLoadFailures, [], "the next good loads clear the footer")
    }
}

/// `URLRequest.httpBody` is nil once the request has gone through
/// `URLProtocol` (the body moves to `httpBodyStream`) — read either, the way
/// a body-asserting test needs to.
private extension URLRequest {
    func httpBodyOrStream() -> Data? {
        if let httpBody { return httpBody }
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufferSize = 4096
        var buffer = [UInt8](repeating: 0, count: bufferSize)
        // Until the stream ends, not while `hasBytesAvailable`: that can be false before the
        // client's writer thread has put the first bytes in (#5607).
        while true {
            let read = stream.read(&buffer, maxLength: bufferSize)
            guard read > 0 else { break }
            data.append(buffer, count: read)
        }
        return data
    }
}
