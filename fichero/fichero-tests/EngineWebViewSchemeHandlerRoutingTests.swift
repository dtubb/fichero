@testable import Fichero
import Foundation
import XCTest

/// Regression coverage for #4066: the KG web pane routes through the active
/// `FicheroClient` transport (`.https` / `.uds` / `.inMemory`), NOT a raw
/// `URLSession` to `https://127.0.0.1:8765` that would fail `-1004` over a
/// UDS-only or socket-less engine.
///
/// `EngineWebViewSchemeHandler` is the `WKURLSchemeHandler` that intercepts
/// every `fichero-engine://` navigation + relative subresource. Its ONLY network
/// path is `client.requestData(...)` — the transport-agnostic fetch that rides
/// whatever `ClientTransport` the client dials. These source-inspection tests
/// pin that contract: a regression that reverts the handler to a raw engine
/// URL or a hand-rolled URLSession fails here, complementing the round-trip
/// coverage in `EngineWebViewRoutingTests` (FicheroAPIClientTests) over the
/// `.uds` and `.inMemory` transports.
@MainActor
final class EngineWebViewSchemeHandlerRoutingTests: XCTestCase {

    private static func source(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // MARK: - Handler routes through the transport-agnostic client path

    /// The handler's only network path MUST be `client.requestData(...)` — the
    /// method that dials the active `ClientTransport`. If someone re-introduces
    /// a raw `URLSession` / `https://127.0.0.1:8765` / `EngineConfig.host` /
    /// `RemoteCertificatePinning` fetch, the pane breaks over `.uds`/`.inMemory`
    /// (no HTTP listener) and this fails.
    func testHandlerRoutesThroughClientRequestDataNotRawNetwork() throws {
        let source = try Self.source("Services/StorageResource/EngineWebViewSchemeHandler.swift")

        XCTAssertTrue(
            source.contains("client.requestData("),
            "EngineWebViewSchemeHandler must fetch via FicheroClient.requestData so it "
                + "rides the active transport (.uds/.https/.inMemory), not a raw network call"
        )
        // Forbidden: any raw HTTP/URLSession path would bypass the transport and
        // silently fail over UDS/in-memory (the original #4066 symptom).
        XCTAssertFalse(
            source.contains("URLSession"),
            "The handler must not dial URLSession directly; it goes through client.requestData"
        )
        XCTAssertFalse(
            source.contains("https://127.0.0.1"),
            "The handler must not hard-code the HTTP listener URL; UDS/in-memory have none"
        )
        XCTAssertFalse(
            source.contains("EngineConfig.host"),
            "The handler must not read EngineConfig.host; the transport, not a host, carries the request"
        )
        XCTAssertFalse(
            source.contains("RemoteCertificatePinning"),
            "The handler must not pin a cert; the active transport handles TLS where relevant"
        )
    }

    /// The handler MUST map `fichero-engine://` URLs to engine paths via
    /// `EngineWebViewURL.enginePath(from:)` — the pure mapper covered by
    /// `EngineWebViewURLTests`. A regression that drops this breaks relative
    /// subresource routing (`/api/...`, `/view/static/...`).
    func testHandlerMapsURLToEnginePathBeforeFetch() throws {
        let source = try Self.source("Services/StorageResource/EngineWebViewSchemeHandler.swift")
        XCTAssertTrue(
            source.contains("EngineWebViewURL.enginePath(from:"),
            "The handler must map the fichero-engine:// URL to an engine path before requestData"
        )
    }

    // @MainActor: validateResponseSize is main-actor-isolated (the handler
    // class is); calling it from a nonisolated test broke the whole
    // FicheroTests bundle at compile.
    @MainActor
    func testHandlerAcceptsLimitAndRejectsOneByteOverBeforeWebKitReceivesData() throws {
        let limit = 100 * 1024 * 1024
        XCTAssertNoThrow(try EngineWebViewSchemeHandler.validateResponseSize(byteCount: limit))
        XCTAssertThrowsError(try EngineWebViewSchemeHandler.validateResponseSize(byteCount: limit + 1)) { error in
            XCTAssertEqual(
                error.localizedDescription,
                "Engine response of \(limit + 1) bytes exceeds the \(limit)-byte limit"
            )
        }

        let source = try Self.source("Services/StorageResource/EngineWebViewSchemeHandler.swift")
        let checkIndex = try XCTUnwrap(source.range(of: "try Self.validateResponseSize"))
        let receiveIndex = try XCTUnwrap(source.range(of: "urlSchemeTask.didReceive(response)"))
        XCTAssertLessThan(checkIndex.lowerBound, receiveIndex.lowerBound)
    }

    // MARK: - Pane wires the handler to the library's FicheroClient (both platforms)

    /// macOS: the KG pane registers `EngineWebViewSchemeHandler` keyed to the
    /// library's `FicheroClient` from `DocumentKGPaneRoute.webViewClient`, using
    /// the active `LibraryManager`. That client's `transportMode` follows
    /// provisioning — `.uds` for the
    /// release-embedded spawn, `.inMemory` for the python-kit load — so the
    /// pane rides the right transport automatically.
    func testMacOSPaneRegistersHandlerWithLibraryClient() throws {
        let source = try Self.source("Views/Reader/Knowledge/DocumentKGWebPane.swift")
        XCTAssertTrue(
            source.contains(
                "DocumentKGPaneRoute.webViewClient(libraryPath: libraryPath, libraryManager: libraryManager)"
            ),
            "macOS pane must resolve the library's FicheroClient through the active LibraryManager"
        )
        XCTAssertTrue(
            source.contains("EngineWebViewSchemeHandler(client: client)"),
            "macOS pane must register EngineWebViewSchemeHandler with that client"
        )
        XCTAssertTrue(
            source.contains("forURLScheme: EngineWebViewURL.scheme"),
            "macOS pane must register the handler for the fichero-engine scheme"
        )
    }

    /// iOS: same wiring as macOS. Both panes must route through the transport.
    func testIOSPaneRegistersHandlerWithLibraryClient() throws {
        let source = try Self.source("Views/Reader/Knowledge/DocumentKGWebPane.swift")
        // The iOS branch appears after `#elseif canImport(UIKit)`; assert it
        // carries the same client-keyed handler registration. Two occurrences
        // (macOS + iOS) prove both platforms wire it.
        let registrations = source.components(separatedBy: "EngineWebViewSchemeHandler(client: client)").count - 1
        XCTAssertEqual(
            registrations,
            2,
            "Both macOS and iOS panes must register EngineWebViewSchemeHandler(client: client); "
                + "found \(registrations) — one platform is missing the transport-routed handler"
        )
    }

    // MARK: - Sibling WKWebView panes (fix-then-sweep-for-siblings)

    /// The workflow-diagram mermaid pane is fully self-contained (bundled
    /// `mermaid.min.js`, `loadHTMLString` with `baseURL: nil`, no navigation) so
    /// it has no transport dependency. Pin that so a future change doesn't
    /// quietly route it at the HTTP listener.
    func testWorkflowMermaidPaneIsSelfContainedAndTransportAgnostic() throws {
        let source = try Self.source("Views/Workflow/Canvas/WorkflowMermaidView.swift")
        XCTAssertTrue(
            source.contains("loadHTMLString(html, baseURL: nil)"),
            "Mermaid pane must load bundled HTML with baseURL: nil (no network/transport)"
        )
        XCTAssertFalse(
            source.contains("EngineConfig.host"),
            "Mermaid pane must not reference the engine HTTP host"
        )
        XCTAssertFalse(
            source.contains("https://127.0.0.1"),
            "Mermaid pane must not load from the HTTP listener"
        )
    }

    /// The generic `FicheroWebView` (research browser) loads arbitrary URLs and
    /// only registers the `fichero-res://` storage scheme (transport-agnostic).
    /// It must NOT dial the engine `/view/...` pages, so it doesn't need the
    /// `fichero-engine://` handler — pinning that it stays out keeps the sweep
    /// honest.
    func testFicheroWebViewDoesNotLoadEnginePagesRequiringEngineScheme() throws {
        let source = try Self.source("Views/Components/FicheroWebView.swift")
        XCTAssertTrue(
            source.contains("StorageResourceSchemeHandler()"),
            "FicheroWebView must keep the fichero-res:// storage handler (transport-agnostic)"
        )
        XCTAssertFalse(
            source.contains("EngineWebViewSchemeHandler"),
            "FicheroWebView is a generic browser; it must not register the engine-page handler"
        )
        XCTAssertFalse(
            source.contains("fichero-engine://"),
            "FicheroWebView must not target the engine-page scheme"
        )
    }
}
