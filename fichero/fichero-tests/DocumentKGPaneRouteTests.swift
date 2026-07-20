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

    /// The global-KG request is built on the shared engine host: it MUST be an
    /// `https://` URL (never hand-rolled `http://localhost`) and carry the
    /// per-library engine-auth header.
    func testGlobalKGRequestIsHTTPSWithEngineAuth() throws {
        try RemoteCertificatePinning.persistSPKIPin(pin, hostString: hostString)

        let request = try XCTUnwrap(
            DocumentKGPaneRoute.request(
                documentId: DocumentKGPaneRoute.globalKGDocumentID,
                libraryPath: "/tmp/library"
            )
        )

        let url = try XCTUnwrap(request.url)
        XCTAssertEqual(url.scheme, "https")
        XCTAssertNotEqual(url.scheme, "http")
        XCTAssertTrue(url.absoluteString.hasSuffix("/view/kg/global"), url.absoluteString)
        // addEngineAuth always stamps the per-library header on engine requests.
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Fichero-Library-Path"), "/tmp/library")
    }

    /// A non-ASCII library path (diacritics, accented home dirs) must be
    /// percent-encoded in the transport header so it survives the latin-1 HTTP
    /// header pipeline; the engine `unquote`s it on read (#2648). Pure-ASCII
    /// paths are unaffected (encoding is a no-op), as the test above pins.
    func testNonASCIILibraryPathHeaderIsPercentEncoded() throws {
        try RemoteCertificatePinning.persistSPKIPin(pin, hostString: hostString)

        let request = try XCTUnwrap(
            DocumentKGPaneRoute.request(
                documentId: DocumentKGPaneRoute.globalKGDocumentID,
                libraryPath: "/tmp/Chocó.fichero"
            )
        )

        // ó (U+00F3) → UTF-8 0xC3 0xB3 → "%C3%B3"; "/" stays unencoded.
        XCTAssertEqual(
            request.value(forHTTPHeaderField: "X-Fichero-Library-Path"),
            "/tmp/Choc%C3%B3.fichero"
        )
    }

    /// A per-document reader request is likewise served over the pinned HTTPS
    /// transport, with the document id percent-encoded into the path.
    func testDocumentReaderRequestIsHTTPS() throws {
        try RemoteCertificatePinning.persistSPKIPin(pin, hostString: hostString)

        let request = try XCTUnwrap(
            DocumentKGPaneRoute.request(documentId: "doc-123", libraryPath: "/tmp/library")
        )

        let url = try XCTUnwrap(request.url)
        XCTAssertEqual(url.scheme, "https")
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
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("fichero")
                .appendingPathComponent("Views/Reader/Knowledge/DocumentKGWebPane.swift"),
            encoding: .utf8
        ) + String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("fichero")
                .appendingPathComponent("Views/Reader/Knowledge/DocumentKGWebPaneCoordinatorMacOS.swift"),
            encoding: .utf8
        ) + String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("fichero")
                .appendingPathComponent("Views/Reader/Knowledge/DocumentKGWebPaneCoordinatoriOS.swift"),
            encoding: .utf8
        )

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
