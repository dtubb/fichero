import XCTest
@testable import FicheroAPIClient

/// Headless coverage for the `fichero-engine://` URL mapping + MIME inference —
/// the pure core the KG web-pane `WKURLSchemeHandler` uses to funnel a WKWebView
/// page load through `FicheroClient.requestData(...)` over any transport. No
/// networking, no WebKit, no app types.
final class EngineWebViewURLTests: XCTestCase {

    // MARK: - make / enginePath round-trip

    func testMakeProducesSchemeHostAndPath() {
        let url = EngineWebViewURL.make(path: "/view/document/abc123")
        XCTAssertEqual(url?.scheme, "fichero-engine")
        XCTAssertEqual(url?.host, "engine")
        XCTAssertEqual(url?.path, "/view/document/abc123")
    }

    func testEnginePathRoundTripsThePage() {
        let url = EngineWebViewURL.make(path: "/view/kg/global")!
        XCTAssertEqual(EngineWebViewURL.enginePath(from: url), "/view/kg/global")
    }

    func testEnginePathMapsRelativeSubresources() {
        // The page's relative `/api/…` + `/view/static/…` fetches resolve against
        // the `fichero-engine://engine` origin and must map back to bare engine
        // paths.
        let api = URL(string: "fichero-engine://engine/api/kg/graph/metrics")!
        XCTAssertEqual(EngineWebViewURL.enginePath(from: api), "/api/kg/graph/metrics")
        let asset = URL(string: "fichero-engine://engine/view/static/app.js")!
        XCTAssertEqual(EngineWebViewURL.enginePath(from: asset), "/view/static/app.js")
    }

    func testEnginePathRejectsForeignScheme() {
        XCTAssertNil(EngineWebViewURL.enginePath(from: URL(string: "https://127.0.0.1:8765/view/document/x")!))
    }

    // MARK: - query items

    func testQueryItemsForwardedVerbatim() {
        let url = URL(string: "fichero-engine://engine/api/kg/graph?doc=d1&mode=focus")!
        let items = EngineWebViewURL.queryItems(from: url)
        XCTAssertEqual(items, [URLQueryItem(name: "doc", value: "d1"),
                               URLQueryItem(name: "mode", value: "focus")])
    }

    func testNoQueryItemsIsEmpty() {
        let url = EngineWebViewURL.make(path: "/view/document/x")!
        XCTAssertTrue(EngineWebViewURL.queryItems(from: url).isEmpty)
    }

    // MARK: - MIME inference

    func testPageRoutesAreHTML() {
        XCTAssertEqual(EngineWebViewURL.mimeType(forPath: "/view/document/abc"), "text/html; charset=utf-8")
        XCTAssertEqual(EngineWebViewURL.mimeType(forPath: "/view/kg/global"), "text/html; charset=utf-8")
    }

    func testApiPathsAreJSON() {
        XCTAssertEqual(EngineWebViewURL.mimeType(forPath: "/api/kg/graph/metrics"), "application/json")
    }

    func testAssetExtensionsWin() {
        XCTAssertEqual(EngineWebViewURL.mimeType(forPath: "/view/static/app.js"), "text/javascript; charset=utf-8")
        XCTAssertEqual(EngineWebViewURL.mimeType(forPath: "/view/static/app.css"), "text/css; charset=utf-8")
        XCTAssertEqual(EngineWebViewURL.mimeType(forPath: "/view/static/logo.svg"), "image/svg+xml")
        XCTAssertEqual(EngineWebViewURL.mimeType(forPath: "/view/static/f.woff2"), "font/woff2")
        // Extension wins even under the /api/ prefix.
        XCTAssertEqual(EngineWebViewURL.mimeType(forPath: "/api/thing.json"), "application/json")
    }
}
