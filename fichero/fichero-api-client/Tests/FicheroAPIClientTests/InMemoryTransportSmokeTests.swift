#if os(macOS)
import XCTest
import Foundation
import OpenAPIRuntime
import HTTPTypes
@testable import FicheroAPIClient

/// Proves the `.inMemory` transport actually round-trips: it boots the real
/// Fichero engine **in-process** via PythonKit (no subprocess, no socket, no
/// network) and issues lightweight reads (`/api/health`) through both the raw
/// `InMemoryASGIClientTransport` and the full `FicheroClient(transportMode:
/// .inMemory)` path (generated `Client` + middlewares + the `inmemory`
/// owner-auth marker).
///
/// This is the headless-test enabler for the whole service-integration mandate:
/// unlike the app's XCTest bundle (which needs `xcodebuild`), this runs under
/// plain `swift test`.
///
/// The streaming / cancellation / concurrency harness (`InMemoryASGITransportHarnessTests`)
/// and the transport-agnostic routing matrix (`TransportRoutingMatrixTests`)
/// build on this same in-process load.
///
/// NOTE: CPython boots ONCE per process and cannot be torn down, so this whole
/// suite must run in a test process that does no *OTHER* PythonKit work.
@MainActor
final class InMemoryTransportSmokeTests: XCTestCase {

    override func setUp() async throws {
        try InMemoryTestEnv.configureOrSkip()
    }

    /// Raw-transport round-trip: build the ASGI request by hand and drain the
    /// response. Proves the `AsgiBridge`/`PythonWorker`/GIL machinery end-to-end.
    func testRawTransportHealthRoundTrip() async throws {
        let transport = InMemoryASGIClientTransport(app: InMemoryEngineApp.shared())
        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: "/api/health")
        request.headerFields[.accept] = "application/json"

        let (response, body) = try await transport.send(
            request, body: nil,
            baseURL: URL(string: "http://asgi.local")!,
            operationID: "smokeHealth"
        )

        XCTAssertEqual(response.status.code, 200, "in-process /api/health must return 200")
        var bytes: [UInt8] = []
        if let body { for try await chunk in body { bytes.append(contentsOf: chunk) } }
        let text = String(decoding: bytes, as: UTF8.self)
        XCTAssertTrue(text.contains("\"status\":\"healthy\""),
                      "health body should report healthy; got: \(text)")
    }

    /// Full-client round-trip: goes through the generated `Client`, the auth +
    /// library-path middlewares, and the `inmemory` transport marker that grants
    /// loopback-owner access — i.e. the exact path production and future service
    /// tests use.
    func testFullClientHealthRoundTrip() async throws {
        let client = FicheroClient(transportMode: .inMemory)
        let response = try await client.api.healthCheckApiHealthGet(.init())
        switch response {
        case .ok(let ok):
            let json = try ok.body.json
            XCTAssertEqual(json.status, "healthy",
                           "full-client in-process /api/health must report healthy")
        default:
            XCTFail("unexpected /api/health response over .inMemory: \(response)")
        }
    }
}
#endif