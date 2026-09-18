@testable import Fichero
import FicheroAPIClient
import XCTest

/// #4824 — `ArtifactStore.delete` used to track only a FAILURE COUNT and then
/// call `await reload()` unconditionally (a full server re-fetch), discarding
/// which ids actually succeeded. It now tracks `succeededIds` and splices
/// only those out of `items` in place — a failed delete keeps its row by
/// construction, never by an incidental server round-trip.
///
/// `update(id:documentId:content:)` was ALREADY the correct in-place-splice
/// pattern (`items[index] = updated`, no reload) — this is its first
/// regression test, added alongside `delete`'s.
///
/// First tests for this store. Mock transport copied locally (not shared).
@MainActor
final class ArtifactStoreTests: XCTestCase {

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
            // Runtime values (the loaded request's own URL, the constructed
            // response) — a force-unwrap here would crash the whole test
            // host on a malformed fixture, not just fail one test. Fail the
            // individual load instead.
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

    private static func storeWithMockTransport() -> ArtifactStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ArtifactStoreTests.fichero",
            session: session
        )
        let service = ArtifactService(ficheroClient: client)
        return ArtifactStore(artifactService: service)
    }

    private static func artifactJSON(id: String, documentId: String) -> [String: Any] {
        [
            "id": id, "document_id": documentId, "artifact_type": "transcription",
            "version": 1, "reviewed": false, "created_at": "2026-09-18T00:00:00Z"
        ]
    }

    /// A store scoped to "doc-1" and already holding two artifacts —
    /// seeded via the same `setScope` path a real caller uses.
    private static func storeWithTwoArtifacts() async -> ArtifactStore {
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/artifacts/document/doc-1", method: "GET", status: 200,
                body: try! JSONSerialization.data(withJSONObject: [
                    "items": [artifactJSON(id: "art-1", documentId: "doc-1"), artifactJSON(id: "art-2", documentId: "doc-1")],
                    // `ArtifactListResponse` REQUIRES `count`; without it the generated
                    // client fails to decode and the seed silently loads nothing.
                    "count": 2
                ])
            )
        ])
        let store = Self.storeWithMockTransport()
        await store.setScope(documentId: "doc-1")
        XCTAssertEqual(store.items.count, 2, "test setup must seed exactly two artifacts")
        MockTransportURLProtocol.reset([])
        return store
    }

    // MARK: - delete: mixed success/failure

    func testDeleteMixedSuccessAndFailureOnlyRemovesTheSucceededId() async throws {
        let store = await Self.storeWithTwoArtifacts()
        let art1 = try XCTUnwrap(store.items.first { $0.id == "art-1" })
        let art2 = try XCTUnwrap(store.items.first { $0.id == "art-2" })

        // art-1 deletes fine; art-2's DELETE fails.
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/artifacts/art-1", method: "DELETE", status: 204, body: Data()),
            Stub(pathContains: "/api/artifacts/art-2", method: "DELETE", status: 422, body: Data(#"{"detail":"nope"}"#.utf8))
        ])

        let failedCount = await store.delete([art1, art2])

        XCTAssertEqual(failedCount, 1, "exactly one delete failed")
        XCTAssertFalse(store.items.contains { $0.id == "art-1" }, "the succeeded delete must remove its row")
        XCTAssertTrue(store.items.contains { $0.id == "art-2" }, "the failed delete must keep its row")
        // No list re-fetch alongside the two DELETE calls.
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 2, "only the two DELETE requests — no GET re-fetch")
    }

    func testDeleteAllFailuresLeavesTheListCompletelyUntouched() async throws {
        let store = await Self.storeWithTwoArtifacts()
        let art1 = try XCTUnwrap(store.items.first { $0.id == "art-1" })
        let art2 = try XCTUnwrap(store.items.first { $0.id == "art-2" })

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/artifacts/art-1", method: "DELETE", status: 422, body: Data(#"{"detail":"nope"}"#.utf8)),
            Stub(pathContains: "/api/artifacts/art-2", method: "DELETE", status: 422, body: Data(#"{"detail":"nope"}"#.utf8))
        ])

        let failedCount = await store.delete([art1, art2])

        XCTAssertEqual(failedCount, 2)
        XCTAssertEqual(store.items.count, 2, "both rows must remain when every delete fails")
    }

    // MARK: - update: already-correct pattern, first regression test

    func testUpdateSplicesInPlaceByIndexPreservingTheOtherRow() async throws {
        let store = await Self.storeWithTwoArtifacts()
        let originalOrder = store.items.map(\.id)

        var updatedFields = Self.artifactJSON(id: "art-1", documentId: "doc-1")
        updatedFields["content"] = "edited content"
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/artifacts/art-1", method: "PUT", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: updatedFields))
        ])

        let updated = try await store.update(id: "art-1", documentId: "doc-1", content: "edited content")

        XCTAssertEqual(updated.content, "edited content")
        XCTAssertEqual(store.items.map(\.id), originalOrder, "update must not reorder the list")
        XCTAssertEqual(store.items.count, 2, "update must not change the list's length")
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the PUT — no list re-fetch")
    }
}
