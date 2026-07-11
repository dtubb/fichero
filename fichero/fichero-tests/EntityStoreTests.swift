@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

// swiftlint:disable file_length
@MainActor
// swiftlint:disable:next type_body_length
final class EntityStoreTests: XCTestCase {
    private struct MockResponse {
        let method: String
        let path: String
        let statusCode: Int
        let body: Data
    }

    private final class MockFicheroURLProtocol: URLProtocol {
        private static let lock = NSLock()
        // ponytail: keyed by (method, path) and NON-consuming — a request is
        // served the response matching its method+path, regardless of arrival
        // order or how many times it fires. This makes the mock immune to the
        // late/stray async URLSession callbacks that previously starved the
        // FIFO queue across serial test methods (the flaky #2289 EntityStore
        // failures). Unmatched requests get a benign 404, never a hard failure.
        nonisolated(unsafe) private static var responses: [MockResponse] = []
        nonisolated(unsafe) private static var requests: [URLRequest] = []

        static func configure(responses: [MockResponse]) {
            lock.lock()
            self.responses = responses
            requests = []
            lock.unlock()
        }

        static func recordedRequests() -> [URLRequest] {
            lock.lock()
            defer { lock.unlock() }
            return requests
        }

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            guard let host = request.url?.host else { return false }
            return host == "127.0.0.1" && request.url?.path.hasPrefix("/api/") == true
        }

        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest {
            request
        }

