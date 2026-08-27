@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// #4024 regression stub: scoped to /api/health with an invocation flag, used to prove the
/// wrapped FicheroClient keeps its injected session after a library-path change
/// (rebuildClient) instead of silently reverting to the real-network transport.
private final class HealthProbeMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handlerInvoked = false
    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path.hasPrefix("/api/health") == true
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        HealthProbeMockURLProtocol.handlerInvoked = true
        let response = HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("{}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite("APIClient generated-client wrapper")
struct APIClientTests {
    @Test("APIClient wraps a FicheroClient configured at the engine host")
    @MainActor
    func wrapsFicheroClientAtEngineHost() {
        let customHost = URL(string: "https://tailnet.example:8765")!
        let client = APIClient(baseURL: customHost, libraryPath: "/tmp/Test.fichero")

        #expect(client.client.baseURL == customHost)
        #expect(client.baseURL == customHost.appendingPathComponent("api"))
        #expect(client.currentLibraryPath == "/tmp/Test.fichero")
    }

    @Test("Library path propagates to the wrapped FicheroClient")
    @MainActor
    func propagatesLibraryPath() {
        let client = APIClient()

        client.currentLibraryPath = "/Users/example/Library.fichero"

        #expect(client.client.currentLibraryPath == "/Users/example/Library.fichero")
    }

    @Test("Exposes the generated OpenAPI client")
    @MainActor
    func exposesGeneratedClient() {
        let client = APIClient(baseURL: URL(string: "https://127.0.0.1:8765")!)

        // `api` returns the generated `Client` from FicheroAPIClient.
        #expect(client.api is Client)
    }

    @Test("#4024: a library-path change retains the injected mock transport (no real-network escape)")
    @MainActor
    func libraryPathChangeRetainsInjectedSession() async throws {
        HealthProbeMockURLProtocol.handlerInvoked = false
        defer { HealthProbeMockURLProtocol.handlerInvoked = false }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HealthProbeMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/a.fichero",
            session: URLSession(configuration: configuration)
        )

        // Trigger rebuildClient() exactly as APIClient.init(client:) / any path change does.
        client.currentLibraryPath = "/tmp/b.fichero"

        // If the injected session survived the rebuild, the stub intercepts and sets its flag;
        // if the fix regressed, the request escapes to the real network (test.fichero DNS
        // failure) and the flag stays false. The decoded result is irrelevant to the contract.
        _ = try? await client.api.healthCheckApiHealthGet(.init())

        #expect(HealthProbeMockURLProtocol.handlerInvoked)
    }
}
