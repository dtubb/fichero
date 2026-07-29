@testable import Fichero
import Foundation
import XCTest

/// Source-inspection regression guard for #4046 / fix-entityservice-transport:
/// `EntityService` must reach the engine ONLY through the library's
/// `FicheroClient` — the generated `client.api.*` ops and the
/// `client.requestData(...)` buffered helper that rides the shared
/// `ClientTransport` + auth/library middleware stack. A raw `URLSession` call
/// can dial only `.https` (127.0.0.1:8765) and silently fails over the app's
/// `.uds` / `.inMemory` transports — the original "Loaded 0 entities" symptom.
///
/// This complements `EntityServiceTransportTests` (which injects a mock
/// `URLProtocol` and asserts each method's request flows through the transport)
/// with a zero-engine source-inspection pin: a regression that re-introduces a
/// raw `URLSession(` / `RemoteCertificatePinning` / `https://127.0.0.1` fetch in
/// any `EntityService*.swift` file fails here, without needing a live engine or
/// even a transport session. Mirrors the style of
/// `EngineWebViewSchemeHandlerRoutingTests`.
///
/// Comment-safe: the main `EntityService.swift` documents the migration in a
/// doc comment that mentions `URLSession` (no call), so we assert against
/// `URLSession(` (the call form) and the pinning symbols, not the bare word.
final class EntityServiceTransportRoutingTests: XCTestCase {

    private static let servicesDir: String = {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent("Services")
            .path
    }()

    /// All `EntityService*.swift` source files (main + per-concern extensions).
    private static func entityServiceSources() throws -> [String] {
        let fm = FileManager.default
        let entries = try fm.contentsOfDirectory(atPath: servicesDir)
        return entries
            .filter { $0.hasPrefix("EntityService") && $0.hasSuffix(".swift") }
            .sorted()
            .map { (servicesDir as NSString).appendingPathComponent($0) }
    }

    private static func readSource(_ path: String) throws -> String {
        try String(contentsOfFile: path, encoding: .utf8)
    }

    // MARK: - No raw network path in any EntityService file

    /// Forbidden: a raw `URLSession(` call bypasses the `ClientTransport` and
    /// breaks over `.uds` / `.inMemory` (no HTTP listener). The call form
    /// `URLSession(` is asserted (not the bare word) so the migration doc
    /// comment in `EntityService.swift` is allowed.
    func testNoEntityServiceFileDialsRawURLSession() throws {
        for path in try Self.entityServiceSources() {
            let source = try Self.readSource(path)
            let name = (path as NSString).lastPathComponent
            XCTAssertFalse(
                source.contains("URLSession("),
                "\(name) must not dial URLSession directly; route through FicheroClient"
                    + " (client.api.* / client.requestData) so the request rides the active transport"
            )
        }
    }

    /// Forbidden: `RemoteCertificatePinning.configuredSession()` was the
    /// pre-migration raw-https path. It pins to the HTTP listener and silently
    /// fails over UDS / in-process transports.
    func testNoEntityServiceFileUsesCertificatePinningSession() throws {
        for path in try Self.entityServiceSources() {
            let source = try Self.readSource(path)
            let name = (path as NSString).lastPathComponent
            XCTAssertFalse(
                source.contains("RemoteCertificatePinning"),
                "\(name) must not build a RemoteCertificatePinning session; the middleware stack handles TLS"
            )
            XCTAssertFalse(
                source.contains("configuredSession("),
                "\(name) must not call configuredSession(); route through FicheroClient instead"
            )
        }
    }

    /// Forbidden: hard-coded `https://127.0.0.1` or `EngineConfig.host` would
    /// bypass the transport and target the HTTP listener that UDS / in-memory
    /// never open.
    func testNoEntityServiceFileHardCodesEngineHTTPEndpoint() throws {
        for path in try Self.entityServiceSources() {
            let source = try Self.readSource(path)
            let name = (path as NSString).lastPathComponent
            XCTAssertFalse(
                source.contains("https://127.0.0.1"),
                "\(name) must not hard-code the HTTP listener URL; UDS/in-memory have none"
            )
            XCTAssertFalse(
                source.contains("EngineConfig.host"),
                "\(name) must not read EngineConfig.host; the transport, not a host, carries the request"
            )
        }
    }

    // MARK: - EntityService reaches the engine through the generated client

    /// The main `EntityService.swift` must route its generic buffered helper
    /// through `client.requestData(...)` — the transport-agnostic sibling of
    /// `streamLines` that folds the middleware stack around the shared
    /// transport. ~90 concern-extension callers go through this helper.
    func testMainEntityServiceRoutesEndpointDataThroughClientRequestData() throws {
        let path = (Self.servicesDir as NSString).appendingPathComponent("EntityService.swift")
        let source = try Self.readSource(path)
        XCTAssertTrue(
            source.contains("client.requestData("),
            "EntityService.endpointData must fetch via FicheroClient.requestData so it "
                + "rides the active transport (.uds/.https/.inMemory), not a raw network call"
        )
        XCTAssertTrue(
            source.contains("let client: FicheroClient"),
            "EntityService must hold the generated FicheroClient as its transport accessor"
        )
    }

    /// The main `EntityService.swift` must call at least one generated
    /// `client.api.*` op (the OpenAPI-backed reactive path mandated by the
    /// knowledge-consistency mandate — no hand-rolled URLSession). Pinning a
    /// representative op catches a regression that drops the generated path.
    func testMainEntityServiceCallsGeneratedClientOps() throws {
        let path = (Self.servicesDir as NSString).appendingPathComponent("EntityService.swift")
        let source = try Self.readSource(path)
        XCTAssertTrue(
            source.contains("client.api."),
            "EntityService must use the generated client.api.* ops (the OpenAPI-backed path), "
                + "not a hand-rolled URLSession"
        )
        // Representative generated op from the migration (citation usages).
        XCTAssertTrue(
            source.contains("listCitationUsagesApiCitationUsagesGet"),
            "EntityService.citationUsages must use the generated listCitationUsages op"
        )
    }

    /// Every per-concern extension file must reach the engine through the
    /// shared client — either a generated `client.api.*` op or the
    /// `endpointData` helper (which itself routes through `client.requestData`).
    /// A new extension that hand-rolls a URLSession would bypass the transport.
    func testEveryEntityServiceExtensionRoutesThroughClientOrEndpointData() throws {
        for path in try Self.entityServiceSources() {
            let source = try Self.readSource(path)
            let name = (path as NSString).lastPathComponent
            // The main file owns `endpointData`; extensions call it or `client.api.*`.
            let usesGeneratedOrHelper = source.contains("client.api.")
                || source.contains("endpointData(")
                || source.contains("client.requestData(")
            XCTAssertTrue(
                usesGeneratedOrHelper,
                "\(name) must reach the engine via client.api.*, endpointData(), or "
                    + "client.requestData() — not a hand-rolled URLSession"
            )
        }
    }
}