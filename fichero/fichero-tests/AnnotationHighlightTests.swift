@testable import Fichero
import XCTest

/// Tests for the pure highlight-range computation behind the reader annotation
/// rendering (#2458). Stale/out-of-bounds spans must degrade gracefully.
final class AnnotationHighlightTests: XCTestCase {

    private func annotation(_ start: Int?, _ end: Int?, kind: AnnotationKind = .highlight) -> DocumentAnnotation {
        DocumentAnnotation(id: UUID().uuidString, pageId: "p1", charStart: start, charEnd: end, kind: kind)
    }

    func testValidSpanProducesRange() {
        let ranges = AnnotationHighlight.ranges(for: [annotation(2, 5)], inUTF16Count: 10)
        XCTAssertEqual(ranges, [2..<5])
    }

    func testSpanEndAtContentLengthIsKept() {
        let ranges = AnnotationHighlight.ranges(for: [annotation(0, 10)], inUTF16Count: 10)
        XCTAssertEqual(ranges, [0..<10])
    }

    func testSpanBeyondContentIsSkipped() {
        // Stale offsets after the page was edited shorter.
        let ranges = AnnotationHighlight.ranges(for: [annotation(8, 20)], inUTF16Count: 10)
        XCTAssertTrue(ranges.isEmpty)
    }

    func testEmptyOrInvertedSpanIsSkipped() {
        XCTAssertTrue(AnnotationHighlight.ranges(for: [annotation(5, 5)], inUTF16Count: 10).isEmpty)
        XCTAssertTrue(AnnotationHighlight.ranges(for: [annotation(6, 4)], inUTF16Count: 10).isEmpty)
    }

    func testNegativeStartIsSkipped() {
        XCTAssertTrue(AnnotationHighlight.ranges(for: [annotation(-1, 4)], inUTF16Count: 10).isEmpty)
    }

    func testAnnotationWithoutSpanIsSkipped() {
        XCTAssertTrue(AnnotationHighlight.ranges(for: [annotation(nil, nil, kind: .note)], inUTF16Count: 10).isEmpty)
        XCTAssertTrue(AnnotationHighlight.ranges(for: [annotation(3, nil)], inUTF16Count: 10).isEmpty)
    }

    func testRangesAreSortedByStart() {
        let ranges = AnnotationHighlight.ranges(
            for: [annotation(6, 8), annotation(0, 2), annotation(3, 5)],
            inUTF16Count: 10
        )
        XCTAssertEqual(ranges, [0..<2, 3..<5, 6..<8])
    }
}
