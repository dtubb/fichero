import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

/// Regression coverage for #2538: after the engine moved to a self-signed
/// pinned HTTPS loopback cert, the KG / document-reader WKWebView pane
/// (`DocumentKGWebPane`) stopped rendering because
/// `supportsAuthenticatedWebView()` gated itself off whenever pinning was
/// enforced. The pane now validates the pinned cert in its navigation
/// delegate, so it must load over the shared pinned HTTPS transport instead.
final class DocumentKGPaneRouteTests: XCTestCase {
    private var host: URL!
    private var hostString: String!
    private let pin = Data("kg-pane-loopback-spki".utf8).base64EncodedString()

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

    /// With a persisted SPKI pin, the pane must report itself available even
    /// though pinning is enforced — the delegate validates the cert. Before the
    /// fix this returned `false` (it was `!shouldEnforcePinning(...)`), which
    /// is exactly why the KG + reader surfaces came up empty.
    func testWebViewAvailableWhenLoopbackPinned() throws {
        try RemoteCertificatePinning.persistSPKIPin(pin, hostString: hostString)
        XCTAssertTrue(DocumentKGPaneRoute.supportsAuthenticatedWebView())
    }

    /// The global-KG request now loads over the custom `fichero-engine://engine`
    /// origin, NOT a raw `https://…:8765` URL — `EngineWebViewSchemeHandler`
    /// funnels it through the transport-agnostic `FicheroClient` so it works over
    /// `.uds`/in-memory too (the old raw URL failed `-1004` over a socket). Auth +
    /// the per-library header are delegated to `requestData`'s middleware, so no
    /// header is hand-stamped on this request.
    func testGlobalKGRequestUsesEngineSchemeAndDelegatesAuth() throws {
        try RemoteCertificatePinning.persistSPKIPin(pin, hostString: hostString)

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
        try RemoteCertificatePinning.persistSPKIPin(pin, hostString: hostString)

        let request = try XCTUnwrap(
            DocumentKGPaneRoute.request(
                documentId: DocumentKGPaneRoute.globalKGDocumentID,
                libraryPath: "/tmp/Chocó.fichero"
            )
        )

        XCTAssertEqual(request.url?.scheme, EngineWebViewURL.scheme)
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Fichero-Library-Path"))
    }

    /// A per-document reader request likewise loads over the `fichero-engine://`
    /// origin, with the document id percent-encoded into the path.
    func testDocumentReaderRequestUsesEngineScheme() throws {
        try RemoteCertificatePinning.persistSPKIPin(pin, hostString: hostString)

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
        let fixtureBase = URL(fileURLWithPath: #filePath)
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
