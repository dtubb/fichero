@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

@MainActor
// swiftlint:disable:next type_body_length
final class EntityStoreTests: XCTestCase {
    private struct MockResponse {
        let statusCode: Int
        let body: Data
    }

    private final class MockFicheroURLProtocol: URLProtocol {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var responseQueue: [MockResponse] = []
        nonisolated(unsafe) private static var requests: [URLRequest] = []

        static func configure(responses: [MockResponse]) {
            lock.lock()
            responseQueue = responses
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
            Self.lock.lock()
            Self.requests.append(request)
            let response = Self.responseQueue.isEmpty ? nil : Self.responseQueue.removeFirst()
            Self.lock.unlock()

            guard let response else {
                let description = "Unexpected request: \(request.httpMethod ?? "?") \(request.url?.path ?? "<nil>")"
                client?.urlProtocol(self, didFailWithError: NSError(
                    domain: "EntityStoreTests.MockFicheroURLProtocol",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: description]
                ))
                return
            }

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

    override func setUp() {
        super.setUp()
        ensureAPIKeyFileExists()
        MockFicheroURLProtocol.configure(responses: [])
    }

    func testRenamePatchesMatchingRowWithoutReloadingList() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [
                            makeEntityJSON(id: "entity-1", name: "Alpha"),
                            makeEntityJSON(id: "entity-2", name: "Beta")
                        ]
                    )
                ),
                .init(
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
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0].httpMethod, "GET")
        XCTAssertEqual(requests[0].url?.path, "/api/documents/doc-1/inspector")
        XCTAssertEqual(requests[1].httpMethod, "PATCH")
        XCTAssertEqual(requests[1].url?.path, "/api/entities/entity-1")
    }

    func testSetCurationUpdatesMatchingRowsInPlace() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
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
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0].httpMethod, "GET")
        XCTAssertEqual(requests[1].httpMethod, "PATCH")
        XCTAssertEqual(requests[1].url?.path, "/api/kg/entities/batch-curation")
    }

    func testDeleteRemovesMatchingRowsInPlace() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
                    statusCode: 200,
                    body: makeDocumentInspectorResponse(
                        entities: [
                            makeEntityJSON(id: "entity-1", name: "Alpha"),
                            makeEntityJSON(id: "entity-2", name: "Beta")
                        ]
                    )
                ),
                .init(statusCode: 204, body: Data())
            ]
        )

        let store = makeStore()
        await store.loadEntities(forDocument: "doc-1")

        try await store.delete(entityIds: ["entity-1"])

        XCTAssertEqual(store.entities.compactMap(\.id), ["entity-2"])
        XCTAssertEqual(store.entities.map(\.canonicalName), ["Beta"])

        let requests = MockFicheroURLProtocol.recordedRequests()
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0].httpMethod, "GET")
        XCTAssertEqual(requests[1].httpMethod, "DELETE")
        XCTAssertEqual(requests[1].url?.path, "/api/entities/entity-1")
    }

    func testMergeRemovesAbsorbedRowsAndRefreshesSurvivorInPlace() async throws {
        MockFicheroURLProtocol.configure(
            responses: [
                .init(
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
                    statusCode: 200,
                    body: makeMergeAuditResponse(
                        survivorId: "entity-1",
                        absorbedIds: ["entity-2", "entity-3"]
                    )
                ),
                .init(
                    statusCode: 200,
                    body: makeEntityResponse(id: "entity-1", name: "Alpha Prime")
                )
            ]
        )

        let store = makeStore()
        await store.loadEntities(forDocument: "doc-1")

        try await store.merge(absorbedIds: ["entity-2", "entity-3"], into: "entity-1")

        XCTAssertEqual(store.entities.compactMap(\.id), ["entity-1"])
        XCTAssertEqual(store.entities.map(\.canonicalName), ["Alpha Prime"])

        let requests = MockFicheroURLProtocol.recordedRequests()
        XCTAssertEqual(requests.count, 3)
        XCTAssertEqual(requests[0].httpMethod, "GET")
        XCTAssertEqual(requests[1].httpMethod, "POST")
        XCTAssertEqual(requests[1].url?.path, "/api/kg/entity-curation/merge")
        XCTAssertEqual(requests[2].httpMethod, "GET")
        XCTAssertEqual(requests[2].url?.path, "/api/entities/entity-1")
    }

    private func makeStore() -> EntityStore {
        let client = FicheroClient(baseURL: URL(string: "http://127.0.0.1:8765")!, libraryPath: "/tmp/test.fichero")
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

    private func makeDocumentInspectorResponse(entities: [[String: Any]]) -> Data {
        let payload: [String: Any] = [
            "document_id": "doc-1",
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

    private func makeEntityResponse(id: String, name: String) -> Data {
        jsonData(makeEntityJSON(id: id, name: name))
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
        curationState: Components.Schemas.EntityCurationState? = nil
    ) -> [String: Any] {
        var payload: [String: Any] = [
            "id": id,
            "canonical_name": name,
            "created_at": Self.isoFormatter.string(from: Date(timeIntervalSince1970: 1_700_000_000)),
            "updated_at": Self.isoFormatter.string(from: Date(timeIntervalSince1970: 1_700_000_000))
        ]
        if let curationState {
            payload["curation_state"] = curationState.rawValue
        }
        return payload
    }

    private func jsonData(_ object: Any) -> Data {
        (try? JSONSerialization.data(withJSONObject: object)) ?? Data()
    }
}
