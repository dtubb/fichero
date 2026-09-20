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

    private static func storeWithMockTransport() -> ActivityStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ActivityStoreRunsTests.fichero",
            session: session
        )
        let service = ActivityService(ficheroClient: client)
        return ActivityStore(service: service)
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
        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: bufferSize)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }
}
