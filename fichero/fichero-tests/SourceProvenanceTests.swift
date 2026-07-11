@testable import Fichero
import XCTest

/// ClaimAttribution — the shared speaker/attribution model behind the
/// provenance popover (#3449) and the editable speaker surface (#3448). Locks
/// the "who is asserting" display logic: a document-attributed claim vs a
/// person-attributed one read differently and use different glyphs.
final class SourceProvenanceTests: XCTestCase {

    func testDocumentAttributionSummaryAndGlyph() {
        let attribution = ClaimAttribution(kind: .document, name: "the article")
        XCTAssertEqual(attribution.summary, "the article says")
        XCTAssertEqual(attribution.systemImage, "doc.text")
    }

    func testPersonAttributionSummaryAndGlyph() {
        let attribution = ClaimAttribution(
            kind: .person,
            name: "Ada Lovelace",
            verbatimSpan: "the engine weaves algebraic patterns",
            locationLabel: "p. 12"
        )
        XCTAssertEqual(attribution.summary, "Ada Lovelace says")
        XCTAssertEqual(attribution.systemImage, "person")
        XCTAssertEqual(attribution.verbatimSpan, "the engine weaves algebraic patterns")
        XCTAssertEqual(attribution.locationLabel, "p. 12")
    }

    func testCropRequestBuiltFromNavAnchor() {
        // The popover feeds SourceSnippet a crop request derived from the same
        // source-nav anchor, so the evidence matches the row.
        let nav = ClaimSourceNavigationRequest(
            documentId: "doc-1",
            pageLabel: "12",
            pageIndex: 11,
            bbox: [0.1, 0.2, 0.5, 0.35]
        )
        let crop = SourceCropRequest(nav)
        XCTAssertEqual(crop.documentId, "doc-1")
        XCTAssertEqual(crop.bbox, [0.1, 0.2, 0.5, 0.35])
        XCTAssertEqual(crop.pageIndex, 11)
        XCTAssertEqual(crop.pageLabel, "12")
    }
}