        override func startLoading() {
            let method = request.httpMethod ?? "GET"
            let path = request.url?.path ?? ""
            Self.lock.lock()
            Self.requests.append(request)
            let match = Self.responses.first { $0.method == method && $0.path == path }
            Self.lock.unlock()

            // Unmatched (e.g. a late/stray request from another test) → benign
            // 404 so it can never starve a real test's response.
            let response = match ?? MockResponse(method: method, path: path, statusCode: 404, body: Data())

            let httpResponse = HTTPURLResponse(
                url: request.url!,
                statusCode: response.statusCode,
                httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: httpResponse, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: response.body)
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}
    }

    private static let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    // swiftlint:disable:next static_over_final_class
    override class func setUp() {
        super.setUp()
        URLProtocol.registerClass(MockFicheroURLProtocol.self)
    }

    // swiftlint:disable:next static_over_final_class
    override class func tearDown() {
        URLProtocol.unregisterClass(MockFicheroURLProtocol.self)
        super.tearDown()
    }

    override func setUp() async throws {
        try await super.setUp()
        ensureAPIKeyFileExists()
        MockFicheroURLProtocol.configure(responses: [])
    }

    func testRenamePatchesMatchingRowWithoutReloadingList() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
                    method: "GET", path: "/api/documents/doc-1/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [
                            makeEntityJSON(id: "entity-1", name: "Alpha"),
                            makeEntityJSON(id: "entity-2", name: "Beta")
                        ]
                    )
                ),
                .init(
                    method: "PATCH", path: "/api/entities/entity-1",
                    statusCode: 200,
                    body: makeEntityResponse(id: "entity-1", name: "Alpha Prime")
                )
            ]
        )

        let store = makeStore()
        await store.loadEntities(forDocument: "doc-1")

        let updated = try await store.rename(entityId: "entity-1", to: "Alpha Prime")

        XCTAssertEqual(updated.canonicalName, "Alpha Prime")
        XCTAssertEqual(store.entities.compactMap(\.id), ["entity-1", "entity-2"])
        XCTAssertEqual(store.entities.map(\.canonicalName), ["Alpha Prime", "Beta"])

        let requests = MockFicheroURLProtocol.recordedRequests()
        XCTAssertTrue(requests.contains { $0.httpMethod == "GET" && $0.url?.path == "/api/documents/doc-1/inspector" })
        XCTAssertTrue(requests.contains { $0.httpMethod == "PATCH" && $0.url?.path == "/api/entities/entity-1" })
    }

    func testSetCurationUpdatesMatchingRowsInPlace() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
                    method: "GET", path: "/api/documents/doc-1/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [
                            makeEntityJSON(id: "entity-1", name: "Alpha"),
                            makeEntityJSON(id: "entity-2", name: "Beta"),
                            makeEntityJSON(id: "entity-3", name: "Gamma")
                        ]
                    )
                ),
                .init(
                    method: "PATCH", path: "/api/kg/entities/batch-curation",
                    statusCode: 200,
                    body: makeBatchCurationResponse(updated: 2, entityIDs: ["entity-1", "entity-3"])
                )
            ]
        )

        let store = makeStore()
        await store.loadEntities(forDocument: "doc-1")

        try await store.setCuration(entityIds: ["entity-1", "entity-3"], to: .verified)

        XCTAssertEqual(store.entities.compactMap(\.id), ["entity-1", "entity-2", "entity-3"])
        XCTAssertEqual(store.entities.map(\.curationState), [.verified, nil, .verified])

        let requests = MockFicheroURLProtocol.recordedRequests()
        XCTAssertTrue(requests.contains { $0.httpMethod == "GET" && $0.url?.path == "/api/documents/doc-1/inspector" })
        XCTAssertTrue(requests.contains { $0.httpMethod == "PATCH" && $0.url?.path == "/api/kg/entities/batch-curation" })
    }

    func testDeleteRemovesMatchingRowsInPlace() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
                    method: "GET", path: "/api/documents/doc-1/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [
                            makeEntityJSON(id: "entity-1", name: "Alpha"),
                            makeEntityJSON(id: "entity-2", name: "Beta")
                        ]
                    )
                ),
                .init(method: "DELETE", path: "/api/entities/entity-1", statusCode: 204, body: Data())
            ]
        )

        let store = makeStore()
        await store.loadEntities(forDocument: "doc-1")

        try await store.delete(entityIds: ["entity-1"])

        XCTAssertEqual(store.entities.compactMap(\.id), ["entity-2"])
        XCTAssertEqual(store.entities.map(\.canonicalName), ["Beta"])

        let requests = MockFicheroURLProtocol.recordedRequests()
        XCTAssertTrue(requests.contains { $0.httpMethod == "GET" && $0.url?.path == "/api/documents/doc-1/inspector" })
        XCTAssertTrue(requests.contains { $0.httpMethod == "DELETE" && $0.url?.path == "/api/entities/entity-1" })
    }

    func testLibraryWideLoadOwnsOntologyBrowserEntityListAndCounts() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
                    method: "GET", path: "/api/entities",
                    statusCode: 200,
                    body: jsonData([
                        "items": [
                            makeEntityJSON(id: "entity-1", name: "Alpha")
                        ],
                        "total": 1
                    ])
                ),
                .init(
                    method: "GET", path: "/api/entities/claim-counts",
                    statusCode: 200,
                    body: jsonData([
                        "counts": [
                            "entity-1": 3
                        ]
                    ])
                ),
                .init(
                    method: "GET", path: "/api/documents/doc-1/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [makeEntityJSON(id: "entity-2", name: "Beta")]
                    )
                )
            ]
        )

        let store = makeStore()
        await store.loadEntities(query: " Alpha ", limit: 100)

        XCTAssertEqual(store.libraryEntities.compactMap(\.id), ["entity-1"])
        XCTAssertEqual(store.libraryClaimCounts["entity-1"], 3)

        await store.loadEntities(forDocument: "doc-1")
        XCTAssertEqual(store.entities.compactMap(\.id), ["entity-2"])
        XCTAssertEqual(store.libraryEntities.compactMap(\.id), ["entity-1"])

        let requests = MockFicheroURLProtocol.recordedRequests()
        XCTAssertTrue(requests.contains { request in
            request.httpMethod == "GET"
                && request.url?.path == "/api/entities"
                && request.url?.query?.contains("q=Alpha") == true
        })
        XCTAssertTrue(requests.contains { $0.httpMethod == "GET" && $0.url?.path == "/api/entities/claim-counts" })
    }

    func testReclassifyReloadsCurrentInspectorScopeAfterPatch() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
                    method: "GET", path: "/api/documents/doc-1/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [
                            makeEntityJSON(id: "entity-1", name: "Alpha", type: "location")
                        ]
                    )
                ),
                .init(
                    method: "PATCH", path: "/api/entities/entity-1",
                    statusCode: 200,
                    body: makeEntityResponse(id: "entity-1", name: "Alpha", type: "person")
                ),
                .init(
                    method: "GET", path: "/api/documents/doc-1/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [
                            makeEntityJSON(id: "entity-1", name: "Alpha", type: "person")
                        ]
                    )
                )
            ]
        )

        let store = makeStore()
        await store.loadEntities(forDocument: "doc-1")

        _ = try await store.reclassify(entityId: "entity-1", to: "person")

        XCTAssertEqual(store.entities.first?.entityType, .person)

        let requests = MockFicheroURLProtocol.recordedRequests()
        XCTAssertTrue(requests.contains { $0.httpMethod == "PATCH" && $0.url?.path == "/api/entities/entity-1" })
        XCTAssertGreaterThanOrEqual(
            requests.filter { $0.httpMethod == "GET" && $0.url?.path == "/api/documents/doc-1/inspector" }.count,
            2
        )
    }

    func testMergeReloadsCurrentInspectorScopeAfterBackendMerge() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
                    method: "GET", path: "/api/documents/doc-1/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [
                            makeEntityJSON(id: "entity-1", name: "Alpha"),
                            makeEntityJSON(id: "entity-2", name: "Alpha Alt"),
                            makeEntityJSON(id: "entity-3", name: "Alpha Alias")
                        ]
                    )
                ),
                .init(
                    method: "POST", path: "/api/kg/entity-curation/merge",
                    statusCode: 200,
                    body: makeMergeAuditResponse(
                        survivorId: "entity-1",
                        absorbedIds: ["entity-2", "entity-3"]
                    )
                ),
                .init(
                    method: "GET", path: "/api/documents/doc-1/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [
                            makeEntityJSON(id: "entity-1", name: "Alpha Prime")
                        ]
                    )
                )
            ]
        )

        let store = makeStore()
        await store.loadEntities(forDocument: "doc-1")

        try await store.merge(absorbedIds: ["entity-2", "entity-3"], into: "entity-1")

        XCTAssertEqual(store.entities.compactMap(\.id), ["entity-1"])
        XCTAssertEqual(store.entities.map(\.canonicalName), ["Alpha Prime"])

        let requests = MockFicheroURLProtocol.recordedRequests()
        XCTAssertTrue(requests.contains { $0.httpMethod == "POST" && $0.url?.path == "/api/kg/entity-curation/merge" })
        XCTAssertGreaterThanOrEqual(
            requests.filter { $0.httpMethod == "GET" && $0.url?.path == "/api/documents/doc-1/inspector" }.count,
            2
        )
    }

    func testDocumentBucketsKeepSeparateInspectorScopesPerDocument() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
                    method: "GET", path: "/api/documents/doc-1/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        documentId: "doc-1",
                        entities: [makeEntityJSON(id: "entity-1", name: "Alpha")]
                    )
                ),
                .init(
                    method: "GET", path: "/api/documents/doc-2/inspector",
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        documentId: "doc-2",
                        entities: [makeEntityJSON(id: "entity-2", name: "Beta")]
                    )
                )
            ]
        )

        let store = makeStore()
        await store.loadEntities(forDocument: "doc-1")
        await store.loadEntities(forDocument: "doc-2")

        XCTAssertEqual(store.entities(forDocument: "doc-1").map(\.canonicalName), ["Alpha"])
        XCTAssertEqual(store.entities(forDocument: "doc-2").map(\.canonicalName), ["Beta"])
        XCTAssertEqual(store.entities.map(\.canonicalName), ["Beta"])
    }

    private func makeStore() -> EntityStore {
        let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/test.fichero")
        let entityService = EntityServiceGenerated(ficheroClient: client)
        let kgCurationService = KGCurationServiceGenerated(ficheroClient: client)
        return EntityStore(
            entityService: entityService,
            kgCurationService: kgCurationService,
            libraryPath: "/tmp/test.fichero"
        )
    }

    private func ensureAPIKeyFileExists() {
        guard let appSupport = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first else {
            return
        }

        let tokenDir = appSupport.appendingPathComponent("Fichero", isDirectory: true)
        let tokenFile = tokenDir.appendingPathComponent(".api-key")
        try? FileManager.default.createDirectory(at: tokenDir, withIntermediateDirectories: true)
        try? Data("test-token\n".utf8).write(to: tokenFile, options: [.atomic])
    }

    private func makeDocumentInspectorResponse(
        documentId: String = "doc-1",
        entities: [[String: Any]]
    ) -> Data {
        let payload: [String: Any] = [
            "document_id": documentId,
            "document": [:],
            "source_metadata": [:],
            "claim_count": 0,
            "claims": [],
            "entities": entities,
            "annotations": [],
            "notes": [],
            "citations_outbound": [],
            "citations_inbound": [],
            "interpretations": [],
            "projects": []
        ]
        return jsonData(payload)
    }

    private func makeEntityResponse(id: String, name: String, type: String? = nil) -> Data {
        jsonData(makeEntityJSON(id: id, name: name, type: type))
    }

    private func makeBatchCurationResponse(updated: Int, entityIDs: [String]) -> Data {
        let payload: [String: Any] = [
            "updated": updated,
            "entity_ids": entityIDs
        ]
        return jsonData(payload)
    }

    private func makeMergeAuditResponse(survivorId: String, absorbedIds: [String]) -> Data {
        let payload: [String: Any] = [
            "id": "audit-1",
            "operation_type": "merge",
            "source_entity_ids": absorbedIds,
            "target_entity_id": survivorId,
            "alias_changes": [:],
            "reversal_id": NSNull(),
            "created_by": "human",
            "created_at": Self.isoFormatter.string(from: Date(timeIntervalSince1970: 1_700_000_000))
        ]
        return jsonData(payload)
    }

    private func makeEntityJSON(
        id: String,
        name: String,
        type: String? = nil,
        curationState: Components.Schemas.EntityCurationState? = nil
    ) -> [String: Any] {
        var payload: [String: Any] = [
            "id": id,
            "canonical_name": name,
            "created_at": Self.isoFormatter.string(from: Date(timeIntervalSince1970: 1_700_000_000)),
            "updated_at": Self.isoFormatter.string(from: Date(timeIntervalSince1970: 1_700_000_000))
        ]
        if let type {
            payload["entity_type"] = type
        }
        if let curationState {
            payload["curation_state"] = curationState.rawValue
        }
        return payload
    }

    private func jsonData(_ object: Any) -> Data {
        (try? JSONSerialization.data(withJSONObject: object)) ?? Data()
    }

    // MARK: - Folder aggregation union (#3450)

    private func aggEntity(id: String?, name: String) -> Components.Schemas.KnowledgeEntity {
        Components.Schemas.KnowledgeEntity(
            id: id,
            canonicalName: name,
            entityType: .person,
            aliases: nil,
            description: nil,
            language: nil,
            metadata: nil,
            mergedIntoId: nil
        )
    }

    func testUnionDedupesByEntityIdPreservingFirstSeenOrder() {
        let folder = [aggEntity(id: "e1", name: "Ada"), aggEntity(id: "e2", name: "Grace")]
        let childA = [aggEntity(id: "e2", name: "Grace"), aggEntity(id: "e3", name: "Alan")]
        let childB = [aggEntity(id: "e1", name: "Ada")]

        let merged = EntityStore.union([folder, childA, childB])

        // e1, e2, e3 — each once, in first-seen order across the folder + children.
        XCTAssertEqual(merged.map(\.id), ["e1", "e2", "e3"])
    }

    func testUnionFallsBackToTypeNameKeyForIdlessEntities() {
        // Two not-yet-persisted entities with the same type+name collapse to one.
        let merged = EntityStore.union([
            [aggEntity(id: nil, name: "Ada")],
            [aggEntity(id: nil, name: "Ada"), aggEntity(id: nil, name: "Grace")]
        ])
        XCTAssertEqual(merged.map(\.canonicalName), ["Ada", "Grace"])
    }
}
