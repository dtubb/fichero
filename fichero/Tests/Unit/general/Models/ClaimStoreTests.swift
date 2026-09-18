@testable import Fichero
import FicheroAPIClient
import XCTest

/// #4824 (second batch) — `ClaimStore.delete`/`.setCuration`/`.merge`/`.link`
/// used to call `await reload()` (a full server re-fetch) after every
/// mutation. `.patch` was already correct (Aug 3) and is untouched here.
///
/// `delete` had a latent bug beyond the wholesale reload: the old loop threw
/// on the FIRST failed id without catching, so `reload()` at the end was
/// never reached on a partial failure — claims already deleted stayed
/// visibly present until some unrelated later reload. The fix (splice
/// per-success, inside the loop) closes that gap too, tested explicitly
/// below (3 ids, the 2nd fails).
///
/// First tests for this store. Mock transport copied locally (not shared).
/// Every stub body includes every field each response schema's `required`
/// list demands (checked against `openapi.json` before writing, per the
/// checklist addition from the first #4824 batch's gate failure).
@MainActor
final class ClaimStoreTests: XCTestCase {

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

    private static func storeWithMockTransport() -> ClaimStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ClaimStoreTests.fichero",
            session: session
        )
        return ClaimStore(
            entityService: EntityService(ficheroClient: client),
            kgCurationService: KGCurationService(ficheroClient: client),
            libraryPath: "/tmp/ClaimStoreTests.fichero"
        )
    }

    /// `KnowledgeClaim` requires only `text` — everything else optional.
    private static func claimJSON(id: String, text: String = "hello", curationState: String? = nil) -> [String: Any] {
        var fields: [String: Any] = ["id": id, "text": text]
        if let curationState { fields["curation_state"] = curationState }
        return fields
    }

    /// A store scoped to document "doc-1" and already holding three claims.
    private static func storeWithThreeClaims() async -> ClaimStore {
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/claims", method: "GET", status: 200,
                // `ClaimListResponse` is a WRAPPED `{items, count}` object (both
                // required), not a bare array — a bare array fails to decode and
                // the seed silently loads nothing.
                body: try! JSONSerialization.data(withJSONObject: [
                    "items": [claimJSON(id: "c1"), claimJSON(id: "c2"), claimJSON(id: "c3")],
                    "count": 3
                ] as [String: Any])
            )
        ])
        let store = Self.storeWithMockTransport()
        await store.loadClaims(forDocument: "doc-1")
        XCTAssertEqual(store.claims.count, 3, "test setup must seed exactly three claims")
        MockTransportURLProtocol.reset([])
        return store
    }

    // MARK: - delete: per-success splice, incl. the latent partial-failure fix

    func testDeleteRemovesEachSucceededIdInPlaceWithoutReload() async throws {
        let store = await Self.storeWithThreeClaims()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/claims/c1", method: "DELETE", status: 204, body: Data())
        ])

        try await store.delete(claimIds: ["c1"])

        XCTAssertFalse(store.claims.contains { $0.id == "c1" })
        XCTAssertEqual(store.claims.count, 2)
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the DELETE — no list re-fetch")
    }

    /// THE latent-bug regression: 3 ids requested, the 2nd fails. The 1st
    /// must be gone (its delete succeeded before the failure), the 2nd and
    /// 3rd must remain, and the error must surface exactly as it does today
    /// (the throw propagates, aborting the batch at the failure).
    func testDeletePartialFailureRemovesOnlyTheSucceededPrefix() async throws {
        let store = await Self.storeWithThreeClaims()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/claims/c1", method: "DELETE", status: 204, body: Data()),
            Stub(pathContains: "/api/claims/c2", method: "DELETE", status: 422, body: Data(#"{"detail":"nope"}"#.utf8))
            // c3's DELETE is never reached — the loop aborts at c2's throw.
        ])

        do {
            try await store.delete(claimIds: ["c1", "c2", "c3"])
            XCTFail("expected the 2nd delete to throw and abort the batch")
        } catch {
            // Expected — same throw-on-first-failure contract as before.
        }

        XCTAssertFalse(store.claims.contains { $0.id == "c1" }, "c1 succeeded before the failure — must be gone")
        XCTAssertTrue(store.claims.contains { $0.id == "c2" }, "c2's own delete failed — must remain")
        XCTAssertTrue(store.claims.contains { $0.id == "c3" }, "c3 was never attempted — must remain")
        XCTAssertEqual(store.claims.count, 2)
    }

    // MARK: - setCuration: splice only server-confirmed ids

    func testSetCurationSplicesOnlyTheServerConfirmedIds() async throws {
        let store = await Self.storeWithThreeClaims()
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/kg/claims/batch-curation", method: "PATCH", status: 200,
                body: try! JSONSerialization.data(withJSONObject: [
                    "updated": 1, "claim_ids": ["c1"]
                    // c2 was requested too, but the server did NOT confirm it —
                    // must not be painted.
                ])
            )
        ])

        try await store.setCuration(claimIds: ["c1", "c2"], to: .shortlisted)

        XCTAssertEqual(store.claims.first { $0.id == "c1" }?.curationState, .shortlisted)
        XCTAssertNotEqual(store.claims.first { $0.id == "c2" }?.curationState, .shortlisted, "c2 was never confirmed by the server")
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the PATCH — no list re-fetch")
    }

    func testSetCurationFallsBackToTheRequestedIdsWhenCountMatchesAndNoIdListIsGiven() async throws {
        let store = await Self.storeWithThreeClaims()
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/kg/claims/batch-curation", method: "PATCH", status: 200,
                body: try! JSONSerialization.data(withJSONObject: ["updated": 2])
                // No claim_ids, but updated == requested.count — safe to trust the request.
            )
        ])

        try await store.setCuration(claimIds: ["c1", "c2"], to: .curated)

        XCTAssertEqual(store.claims.first { $0.id == "c1" }?.curationState, .curated)
        XCTAssertEqual(store.claims.first { $0.id == "c2" }?.curationState, .curated)
    }

    func testSetCurationFallsBackToReloadWhenCountIsAmbiguous() async throws {
        let store = await Self.storeWithThreeClaims()
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/kg/claims/batch-curation", method: "PATCH", status: 200,
                body: try! JSONSerialization.data(withJSONObject: ["updated": 1])
                // No claim_ids AND updated != requested.count (2) — genuinely
                // ambiguous which one id succeeded. Must not guess.
            ),
            Stub(
                pathContains: "/api/claims", method: "GET", status: 200,
                body: try! JSONSerialization.data(withJSONObject: [
                    "items": [
                        Self.claimJSON(id: "c1", curationState: "curated"),
                        Self.claimJSON(id: "c2"),
                        Self.claimJSON(id: "c3")
                    ],
                    "count": 3
                ] as [String: Any])
            )
        ])

        try await store.setCuration(claimIds: ["c1", "c2"], to: .curated)

        // The fallback reload's own server response is what decides state
        // here — not a client-side guess.
        XCTAssertEqual(store.claims.first { $0.id == "c1" }?.curationState, .curated)
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 2, "the PATCH plus the fallback reload's GET")
    }

    // MARK: - merge: not one-item — remove absorbed, splice the fresh survivor

    private static func auditJSON(sourceIds: [String], targetId: String) -> Data {
        try! JSONSerialization.data(withJSONObject: [
            "id": "audit-1", "operation_type": "merge",
            "source_claim_ids": sourceIds, "target_claim_id": targetId,
            "reversal_id": NSNull(), "created_by": "test", "created_at": "2026-09-18T00:00:00Z"
        ])
    }

    func testMergeRemovesAbsorbedAndSplicesTheFreshSurvivor() async throws {
        let store = await Self.storeWithThreeClaims()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/kg/claims/merge", method: "POST", status: 200,
                 body: Self.auditJSON(sourceIds: ["c2"], targetId: "c1")),
            Stub(pathContains: "/api/claims/c1", method: "GET", status: 200,
                 body: try! JSONSerialization.data(withJSONObject: Self.claimJSON(id: "c1", text: "merged text")))
        ])

        _ = try await store.merge(absorbedIds: ["c2"], into: "c1")

        XCTAssertFalse(store.claims.contains { $0.id == "c2" }, "the absorbed claim must be removed")
        XCTAssertEqual(store.claims.first { $0.id == "c1" }?.text, "merged text", "the survivor must be refreshed")
        XCTAssertEqual(store.claims.count, 2)
    }

    func testMergeSurvivorFetchFailureKeepsAbsorbedRemovedAndSurvivorUnchanged() async throws {
        let store = await Self.storeWithThreeClaims()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/kg/claims/merge", method: "POST", status: 200,
                 body: Self.auditJSON(sourceIds: ["c2"], targetId: "c1")),
            Stub(pathContains: "/api/claims/c1", method: "GET", status: 422, body: Data(#"{"detail":"nope"}"#.utf8))
        ])

        _ = try await store.merge(absorbedIds: ["c2"], into: "c1")

        XCTAssertFalse(store.claims.contains { $0.id == "c2" }, "the merge itself succeeded — absorbed stays removed")
        XCTAssertEqual(store.claims.first { $0.id == "c1" }?.text, "hello", "a failed refresh must not resurrect or corrupt the survivor row")
    }

    func testMergeSkipsTheFetchWhenSurvivorIsOutOfTheCurrentScope() async throws {
        let store = await Self.storeWithThreeClaims()
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/kg/claims/merge", method: "POST", status: 200,
                 body: Self.auditJSON(sourceIds: ["c2"], targetId: "survivor-elsewhere"))
        ])

        _ = try await store.merge(absorbedIds: ["c2"], into: "survivor-elsewhere")

        XCTAssertFalse(store.claims.contains { $0.id == "c2" })
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "no GET — the survivor isn't in this scope, nothing to refresh")
    }

    // MARK: - link: no list change, changeToken bumps synchronously instead of a reload

    func testLinkBumpsChangeTokenAndFiresNoListRefetch() async throws {
        let store = await Self.storeWithThreeClaims()
        let tokenBefore = store.changeToken
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/claims/c1/links", method: "POST", status: 200,
                body: try! JSONSerialization.data(withJSONObject: [
                    "claim_id": "c1", "related_claim_id": "c2", "relation_type": "supports"
                ])
            )
        ])

        _ = try await store.link(claimId: "c1", relatedClaimId: "c2", relationType: .supports)

        XCTAssertEqual(store.changeToken, tokenBefore + 1, "changeToken must bump so bespoke consumers resync")
        XCTAssertEqual(store.claims.count, 3, "linking must not change the claims list itself")
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the link's own POST — no list re-fetch")
    }
}
