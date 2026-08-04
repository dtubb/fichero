import Foundation
import HTTPTypes
import OpenAPIRuntime
import OpenAPIURLSession
import Testing
@testable import FicheroAPIClient

/// #4511 — the test-host dial chokepoint.
///
/// These tests run inside a test host, so `TestHostTransportGuard.isTestHost`
/// is true for them by construction: the suite asserts the guard's *effect* in
/// exactly the situation it exists for, rather than simulating it.
@Suite("Test-host transport guard (#4511)")
struct TestHostTransportGuardTests {
    // MARK: - The guard is actually armed here

    /// If this ever fails, every other assertion below is vacuous — so it is
    /// asserted first and separately. A guard whose precondition is not met
    /// silently proves nothing.
    @Test("the guard detects that this process is a test host")
    func guardIsArmedInThisProcess() {
        #expect(TestHostTransportGuard.isTestHost)
    }

    // MARK: - The chokepoint refuses

    @Test("makeTransport returns the fail-fast transport for every live mode")
    func makeTransportRefusesEveryLiveMode() {
        var modes: [TransportMode] = [.https, .uds(path: "/tmp/fichero-guard-test.sock")]
        #if os(macOS)
        // `.inMemory` boots CPython on first use — the guard must intercept it
        // BEFORE that happens, which is exactly what this asserts.
        modes.append(.inMemory)
        #endif

        for mode in modes {
            for usage in [FicheroClient.TransportUsage.request, .stream] {
                let transport = FicheroClient.makeTransport(transportMode: mode, usage: usage)
                #expect(
                    transport is FailFastTransport,
                    "\(mode) / \(usage) dialled live under a test host"
                )
            }
        }
    }

    /// The failure is TYPED and carries the operation that tried to dial —
    /// the point is a developer reading the log knows which call was refused,
    /// not that something somewhere threw.
    @Test("the fail-fast transport throws a typed, operation-tagged error")
    func failFastTransportThrowsTypedError() async throws {
        let transport = FailFastTransport()
        var thrown: Error?
        do {
            _ = try await transport.send(
                HTTPRequest(method: .get, scheme: nil, authority: nil, path: "/api/documents/roots"),
                body: nil,
                baseURL: URL(string: "https://127.0.0.1:8765")!,
                operationID: "listDocumentRootsApiDocumentsRootsGet"
            )
        } catch {
            thrown = error
        }

        let refusal = try #require(thrown as? EngineDialRefusedUnderTest)
        #expect(refusal.operationID == "listDocumentRootsApiDocumentsRootsGet")
        let message = try #require(refusal.errorDescription)
        #expect(message.contains("listDocumentRootsApiDocumentsRootsGet"))
        #expect(message.contains("#4511"))
    }

    /// It must throw, not return an empty 200. A canned success would read to
    /// every store under test as "the engine answered with nothing", which is
    /// the silent-fallback class this project bans — and it would have hidden
    /// #4511 rather than surfacing it.
    @Test("a refused dial is an error, never an empty success")
    func refusedDialIsNeverASilentSuccess() async {
        let transport = FailFastTransport()
        await #expect(throws: EngineDialRefusedUnderTest.self) {
            _ = try await transport.send(
                HTTPRequest(method: .get, scheme: nil, authority: nil, path: "/api/registry"),
                body: nil,
                baseURL: URL(string: "https://127.0.0.1:8765")!,
                operationID: "getRegistryApiRegistryGet"
            )
        }
    }

    // MARK: - The exemption

    /// An injected session is the test's OWN stub (URLProtocol mock, pinning
    /// probe). Swapping it for the fail-fast transport would silently defeat
    /// the test that installed it — the #4024 failure mode, in a new costume.
    @Test("an explicitly injected session is honoured, not replaced")
    func injectedSessionSurvivesTheGuard() {
        let session = URLSession(configuration: .ephemeral)
        let transport = FicheroClient.makeTransport(session: session, transportMode: .https)
        #expect(transport is URLSessionTransport)
        #expect(!(transport is FailFastTransport))
    }

    /// The transport-selection tests must still be able to see the real
    /// factory — that is the whole reason `liveTransport` is a separate
    /// symbol. If the guard leaked into it, those tests would go vacuous.
    @Test("liveTransport still builds the real transport under a test host")
    func liveTransportIsNotGuarded() {
        let transport = FicheroClient.liveTransport(transportMode: .https)
        #expect(transport is URLSessionTransport)
        #expect(!(transport is FailFastTransport))
    }

    // MARK: - A whole client is guarded, not just the helper

    /// The five #4511 dials go through `FicheroClient.init`, not through
    /// `makeTransport` directly — so the client's OWN transports must be the
    /// fail-fast ones, request and stream alike. A stream that still dialled
    /// would hang the host exactly as before.
    @Test("a default-constructed client holds fail-fast request and stream transports")
    @MainActor
    func clientTransportsAreBothGuarded() {
        let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!)
        #expect(client.transport is FailFastTransport)
        #expect(client.streamTransport is FailFastTransport)
    }
}
