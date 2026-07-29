import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

/// Contract coverage for the KG pane's routing after the availability gate
/// was retired (approved 2026-07-27; lineage #2538 → #4066). Every load
/// routes through the custom `fichero-server://` scheme, whose handler
/// re-issues requests via `FicheroClient.requestData` — the layer that
/// applies auth AND SPKI pinning (transport proof: the #4066 tests
/// `EngineWebViewSchemeHandlerRoutingTests` / `EngineWebViewRoutingTests`
/// cover UDS + in-memory routing). The pane therefore never refuses a host
/// itself, and no persisted pin is required for the ROUTE to form.
final class DocumentKGPaneRouteTests: XCTestCase {
    private var host: URL!
    private var hostString: String!

    override func setUp() {
        super.setUp()
        host = EngineConfig.host
        hostString = host.absoluteString
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostString)
    }

    override func tearDown() {
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostString)
        host = nil
        hostString = nil
        super.tearDown()
    }

    /// The pane never gates on host or persisted pin: with NO pin stored the
    /// request must still form. (The old `supportsAuthenticatedWebView()`
    /// returned nil here for pinned remote hosts — a dead switch once the
    /// scheme handler owned auth/pinning — which blanked the KG pane over
    /// remote/UDS transports.)
    func testRequestFormsWithNoPersistedPin() throws {
        let request = try XCTUnwrap(
            DocumentKGPaneRoute.request(
                documentId: DocumentKGPaneRoute.globalKGDocumentID,
                libraryPath: "/tmp/library"
            )
        )
        XCTAssertEqual(request.url?.scheme, EngineWebViewURL.scheme)
    }

    /// The gate and its remote-host "unavailable" page are gone from the pane
    /// sources; the only fallback left is the honest LOAD-FAILURE page. The
    /// security property did not disappear — it moved: FicheroClient's
    /// transport applies SPKI pinning for every request the scheme handler
    /// re-issues, so assert the pinning hook still lives there.
    func testAvailabilityGateIsRetiredAndPinningLivesInTheClient() throws {
        let fixtureBase = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let paneSources = try [
            "fichero/Views/Reader/Knowledge/DocumentKGWebPane+Route.swift",
            "fichero/Views/Reader/Knowledge/DocumentKGWebPane.swift",
            "fichero/Views/Reader/Knowledge/DocumentKGWebPaneCoordinatorMacOS.swift",
            "fichero/Views/Reader/Knowledge/DocumentKGWebPaneCoordinatoriOS.swift"
        ]
        .map { try String(contentsOf: fixtureBase.appendingPathComponent($0), encoding: .utf8) }
        .joined(separator: "\n")

        XCTAssertFalse(paneSources.contains("func supportsAuthenticatedWebView"))
        XCTAssertFalse(paneSources.contains("unavailableHTML"))
        XCTAssertTrue(paneSources.contains("loadFailureHTML(detail:"))

        let client = try String(
            contentsOf: fixtureBase.appendingPathComponent(
                "fichero-api-client/Sources/FicheroAPIClient/FicheroClient.swift"
            ),
            encoding: .utf8
        )
        XCTAssertTrue(
            client.contains("RemoteCertificatePinning"),
            "SPKI pinning must keep living in the client transport the scheme handler uses"
        )
    }

    /// The failure page shows the engine's real error and can't be used to
    /// inject markup through an attacker-influenced error string.
    func testLoadFailureHTMLEscapesDetail() {
        let html = DocumentKGPaneRoute.loadFailureHTML(detail: "boom <script>alert(1)</script> & more")
        XCTAssertTrue(html.contains("boom &lt;script&gt;alert(1)&lt;/script&gt; &amp; more"))
        XCTAssertFalse(html.contains("<script>alert(1)</script>"))
        XCTAssertTrue(html.contains("failed to load"))
    }

    /// The global-KG request now loads over the custom `fichero-server://engine`
    /// origin, NOT a raw `https://…:8765` URL — `EngineWebViewSchemeHandler`
    /// funnels it through the transport-agnostic `FicheroClient` so it works over
    /// `.uds`/in-memory too (the old raw URL failed `-1004` over a socket). Auth +
    /// the per-library header are delegated to `requestData`'s middleware, so no
    /// header is hand-stamped on this request.
    func testGlobalKGRequestUsesEngineSchemeAndDelegatesAuth() throws {
        let request = try XCTUnwrap(
            DocumentKGPaneRoute.request(
                documentId: DocumentKGPaneRoute.globalKGDocumentID,
                libraryPath: "/tmp/library"
            )
        )

        let url = try XCTUnwrap(request.url)
        XCTAssertEqual(url.scheme, EngineWebViewURL.scheme)
        XCTAssertEqual(url.host, EngineWebViewURL.host)
        XCTAssertTrue(url.absoluteString.hasSuffix("/view/kg/global"), url.absoluteString)
        // Auth is applied by the scheme handler's requestData middleware, never a
        // header on this navigation request (the handler doesn't forward headers).
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Fichero-Library-Path"))
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
    }

    /// A non-ASCII library path must not break request construction. Because the
    /// scheme handler delegates library scoping to `requestData` (which the
    /// `LibraryPathMiddleware` percent-encodes for the latin-1 header pipeline,
    /// #2648), the KG request itself carries no per-library header regardless of
    /// the path's characters.
    func testNonASCIILibraryPathStillBuildsEngineRequest() throws {
        let request = try XCTUnwrap(
            DocumentKGPaneRoute.request(
                documentId: DocumentKGPaneRoute.globalKGDocumentID,
                libraryPath: "/tmp/Chocó.fichero"
            )
        )

        XCTAssertEqual(request.url?.scheme, EngineWebViewURL.scheme)
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Fichero-Library-Path"))
    }

    /// A per-document reader request likewise loads over the `fichero-server://`
    /// origin, with the document id percent-encoded into the path.
    func testDocumentReaderRequestUsesEngineScheme() throws {
        let request = try XCTUnwrap(
            DocumentKGPaneRoute.request(documentId: "doc-123", libraryPath: "/tmp/library")
        )

        let url = try XCTUnwrap(request.url)
        XCTAssertEqual(url.scheme, EngineWebViewURL.scheme)
        XCTAssertTrue(url.absoluteString.hasSuffix("/view/document/doc-123"), url.absoluteString)
    }

    func testBootstrapScriptRefreshesOnlyWhenNeeded() {
        XCTAssertTrue(
            DocumentKGPaneRoute.shouldRefreshBootstrapScript(
                hasCachedScript: false,
                cachedLibraryPath: nil,
                libraryPath: "/tmp/library",
                force: false
            )
        )
        XCTAssertFalse(
            DocumentKGPaneRoute.shouldRefreshBootstrapScript(
                hasCachedScript: true,
                cachedLibraryPath: "/tmp/library",
                libraryPath: "/tmp/library",
                force: false
            )
        )
        XCTAssertTrue(
            DocumentKGPaneRoute.shouldRefreshBootstrapScript(
                hasCachedScript: true,
                cachedLibraryPath: "/tmp/old",
                libraryPath: "/tmp/library",
                force: false
            )
        )
        XCTAssertTrue(
            DocumentKGPaneRoute.shouldRefreshBootstrapScript(
                hasCachedScript: true,
                cachedLibraryPath: "/tmp/library",
                libraryPath: "/tmp/library",
                force: true
            )
        )
    }

    func testBootstrapScriptDoesNotExposeRealTokenOnWindow() {
        let script = DocumentKGPaneRoute.bootstrapScript(token: "secret-token", libraryPath: "/tmp/library")

        XCTAssertTrue(script.contains("window.ficheroToken = nativeTokenSentinel"))
        XCTAssertTrue(script.contains("window.fetch = function(input, init)"))
        XCTAssertTrue(script.contains("headers.set('Authorization', 'Bearer ' + nativeToken)"))
        XCTAssertFalse(script.contains("window.ficheroToken = 'secret-token'"))
    }

    func testBootstrapScriptSealsFetchSoItCannotBeRewrapped() {
        // #3223 hardening: the fetch override is sealed non-writable/non-configurable
        // so a later page script (or an XSS in the reader templates) can't re-wrap
        // window.fetch to capture the real token swapped into proxied requests.
        let script = DocumentKGPaneRoute.bootstrapScript(token: "secret-token", libraryPath: "/tmp/library")

        XCTAssertTrue(script.contains("Object.defineProperty(window, 'fetch'"))
        XCTAssertTrue(script.contains("writable: false"))
        XCTAssertTrue(script.contains("configurable: false"))
    }

    func testReaderPaneCachesBootstrapScriptBetweenUpdates() throws {
        let fixtureBase = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
        let relativePaths = [
            "Views/Reader/Knowledge/DocumentKGWebPane.swift",
            "Views/Reader/Knowledge/DocumentKGWebPaneCoordinatoriOS.swift",
            "Views/Reader/Knowledge/DocumentKGWebPaneCoordinatorMacOS.swift"
        ]
        let source = try relativePaths
            .map { try String(contentsOf: fixtureBase.appendingPathComponent($0), encoding: .utf8) }
            .joined(separator: "\n")

        XCTAssertTrue(source.contains("cachedBootstrapScript"))
        XCTAssertTrue(source.contains("cachedBootstrapLibraryPath"))
        XCTAssertTrue(source.contains("shouldRefreshBootstrapScript"))
        XCTAssertTrue(source.contains("context.coordinator.bootstrapScript(forceRefresh: true)"))
        XCTAssertFalse(source.contains("let script = DocumentKGPaneRoute.bootstrapScript("))
        XCTAssertFalse(source.contains("webView.evaluateJavaScript(script)"))
    }

    func testScrollSyncUsesMeasuredTranscriptPageAnchors() {
        let script = DocumentKGPaneRoute.scrollSyncScript(pageCount: 3)

        // Real per-page DOM anchors, measured (not a proportional estimate):
        // offsets come from getBoundingClientRect/scrollTop, scroll→page maps by
        // range containment, and page→scroll uses scrollIntoView (#3226).
        XCTAssertTrue(script.contains("data-page"))
        XCTAssertTrue(script.contains("getBoundingClientRect"))
        XCTAssertTrue(script.contains("pageForScroll"))
        XCTAssertTrue(script.contains("scrollIntoView"))
        XCTAssertTrue(script.contains("addEventListener('scroll'"))
        // No proportional scroll↔page estimation may creep back in.
        XCTAssertFalse(script.contains("progress * maxScroll"))
        XCTAssertFalse(script.contains("scrollTop / maxScroll"))
    }
}
