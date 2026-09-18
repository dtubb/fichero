@testable import Fichero
import FicheroAPIClient
import XCTest

/// #4824 — `AnnotationStore`'s mutators used to throw away
/// `AnnotationService`'s already-correct in-place splice (`insert`/`[idx] =`/
/// `removeAll`, all success-gated) by reassigning `annotations =
/// annotationService.annotations` wholesale right after. Unlike `NoteStore`'s
/// old `reload()` bug, this was never a NETWORK re-fetch — just a redundant
/// array copy — but it is still the shape the guardrail (correctly) flags,
/// and it is what the store's mutators now splice directly instead.
///
/// These are the FIRST tests for this store. Mock transport copied locally
/// (not shared, per this session's instruction). Same #4024 httpBody
/// limitation as the other new suites in this delivery.
@MainActor
final class AnnotationStoreTests: XCTestCase {

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
            // Runtime values — a force-unwrap here would crash the whole test
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

    private static func storeWithMockTransport() -> AnnotationStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/AnnotationStoreTests.fichero",
            session: session
        )
        let service = AnnotationService(ficheroClient: client)
        return AnnotationStore(annotationService: service)
    }

    /// A store already loaded (empty) for a document scope — the state a real
    /// caller is in before adding/editing/deleting an annotation in a
    /// document-scoped view.
    private static func storeScopedToDocument(_ documentId: String) async -> AnnotationStore {
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "GET", status: 200, body: Data(#"{"items":[],"count":0}"#.utf8))
        ])
        let store = Self.storeWithMockTransport()
        await store.loadAnnotations(for: .document(documentId))
        MockTransportURLProtocol.reset([])
        return store
    }

    private static func annotationJSON(id: String, documentId: String, kind: String = "note", text: String = "hi") -> Data {
        let fields: [String: Any] = [
            "id": id, "document_id": documentId, "kind": kind, "text": text,
            "tags": [], "linked_claim_ids": [], "linked_entity_ids": [], "linked_note_ids": []
        ]
        return try! JSONSerialization.data(withJSONObject: fields)
    }

    // MARK: - addNote splices in place

    func testAddNoteInsertsAtIndexZero() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "POST", status: 200, body: Self.annotationJSON(id: "a1", documentId: "doc-1"))
        ])

        let created = await store.addNote(scope: .document("doc-1"), text: "hello")

        XCTAssertEqual(created?.id, "a1")
        XCTAssertEqual(store.annotations.first?.id, "a1")
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the create's own POST — no list re-fetch")
    }

    func testAddNoteFailureLeavesTheListUntouched() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "POST", status: 422, body: Data(#"{"detail":"nope"}"#.utf8))
        ])

        let created = await store.addNote(scope: .document("doc-1"), text: "hello")

        XCTAssertNil(created)
        XCTAssertTrue(store.annotations.isEmpty, "a failed create must not add a row")
    }

    // MARK: - updateText splices by index

    func testUpdateTextSplicesInPlaceByIndex() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "POST", status: 200, body: Self.annotationJSON(id: "a1", documentId: "doc-1"))
        ])
        _ = await store.addNote(scope: .document("doc-1"), text: "original")
        XCTAssertEqual(store.annotations.count, 1)

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations/a1", method: "PATCH", status: 200,
                 body: Self.annotationJSON(id: "a1", documentId: "doc-1", text: "edited"))
        ])
        let updated = await store.updateText(id: "a1", text: "edited")

        XCTAssertEqual(updated?.text, "edited")
        XCTAssertEqual(store.annotations.count, 1, "update must not change the list's length")
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the PATCH — no list re-fetch")
    }

    func testUpdateTextFailureLeavesTheListUntouched() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "POST", status: 200, body: Self.annotationJSON(id: "a1", documentId: "doc-1", text: "original"))
        ])
        _ = await store.addNote(scope: .document("doc-1"), text: "original")

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations/a1", method: "PATCH", status: 422, body: Data(#"{"detail":"nope"}"#.utf8))
        ])
        let updated = await store.updateText(id: "a1", text: "edited")

        XCTAssertNil(updated)
        XCTAssertEqual(store.annotations.first?.text, "original", "a failed update must not touch the row")
    }

    // MARK: - delete removes in place

    func testDeleteRemovesInPlace() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "POST", status: 200, body: Self.annotationJSON(id: "a1", documentId: "doc-1"))
        ])
        _ = await store.addNote(scope: .document("doc-1"), text: "original")
        XCTAssertEqual(store.annotations.count, 1)

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations/a1", method: "DELETE", status: 204, body: Data())
        ])
        let success = await store.delete(id: "a1")

        XCTAssertTrue(success)
        XCTAssertTrue(store.annotations.isEmpty)
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the DELETE — no list re-fetch")
    }

    func testDeleteFailureLeavesTheListUntouched() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "POST", status: 200, body: Self.annotationJSON(id: "a1", documentId: "doc-1"))
        ])
        _ = await store.addNote(scope: .document("doc-1"), text: "original")

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations/a1", method: "DELETE", status: 422, body: Data(#"{"detail":"nope"}"#.utf8))
        ])
        let success = await store.delete(id: "a1")

        XCTAssertFalse(success)
        XCTAssertEqual(store.annotations.count, 1, "a failed delete must not remove the row")
    }

    // MARK: - getAnnotation merges (index update or insert)

    func testGetAnnotationUpdatesAnExistingRowByIndex() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "POST", status: 200, body: Self.annotationJSON(id: "a1", documentId: "doc-1", text: "original"))
        ])
        _ = await store.addNote(scope: .document("doc-1"), text: "original")

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations/a1", method: "GET", status: 200,
                 body: Self.annotationJSON(id: "a1", documentId: "doc-1", text: "refreshed"))
        ])
        let fetched = await store.getAnnotation(id: "a1")

        XCTAssertEqual(fetched?.text, "refreshed")
        XCTAssertEqual(store.annotations.count, 1, "must update in place, not append a duplicate")
        XCTAssertEqual(store.annotations.first?.text, "refreshed")
    }

    // MARK: - promoteToClaim merges the follow-up fetch

    func testPromoteToClaimMergesTheFollowUpFetchedCopy() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "POST", status: 200, body: Self.annotationJSON(id: "a1", documentId: "doc-1"))
        ])
        _ = await store.addNote(scope: .document("doc-1"), text: "original")

        MockTransportURLProtocol.reset([
            // `PromoteResponse` REQUIRES all three fields; an empty object fails to
            // decode and the service reports failure before the store logic runs.
            Stub(pathContains: "/promote-to-claim", method: "POST", status: 200,
                 body: Data(#"{"annotation_id":"a1","claim_id":"c1","claim_text":"promoted"}"#.utf8)),
            Stub(pathContains: "/api/annotations/a1", method: "GET", status: 200,
                 body: Self.annotationJSON(id: "a1", documentId: "doc-1", text: "promoted"))
        ])
        let success = await store.promoteToClaim(id: "a1")

        XCTAssertTrue(success)
        XCTAssertEqual(store.annotations.count, 1, "must merge in place, not duplicate the row")
        XCTAssertEqual(store.annotations.first?.text, "promoted")
    }

    func testPromoteToClaimFailureTouchesNothing() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/annotations", method: "POST", status: 200, body: Self.annotationJSON(id: "a1", documentId: "doc-1"))
        ])
        _ = await store.addNote(scope: .document("doc-1"), text: "original")

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/promote-to-claim", method: "POST", status: 422, body: Data(#"{"detail":"nope"}"#.utf8))
        ])
        let success = await store.promoteToClaim(id: "a1")

        XCTAssertFalse(success)
        // No follow-up getAnnotation fetch should have fired on a failed promote.
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "a failed promote must not attempt the follow-up merge fetch")
    }
}
