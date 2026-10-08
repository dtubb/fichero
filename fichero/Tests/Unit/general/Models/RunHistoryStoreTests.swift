//
//  RunHistoryStoreTests.swift
//  FicheroTests
//
//  #5434 (`activity.document.what-has-been-run`): the document Inspector's "What has been run"
//  reads `GET /api/documents/run-history?ids=…` through the generated client, in ONE call for many
//  documents, and shows each entry as the engine recorded it, newest first: what, the model, when,
//  the outcome, the cost when priced. Driven through the real store and the generated client's real
//  decoding against a stub scoped to this suite's own host; the JSON is the engine's response shape
//  (`RunHistoryResponse` in the committed openapi.json).
//
//  Not covered: the section drawn in a real Inspector (no mounted-view harness in this target).
//

@testable import Fichero
import FicheroAPIClient
import XCTest

private final class RunHistoryMockURLProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var answer: (Int, String) = (404, #"{"detail":"no stub"}"#)
    nonisolated(unsafe) private static var log: [URLRequest] = []

    static func reset(status: Int, json: String) {
        lock.lock()
        answer = (status, json)
        log = []
        lock.unlock()
    }

    static func recorded() -> [URLRequest] {
        lock.lock()
        defer { lock.unlock() }
        return log
    }

    // swiftlint:disable:next static_over_final_class
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "runhistory.test"
    }

    // swiftlint:disable:next static_over_final_class
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else { return }
        Self.lock.lock()
        Self.log.append(request)
        let (status, json) = Self.answer
        Self.lock.unlock()
        guard let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1",
                                             headerFields: ["Content-Type": "application/json"]) else { return }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@MainActor
final class RunHistoryStoreTests: XCTestCase {
    /// Two documents' histories as the engine answers them, newest first: a failed page read and a
    /// priced workflow run on the first, nothing on the second.
    private static let twoDocuments = """
    {"items": {
      "doc-1": [
        {"document_id": "doc-1", "source": "job", "kind": "read-a-page", "name": "Read the page",
         "state": "failed", "reason": "the provider refused this letter", "model": "gpt-5",
         "provider": null, "cost": null, "at": "2026-10-08T09:14:00Z", "job_id": "job-3",
         "parent_id": null, "workflow_id": null, "thread_id": null},
        {"document_id": "doc-1", "source": "workflow_run", "kind": "workflow", "name": "Transcribe",
         "state": "done", "reason": null, "model": "claude-sonnet", "provider": "anthropic",
         "cost": 0.0225, "at": "2026-10-07T16:02:00Z", "job_id": null, "parent_id": null,
         "workflow_id": "wf-1", "thread_id": "thread-2"}
      ],
      "doc-2": []
    }, "withheld": 0}
    """

    private func makeStore() -> RunHistoryStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RunHistoryMockURLProtocol.self]
        return RunHistoryStore(client: FicheroClient(
            baseURL: URL(string: "https://runhistory.test")!,
            libraryPath: "/tmp/RunHistoryStoreTests.fichero",
            session: URLSession(configuration: configuration)
        ))
    }

    override func setUp() {
        super.setUp()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
    }

    /// WHY: "the read is batched for the visible rows, never one call per row"; a store that asked
    /// once per document would make a table of a thousand rows a thousand calls.
    func testManyDocumentsAreOneCallAndEachGetsItsOwnHistory() async throws {
        RunHistoryMockURLProtocol.reset(status: 200, json: Self.twoDocuments)
        let store = makeStore()

        await store.load(documentIds: ["doc-2", "doc-1", "doc-1"])

        let requests = RunHistoryMockURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "many documents are one read")
        let url = try XCTUnwrap(requests.first?.url)
        XCTAssertEqual(url.path, "/api/documents/run-history")
        let ids = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
            .filter { $0.name == "ids" }.compactMap(\.value)
        XCTAssertEqual(ids, ["doc-1", "doc-2"], "each document is asked for once")
        XCTAssertEqual(store.history(documentId: "doc-1")?.map(\.name), ["Read the page", "Transcribe"],
                       "newest first, in the engine's order")
        XCTAssertEqual(store.history(documentId: "doc-2"), [], "a document with nothing run reads as empty, not unread")
        XCTAssertNil(store.history(documentId: "doc-3"), "a document not asked for is not read")
    }

    /// WHY: each entry gives "the model, the provider, the time, the cost (null unless priced) and
    /// the outcome, as recorded when the step ran"; a cost shown for an unpriced run would be invented.
    func testAnEntrySaysWhatModelWhenOutcomeAndCostOnlyWhenPriced() async throws {
        RunHistoryMockURLProtocol.reset(status: 200, json: Self.twoDocuments)
        let store = makeStore()

        await store.load(documentIds: ["doc-1"])

        let entries = try XCTUnwrap(store.history(documentId: "doc-1"))
        let read = entries[0]
        XCTAssertEqual(read.id, "job-3")
        XCTAssertEqual(read.outcomeText, "Failed")
        XCTAssertTrue(read.isFailed)
        XCTAssertEqual(read.reason, "the provider refused this letter")
        XCTAssertEqual(read.modelText, "gpt-5", "a job row records its model only")
        XCTAssertNil(read.costText, "an unpriced entry shows no cost")
        XCTAssertEqual(read.when, ISO8601DateFormatter().date(from: "2026-10-08T09:14:00Z"))
        let run = entries[1]
        XCTAssertEqual(run.id, "thread-2")
        XCTAssertEqual(run.outcomeText, "Done")
        XCTAssertEqual(run.modelText, "claude-sonnet · anthropic")
        XCTAssertEqual(run.costText, "$0.0225")
    }

    /// WHY: a failed read must say why, and must not blank what the section already showed.
    func testAFailedReadSaysWhyAndKeepsWhatWasShown() async throws {
        RunHistoryMockURLProtocol.reset(status: 200, json: Self.twoDocuments)
        let store = makeStore()
        await store.load(documentIds: ["doc-1"])
        let before = store.history(documentId: "doc-1")

        RunHistoryMockURLProtocol.reset(status: 409, json: #"{"detail":"The project is not open."}"#)
        await store.load(documentIds: ["doc-1"])

        XCTAssertEqual(store.history(documentId: "doc-1"), before, "a failed read keeps what was shown")
        XCTAssertEqual(store.failures["doc-1"], "The project is not open.", "the engine's words")
    }
}
