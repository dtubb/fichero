@testable import Fichero
import XCTest

/// #4329 — a conversion artifact routes to the RIGHT renderer: WebKit for
/// html/svg, rendered Markdown otherwise; the server's target_format stamp
/// wins, sniffing covers legacy artifacts saved before the stamp existed.
@MainActor
final class RenditionRoutingTests: XCTestCase {

    private func artifact(content: String, format: String? = nil) -> Artifact {
        Artifact(
            documentId: "doc-1",
            artifactType: "conversion",
            content: content,
            data: format.map { ["target_format": AnyCodable($0)] }
        )
    }

    func testStampedSVGRoutesToSVGCanvas() {
        let content = "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>"
        let route = DocumentCanvas.renditionContent(for: artifact(content: content, format: "svg"))
        guard case .svg(let svg) = route else {
            return XCTFail("expected .svg, got \(route)")
        }
        XCTAssertEqual(svg, content)
    }

    func testStampedHTMLRoutesToHTMLCanvas() {
        let route = DocumentCanvas.renditionContent(
            for: artifact(content: "<html><body>hi</body></html>", format: "html")
        )
        guard case .html = route else {
            return XCTFail("expected .html, got \(route)")
        }
    }

    func testStampedMarkdownRoutesToMarkdownCanvas() {
        let route = DocumentCanvas.renditionContent(
            for: artifact(content: "# Title", format: "markdown")
        )
        guard case .markdown(let text) = route else {
            return XCTFail("expected .markdown, got \(route)")
        }
        XCTAssertEqual(text, "# Title")
    }

    func testUnstampedLegacyArtifactIsSniffed() {
        XCTAssertEqual(DocumentCanvas.sniffRenditionFormat("<svg viewBox=\"0 0 1 1\"/>"), "svg")
        XCTAssertEqual(DocumentCanvas.sniffRenditionFormat("<!doctype html><p>x</p>"), "html")
        XCTAssertEqual(DocumentCanvas.sniffRenditionFormat("# Just markdown"), "markdown")

        let route = DocumentCanvas.renditionContent(
            for: artifact(content: "<svg xmlns=\"a\"></svg>")
        )
        guard case .svg = route else {
            return XCTFail("expected sniffed .svg, got \(route)")
        }
    }

    func testSVGShellCentersAndConstrainsTheDrawing() {
        let canvas = WebContentCanvas(content: "<svg id=\"x\"></svg>", kind: .svg)
        XCTAssertTrue(canvas.htmlDocument.contains("<svg id=\"x\"></svg>"))
        XCTAssertTrue(canvas.htmlDocument.contains("max-width: 100%"))
        // HTML loads verbatim — no shell injected around a full document.
        let html = WebContentCanvas(content: "<html><body>y</body></html>", kind: .html)
        XCTAssertEqual(html.htmlDocument, "<html><body>y</body></html>")
    }
}
