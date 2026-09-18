@testable import Fichero
import FicheroAPIClient
import XCTest

/// #4824 (second batch) — `InterpretationStore.create`/`.update` used to
/// call `await reload()` after every mutation. The server's list route
/// (`GET /interpretations`, `hermeneutics.py:378-394`) issues no `ORDER BY` —
/// storage/insertion order, oldest first — and `DocumentInterpretationsSection`
/// renders `store.items` unsorted, so `create` must APPEND (not insert at 0)
/// to match what a real reload would have produced.
///
/// First tests for this store. Mock transport copied locally (not shared).
/// Every stub satisfies its response schema's `required` fields.
@MainActor
final class InterpretationStoreTests: XCTestCase {

    // MARK: - Mock transport (copied, not shared)

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
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: resolved.status,
                httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
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

    private static func storeWithMockTransport() -> InterpretationStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/InterpretationStoreTests.fichero",
            session: session
        )
        return InterpretationStore(entityService: EntityService(ficheroClient: client))
    }

    /// `Interpretation` requires `framework_id`, `interpretation_text`, `act`.
    private static func interpretationJSON(id: String, documentId: String, text: String = "a reading") -> [String: Any] {
        [
            "id": id, "framework_id": "fw-1", "document_id": documentId,
            "interpretation_text": text, "act": "reading", "confidence": 0.8
        ]
    }

    private static func storeScopedToDocument(_ documentId: String) async -> InterpretationStore {
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/hermeneutics/interpretations", method: "GET", status: 200,
                 // `InterpretationListResponse` REQUIRES `count` beside `items`.
                 body: try! JSONSerialization.data(withJSONObject: ["items": [], "count": 0] as [String: Any]))
        ])
        let store = Self.storeWithMockTransport()
        await store.setScope(documentId: documentId)
        XCTAssertTrue(store.items.isEmpty, "test setup must seed an empty scoped store")
        MockTransportURLProtocol.reset([])
        return store
    }

    // MARK: - create: appends, matching the server's insertion-order list

    func testCreateAppendsInPlaceWithoutReload() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/hermeneutics/interpretations", method: "POST", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: Self.interpretationJSON(id: "i1", documentId: "doc-1")))
        ])

        let created = try await store.create(
            frameworkId: "fw-1", documentId: "doc-1", act: .reading, text: "a reading", confidence: 0.8
        )

        XCTAssertEqual(created.id, "i1")
        XCTAssertEqual(store.items.last?.id, "i1", "must append, not insert at index 0")
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the create's own POST — no list re-fetch")
    }

    func testCreatePreservesOrderAcrossMultipleAppends() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/hermeneutics/interpretations", method: "POST", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: Self.interpretationJSON(id: "i1", documentId: "doc-1")))
        ])
        _ = try await store.create(frameworkId: "fw-1", documentId: "doc-1", act: .reading, text: "first", confidence: 0.8)

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/hermeneutics/interpretations", method: "POST", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: Self.interpretationJSON(id: "i2", documentId: "doc-1")))
        ])
        _ = try await store.create(frameworkId: "fw-1", documentId: "doc-1", act: .reading, text: "second", confidence: 0.8)

        XCTAssertEqual(store.items.map(\.id), ["i1", "i2"], "insertion order must be oldest-first, matching the server's own list order")
    }

    func testCreateSkipsAppendWhenTheInterpretationIsOutOfTheCurrentScope() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/hermeneutics/interpretations", method: "POST", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: Self.interpretationJSON(id: "i1", documentId: "doc-99")))
        ])

        let created = try await store.create(
            frameworkId: "fw-1", documentId: "doc-1", act: .reading, text: "misrouted", confidence: 0.8
        )

        XCTAssertEqual(created.id, "i1", "still returned to the caller")
        XCTAssertTrue(store.items.isEmpty, "an out-of-scope interpretation must not appear in the current list")
    }

    // MARK: - update: splices by index, mirrors ClaimStore.patch's fallback

    func testUpdateSplicesInPlaceByIndex() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/hermeneutics/interpretations", method: "POST", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: Self.interpretationJSON(id: "i1", documentId: "doc-1")))
        ])
        _ = try await store.create(frameworkId: "fw-1", documentId: "doc-1", act: .reading, text: "original", confidence: 0.8)

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/hermeneutics/interpretations/i1", method: "PATCH", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: Self.interpretationJSON(id: "i1", documentId: "doc-1", text: "edited")))
        ])
        let updated = try await store.update(interpretationId: "i1", text: "edited", confidence: 0.9)

        XCTAssertEqual(updated.interpretationText, "edited")
        XCTAssertEqual(store.items.count, 1, "update must not change the list's length")
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the PATCH — no list re-fetch")
    }

    func testUpdateFallsBackToReloadWhenTheIdIsAbsent() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        // Nothing created — "i1" is not in the list at all.
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/hermeneutics/interpretations/i1", method: "PATCH", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: Self.interpretationJSON(id: "i1", documentId: "doc-1", text: "edited"))),
            Stub(pathContains: "/api/hermeneutics/interpretations", method: "GET", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: [
                     "items": [Self.interpretationJSON(id: "i1", documentId: "doc-1", text: "edited")],
                     "count": 1
                 ] as [String: Any]))
        ])

        _ = try await store.update(interpretationId: "i1", text: "edited", confidence: 0.9)

        // The fallback reload is what actually populates the list here.
        XCTAssertEqual(store.items.count, 1)
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 2, "the PATCH plus the fallback reload's GET")
    }
}
