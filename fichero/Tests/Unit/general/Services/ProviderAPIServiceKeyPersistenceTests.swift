@testable import Fichero
import FicheroAPIClient
import XCTest

/// #4815 — one store of truth for provider keys: Settings must persist to the
/// app's own Keychain on a successful save/remove, the launch-time push must
/// NEVER write it back, and the engine always receives the trimmed value the
/// Keychain keeps.
///
/// `storeProviderKey`/`removeProviderKey` are overridden with an in-memory
/// spy throughout, so NOTHING here ever touches the real Keychain (contrast
/// `ProviderKeyStoreTests`, which deliberately DOES exercise the real
/// Keychain — a different concern, testing `ProviderKeyStore` itself rather
/// than `ProviderAPIService`'s use of it).
///
/// A real HTTP seam DOES exist for the success path — copied here from
/// `EntityServiceTransportTests.swift`'s `MockTransportURLProtocol` (not
/// refactored to share in this delivery, per instruction): a stub `URLProtocol`
/// registered on the `URLSession` a `FicheroClient` is built from.
///
/// Coverage gap, flagged rather than silently claimed: the recorded
/// `URLRequest`'s `httpBody` is NOT readable here — the generated client sends
/// POST bodies as upload tasks, whose body a `URLProtocol` stub cannot see
/// (`httpBody` is `nil`; the same limitation `BatchServiceTests.swift` already
/// documents, #4024). So this suite cannot independently re-read the WIRE body
/// to confirm it carries the trimmed value. What IS proven instead: `setAPIKey`
/// computes ONE `trimmed` local and passes that SAME value to both `postAPIKey`
/// (the engine call) and `storeProviderKey` (the Keychain call) —
/// dynamically, by asserting the closure receives the expected trimmed
/// string, plus the existing source-scan (`testSetAPIKeyTrimsOnceForBoth
/// TheEngineAndTheKeychain`) pinning that both calls read the ONE local — the
/// combination is the closest honest proof of "engine and Keychain get the
/// identical value" this test target can produce without the wire-body seam
/// #4024 already ruled out.
@MainActor
final class ProviderAPIServiceKeyPersistenceTests: XCTestCase {

    // MARK: - Mock transport (copied from EntityServiceTransportTests.swift,
    // not shared, per instruction — this delivery does not refactor that file)

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

    override func setUp() {
        super.setUp()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        MockTransportURLProtocol.reset([])
    }

