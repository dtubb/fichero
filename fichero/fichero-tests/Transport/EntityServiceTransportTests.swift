//
//  EntityServiceTransportTests.swift
//  FicheroTests
//
//  Regression guard for the EntityService raw-URLSession → centralized-transport
//  migration (fix/entityservice-transport).
//
//  Every EntityService read/write method must dial the engine through the
//  FicheroClient's shared `ClientTransport` (`client.api` for the generated ops,
//  `client.requestData` for the generic `endpointData` helper), NOT a raw
//  `RemoteCertificatePinning.configuredSession()`. A raw URLSession can reach
//  only `.https` (127.0.0.1:8765) and silently fails over the app's `.uds` /
//  `.inMemory` transports — the "Loaded 0 entities" bug.
//
//  How this catches a bypass: we inject a mock `URLProtocol` onto the URLSession
//  that FicheroClient's `.https` `URLSessionTransport` is built from. Requests
//  that flow through `client.transport` are intercepted and recorded here. A
//  method still on `RemoteCertificatePinning.configuredSession()` would issue on
//  a DIFFERENT session with no mock protocol — its request never reaches this
//  recorder and instead hits the (absent) real engine, throwing a URLError. So
//  "a request was recorded here for method X" is a direct assertion that X went
//  through the transport rather than bypassing it.
//
//  Note on `.inMemory`: the plan called for driving the engine's ASGI app
//  in-process via `FicheroClient(transportMode: .inMemory)`. That boots CPython
//  (libpython + `fichero.api.main` import via PythonKit) and needs a real
//  provisioned library DB for these read endpoints to return anything but a
//  library-not-found error — indistinguishable from a transport error and not
//  available in a headless unit test. Per the plan's documented fallback, we
//  assert the requests flow through the injected transport instead. The mock
//  session exercises the SAME code path (`client.transport` + middleware stack)
//  that `.uds` / `.inMemory` use; only the concrete transport differs.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

@MainActor
final class EntityServiceTransportTests: XCTestCase {

    // MARK: - Mock transport

    private struct Stub {
        let pathContains: String
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
            Self.lock.lock()
            Self.requests.append(request)
            let stub = Self.stubs.first { !$0.pathContains.isEmpty && path.contains($0.pathContains) }
            Self.lock.unlock()

            let resolved = stub ?? Stub(pathContains: "", status: 200, body: Data("{}".utf8))
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

    // MARK: - Fixtures

    private let libraryPath = "/tmp/entity-service-transport-test.fichero"

    override func setUp() async throws {
        try await super.setUp()
        // Bootstrap-token env override so AuthTokenMiddleware resolves a token
        // instantly (loopback host) instead of stalling 3s per request waiting
        // for a `.api-key` file that doesn't exist in the test sandbox.
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        MockTransportURLProtocol.reset([])
    }

    private func makeService(stubs: [Stub], withLibrary: Bool = true) -> EntityService {
        MockTransportURLProtocol.reset(stubs)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: withLibrary ? libraryPath : nil,
            session: session
        )
        return EntityService(ficheroClient: client)
    }

    private func assertRecorded(
        pathContains fragment: String,
        method: String? = nil,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        let requests = MockTransportURLProtocol.recorded()
        let matched = requests.contains { request in
            let pathOK = (request.url?.path.contains(fragment) ?? false)
            let methodOK = method.map { $0 == (request.httpMethod ?? "GET") } ?? true
            return pathOK && methodOK
        }
        XCTAssertTrue(
            matched,
            "Expected a \(method ?? "any")-request through the transport whose path "
                + "contains \(fragment); recorded: "
                + "\(requests.map { "\($0.httpMethod ?? "?") \($0.url?.path ?? "?")" })",
            file: file,
            line: line
        )
    }

    // MARK: - endpointData (generic helper feeding ~90 concern-extension callers)

    func testEndpointDataRoutesThroughTransport() async throws {
        let service = makeService(stubs: [
            Stub(pathContains: "/api/kg/graph/metrics", status: 200, body: Data("{}".utf8))
        ])
        let data = try await service.endpointData(path: "/api/kg/graph/metrics")
        XCTAssertFalse(data.isEmpty)
        assertRecorded(pathContains: "/api/kg/graph/metrics", method: "GET")
    }

    func testEndpointDataPostBodyRoutesThroughTransport() async throws {
        let service = makeService(stubs: [
            Stub(pathContains: "/api/kg/inclusion", status: 200, body: Data("{}".utf8))
        ])
        _ = try await service.endpointData(
            path: "/api/kg/inclusion",
            method: "POST",
            jsonBody: ["enabled": true]
        )
        assertRecorded(pathContains: "/api/kg/inclusion", method: "POST")
    }

    // MARK: - Migrated generated-op methods

    func testCitationUsagesRoutesThroughTransport() async throws {
        let service = makeService(stubs: [
            Stub(
                pathContains: "/api/citation-usages",
                status: 200,
                body: Data(#"{"items":[],"count":0}"#.utf8)
            )
        ])
        let usages = try await service.citationUsages(sourceDocumentId: "doc-1")
        XCTAssertEqual(usages.count, 0)
        assertRecorded(pathContains: "/api/citation-usages", method: "GET")
    }

    func testListLibraryEntityTypesRoutesThroughTransport() async throws {
        let service = makeService(stubs: [
            Stub(
                pathContains: "/entity-types",
                status: 200,
                body: Data(#"{"items":[],"count":0}"#.utf8)
            )
        ])
        let types = try await service.listLibraryEntityTypes()
        XCTAssertEqual(types.count, 0)
        assertRecorded(pathContains: "/entity-types", method: "GET")
    }

    func testAddLibraryEntityTypeRoutesThroughTransport() async throws {
        let service = makeService(stubs: [
            Stub(
                pathContains: "/entity-types",
                status: 200,
                body: Data(#"{"library_id":"lib-1","entity_type_key":"person","enabled":true}"#.utf8)
            )
        ])
        let item = try await service.addLibraryEntityType(key: "person")
        XCTAssertEqual(item.entityTypeKey, "person")
        assertRecorded(pathContains: "/entity-types", method: "POST")
    }

    func testRemoveLibraryEntityTypeRoutesThroughTransport() async throws {
        let service = makeService(stubs: [
            Stub(pathContains: "/entity-types", status: 204, body: Data())
        ])
        try await service.removeLibraryEntityType(key: "person")
        assertRecorded(pathContains: "/entity-types", method: "DELETE")
    }

    func testListDocumentPrototypesRoutesThroughTransport() async throws {
        let service = makeService(stubs: [
            Stub(
                pathContains: "/api/classifications",
                status: 200,
                body: Data(#"{"items":[],"count":0}"#.utf8)
            )
        ])
        let prototypes = try await service.listDocumentPrototypes()
        XCTAssertEqual(prototypes.count, 0)
        assertRecorded(pathContains: "/api/classifications", method: "GET")
    }

    func testListNodeClassesRoutesThroughTransport() async throws {
        let service = makeService(stubs: [
            Stub(
                pathContains: "/api/classifications",
                status: 200,
                body: Data(#"{"items":[],"count":0}"#.utf8)
            )
        ])
        let classes = try await service.listNodeClasses()
        XCTAssertEqual(classes.count, 0)
        assertRecorded(pathContains: "/api/classifications", method: "GET")
    }
}