    private static func serviceWithMockTransport(stubs: [Stub]) -> ProviderAPIService {
        MockTransportURLProtocol.reset(stubs)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ProviderAPIServiceKeyPersistenceTests.fichero",
            session: session
        )
        return ProviderAPIService(ficheroClient: client)
    }

    /// Port 1 is reserved; nothing listens on it locally, so every request
    /// fails with a connection error almost immediately — fast and
    /// deterministic, no real server and no timeout.
    private static func serviceWithUnreachableClient() -> ProviderAPIService {
        let client = FicheroClient(
            baseURL: URL(string: "http://127.0.0.1:1")!,
            libraryPath: "/tmp/ProviderAPIServiceKeyPersistenceTests.fichero"
        )
        return ProviderAPIService(ficheroClient: client)
    }

    // MARK: - Success path: HTTP 200 -> Keychain written with the trimmed value

    /// The regression test #4815 demands: a successful Settings save must
    /// reach the Keychain closure with the SAME trimmed value the engine
    /// accepted. Sentinel string, never anything shaped like a real key.
    func testSetAPIKeySuccessStoresTheTrimmedKey() async throws {
        let service = Self.serviceWithMockTransport(stubs: [
            Stub(pathContains: "/api-key", status: 200, body: Data(#"{"status":"stored"}"#.utf8))
        ])
        var storeCalls: [(String, String)] = []
        service.storeProviderKey = { key, provider in
            storeCalls.append((key, provider))
            return true
        }

        try await service.setAPIKey(providerType: "openrouter", apiKey: "  SENTINEL-NOT-A-KEY  ")

        XCTAssertEqual(storeCalls.count, 1)
        XCTAssertEqual(storeCalls.first?.0, "SENTINEL-NOT-A-KEY")
        XCTAssertEqual(storeCalls.first?.1, "openrouter")
        XCTAssertTrue(MockTransportURLProtocol.recorded().contains {
            $0.url?.path.contains("/api-key") == true && $0.httpMethod == "POST"
        })
    }

    /// `deleteAPIKey` success -> the remove closure fires once, and the
    /// launch push's own read-then-supply shape
    /// (`EngineLifecycleController+ProviderKeys.swift:52`:
    /// `guard let key = ProviderKeyStore.key(for: provider) else { continue }`)
    /// sends NOTHING for that provider afterward, simulated against the same
    /// fake store `setAPIKey`'s success test above uses.
    func testDeleteAPIKeySuccessRemovesTheKeyAndLeavesNothingForTheNextLaunchPush() async throws {
        let service = Self.serviceWithMockTransport(stubs: [
            Stub(pathContains: "/api-key", status: 200, body: Data(#"{"status":"deleted"}"#.utf8))
        ])
        var fakeStore: [String: String] = ["openrouter": "SENTINEL-OLD-KEY"]
        var removeCalls = 0
        service.removeProviderKey = { provider in
            removeCalls += 1
            fakeStore.removeValue(forKey: provider)
            return true
        }

        try await service.deleteAPIKey(providerType: "openrouter")
        XCTAssertEqual(removeCalls, 1)

        // The launch push's own guard, simulated: nothing left to read means
        // nothing is supplied — no `supplyAPIKeyToEngine` call happens at all.
        XCTAssertNil(fakeStore["openrouter"], "the fake Keychain must no longer hold a key for this provider")
    }

    /// THE REGRESSION TEST FROM THE ISSUE: seed the fake store with a STALE
    /// key, save a NEW one through `setAPIKey`, then simulate the launch
    /// push reading from that SAME fake store and supplying to the engine —
    /// the last key the engine receives must be the NEW one, never the
    /// stale one #4815's bug kept resurrecting.
    ///
    /// Scoped to `ProviderAPIService` rather than a live
    /// `EngineLifecycleController` (a smaller, deliberate choice, not an
    /// oversight): `EngineLifecycleController()` constructs
    /// `EmbeddedBackendService`/`AppState`/`LibraryManager.shared` — real
    /// app-lifetime infrastructure, too heavy for a unit test and not what
    /// this regression is actually about. The bug was "Settings never
    /// updates the store the launch push reads from" — this test proves
    /// exactly that seam: a store update via `setAPIKey`, followed by a
    /// read+supply via `supplyAPIKeyToEngine`, reflects the NEW value.
    func testStaleKeyRegression_settingsSaveIsReflectedByTheNextEngineSupply() async throws {
        let service = Self.serviceWithMockTransport(stubs: [
            Stub(pathContains: "/api-key", status: 200, body: Data(#"{"status":"stored"}"#.utf8))
        ])
        var fakeStore: [String: String] = ["openrouter": "SENTINEL-OLD-KEY"]
        service.storeProviderKey = { key, provider in
            fakeStore[provider] = key
            return true
        }

        // Settings save — the fix under test.
        try await service.setAPIKey(providerType: "openrouter", apiKey: "SENTINEL-NEW-KEY")
        XCTAssertEqual(fakeStore["openrouter"], "SENTINEL-NEW-KEY")

        // The launch push's own read-then-supply shape
        // (`EngineLifecycleController+ProviderKeys.swift:52-57`), simulated
        // against the SAME fake store rather than a live controller.
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api-key", status: 200, body: Data(#"{"status":"stored"}"#.utf8))
        ])
        guard let key = fakeStore["openrouter"] else {
            XCTFail("the fake store must still hold a key for this provider")
            return
        }
        try await service.supplyAPIKeyToEngine(providerType: "openrouter", apiKey: key)

        let sentKeys = MockTransportURLProtocol.recorded().count
        XCTAssertEqual(sentKeys, 1, "exactly one engine-supply request for the read key")
        XCTAssertEqual(key, "SENTINEL-NEW-KEY", "the launch push must never resupply the stale key")
    }

    /// Engine accepts (200), but the Keychain write fails — surfaced
    /// distinctly (prefer raise over silent fallback), never silently
    /// swallowed, and the error's own description names no key material.
    func testSetAPIKeySuccessButKeychainFailureThrowsDistinctErrorWithNoKeyMaterial() async {
        let service = Self.serviceWithMockTransport(stubs: [
            Stub(pathContains: "/api-key", status: 200, body: Data(#"{"status":"stored"}"#.utf8))
        ])
        service.storeProviderKey = { _, _ in false }

        do {
            try await service.setAPIKey(providerType: "openrouter", apiKey: "SENTINEL-NOT-A-KEY")
            XCTFail("expected a Keychain-failure error")
        } catch ProviderAPIServiceError.keyNotPersistedLocally {
            let description = ProviderAPIServiceError.keyNotPersistedLocally.errorDescription ?? ""
            XCTAssertFalse(description.contains("SENTINEL-NOT-A-KEY"), "the error must never name the key")
        } catch {
            XCTFail("expected .keyNotPersistedLocally, got \(error)")
        }
    }

    /// `supplyAPIKeyToEngine` success -> the request IS recorded (the engine
    /// really got it), but NEITHER Keychain closure fires.
    func testSupplyAPIKeyToEngineSuccessRecordsTheRequestButTouchesNoClosure() async throws {
        let service = Self.serviceWithMockTransport(stubs: [
            Stub(pathContains: "/api-key", status: 200, body: Data(#"{"status":"stored"}"#.utf8))
        ])
        var storeCalls = 0
        var removeCalls = 0
        service.storeProviderKey = { _, _ in storeCalls += 1; return true }
        service.removeProviderKey = { _ in removeCalls += 1; return true }

        try await service.supplyAPIKeyToEngine(providerType: "openrouter", apiKey: "SENTINEL-NOT-A-KEY")

        XCTAssertTrue(MockTransportURLProtocol.recorded().contains {
            $0.url?.path.contains("/api-key") == true && $0.httpMethod == "POST"
        })
        XCTAssertEqual(storeCalls, 0)
        XCTAssertEqual(removeCalls, 0)
    }

    // MARK: - Order: engine before Keychain

    /// When the engine POST fails, the Keychain closure must never fire —
    /// proves the order (engine first) without needing a successful network
    /// call.
    func testSetAPIKeyNeverTouchesTheStoreWhenTheEngineCallFails() async {
        let service = Self.serviceWithUnreachableClient()
        var storeCalls: [(String, String)] = []
        service.storeProviderKey = { key, provider in
            storeCalls.append((key, provider))
            return true
        }

        do {
            try await service.setAPIKey(providerType: "openrouter", apiKey: "  sk-test  ")
            XCTFail("expected the unreachable client to throw")
        } catch {
            // Expected — the connection fails.
        }

        XCTAssertTrue(storeCalls.isEmpty, "a failed engine call must never reach the Keychain closure")
    }

    func testDeleteAPIKeyNeverTouchesTheRemoveClosureWhenTheEngineCallFails() async {
        let service = Self.serviceWithUnreachableClient()
        var removeCalls: [String] = []
        service.removeProviderKey = { provider in
            removeCalls.append(provider)
            return true
        }

        do {
            try await service.deleteAPIKey(providerType: "openrouter")
            XCTFail("expected the unreachable client to throw")
        } catch {
            // Expected.
        }

        XCTAssertTrue(removeCalls.isEmpty, "a failed engine call must never reach the Keychain closure")
    }

    // MARK: - The engine-only path — #4815/#4817's whole reason to be distinct

    /// `supplyAPIKeyToEngine` reads a key the Keychain ALREADY holds and
    /// hands it to the engine — it must never write the store back, success
    /// or failure. Proven for the failure case the same way as above; the
    /// structural half (it references neither closure at all, so there is no
    /// SUCCESS-path branch that could call them) is pinned by the source-scan
    /// test below.
    func testSupplyAPIKeyToEngineNeverTouchesEitherKeychainClosure() async {
        let service = Self.serviceWithUnreachableClient()
        var storeCalls = 0
        var removeCalls = 0
        service.storeProviderKey = { _, _ in storeCalls += 1; return true }
        service.removeProviderKey = { _ in removeCalls += 1; return true }

        do {
            try await service.supplyAPIKeyToEngine(providerType: "openrouter", apiKey: "sk-test")
            XCTFail("expected the unreachable client to throw")
        } catch {
            // Expected.
        }

        XCTAssertEqual(storeCalls, 0)
        XCTAssertEqual(removeCalls, 0)
    }

    // MARK: - Source contract (structural, not runtime-observable without an HTTP mock)

    private func appSource(_ relativePath: String) throws -> String {
        try AppSource.code(relativePath)
    }

    /// `supplyAPIKeyToEngine`'s own body never mentions either Keychain
    /// closure — the engine-only guarantee holds even on the SUCCESS path,
    /// which the tests above cannot reach without a real server.
    func testSupplyAPIKeyToEngineBodyNeverReferencesTheKeychainClosures() throws {
        let source = try appSource("Services/ProviderAPIService.swift")
        guard let start = source.range(of: "func supplyAPIKeyToEngine"),
              let bodyStart = source.range(of: "{", range: start.upperBound..<source.endIndex),
              let bodyEnd = source.range(of: "\n    }", range: bodyStart.upperBound..<source.endIndex)
        else {
            XCTFail("could not locate supplyAPIKeyToEngine's body")
            return
        }
        let body = source[bodyStart.upperBound..<bodyEnd.lowerBound]
        XCTAssertFalse(body.contains("storeProviderKey"))
        XCTAssertFalse(body.contains("removeProviderKey"))
    }

    /// #4815/#4817's whole reason `supplyAPIKeyToEngine` is a DISTINCT method
    /// rather than a flag: it must have exactly one caller, the launch push.
    func testSupplyAPIKeyToEngineHasExactlyOneCaller() throws {
        let root = try AppSource.root()
        guard let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil) else {
            XCTFail("could not enumerate \(root.path)")
            return
        }
        var callers: [String] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let relative = AppSource.relativePath(of: url, under: root)
            guard let source = try? String(contentsOf: url, encoding: .utf8) else { continue }
            let occurrences = source.components(separatedBy: ".supplyAPIKeyToEngine(").count - 1
            if occurrences > 0 {
                callers.append(contentsOf: Array(repeating: relative, count: occurrences))
            }
        }
        XCTAssertEqual(
            callers, ["Services/EngineLifecycleController+ProviderKeys.swift"],
            "supplyAPIKeyToEngine must have exactly one caller, the launch push"
        )
    }

    /// The remote-engine skip — the app Keychain is not that engine's truth.
    func testSetAndDeleteAPIKeySkipTheKeychainForARemoteEngine() throws {
        let source = try appSource("Services/ProviderAPIService.swift")
        let occurrences = source.components(separatedBy: "connectsToRemoteHost").count - 1
        XCTAssertEqual(occurrences, 2, "both setAPIKey and deleteAPIKey must check the remote-engine guard")
    }

    /// The engine and the Keychain must receive the IDENTICAL trimmed value —
    /// not two independent trims that could disagree.
    func testSetAPIKeyTrimsOnceForBothTheEngineAndTheKeychain() throws {
        let source = try appSource("Services/ProviderAPIService.swift")
        XCTAssertTrue(source.contains("let trimmed = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)"))
        XCTAssertTrue(source.contains("try await postAPIKey(providerType: providerType, apiKey: trimmed)"))
        XCTAssertTrue(source.contains("storeProviderKey(trimmed, providerType)"))
    }
}
