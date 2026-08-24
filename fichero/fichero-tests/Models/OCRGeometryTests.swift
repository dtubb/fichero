@testable import Fichero
import XCTest

/// #4309 — the app-side OCR geometry contract: snake_case decode from the
/// backend payload, level filters, and the box↔text span link surviving the
/// round trip.
final class OCRGeometryTests: XCTestCase {

    private let payload = """
    {
      "text": "Hello world",
      "provider": "apple_vision",
      "model": "VNRecognizeTextRequest",
      "boxes": [
        {"text": "Hello world", "bbox": [0.1, 0.2, 0.6, 0.1], "level": "line",
         "confidence": 0.97, "page_index": 2, "char_start": 0, "char_end": 11},
        {"text": "Hello", "bbox": [0.1, 0.2, 0.25, 0.1], "level": "word",
         "char_start": 0, "char_end": 5},
        {"text": "world", "bbox": [0.4, 0.2, 0.3, 0.1], "level": "word",
         "char_start": 6, "char_end": 11}
      ]
    }
    """

    private func decode() throws -> OCRGeometry {
        try JSONDecoder().decode(OCRGeometry.self, from: Data(payload.utf8))
    }

    func testDecodesSnakeCasePayload() throws {
        let geometry = try decode()
        XCTAssertEqual(geometry.text, "Hello world")
        XCTAssertEqual(geometry.provider, "apple_vision")
        XCTAssertEqual(geometry.boxes.count, 3)
        let line = try XCTUnwrap(geometry.boxes.first)
        XCTAssertEqual(line.pageIndex, 2)
        XCTAssertEqual(line.confidence ?? 0, 0.97, accuracy: 0.0001)
    }

    func testLevelFiltersSplitLinesAndWords() throws {
        let geometry = try decode()
        XCTAssertEqual(geometry.lineBoxes.map(\.text), ["Hello world"])
        XCTAssertEqual(geometry.wordBoxes.map(\.text), ["Hello", "world"])
    }

    func testCharSpansSliceTheOwningText() throws {
        let geometry = try decode()
        for box in geometry.boxes {
            let start = try XCTUnwrap(box.charStart)
            let end = try XCTUnwrap(box.charEnd)
            let startIndex = geometry.text.index(geometry.text.startIndex, offsetBy: start)
            let endIndex = geometry.text.index(geometry.text.startIndex, offsetBy: end)
            XCTAssertEqual(String(geometry.text[startIndex..<endIndex]), box.text)
        }
    }

    func testArtifactDecodesOCRGeometry() throws {
        let artifactJSON = """
        {
          "id": "a1", "document_id": "d1", "version": 1,
          "artifact_type": "transcription", "content": "Hello world",
          "reviewed": false, "created_at": "2026-07-29T00:00:00Z",
          "ocr_geometry": \(payload)
        }
        """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let artifact = try decoder.decode(Artifact.self, from: Data(artifactJSON.utf8))
        XCTAssertEqual(artifact.ocrGeometry?.boxes.count, 3)
        XCTAssertEqual(artifact.ocrGeometry?.wordBoxes.first?.text, "Hello")
    }
}

// MARK: - Frame identity (2026-08-23, entry-scoped runs)

extension OCRGeometryTests {
    /// `rendition_id` names the PICTURE the whole set was measured on; absent
    /// means the document's own frame — every pre-existing artifact.
    func testRenditionIdDecodesOnTheSetAndDefaultsNil() throws {
        let named = """
        {"text": "x", "provider": "apple", "boxes": [], "rendition_id": "r-crop-1"}
        """
        let bare = """
        {"text": "x", "provider": "apple", "boxes": []}
        """
        let decoder = JSONDecoder()
        XCTAssertEqual(
            try decoder.decode(OCRGeometry.self, from: Data(named.utf8)).renditionId,
            "r-crop-1"
        )
        XCTAssertNil(try decoder.decode(OCRGeometry.self, from: Data(bare.utf8)).renditionId)
    }

    /// A DocumentRegion measured on a named rendition is NOT in the parent's
    /// frame — the flag every zoom/highlight consumer gates on.
    func testRegionFrameFlag() throws {
        let named = """
        {"rect": [0.1, 0.2, 0.3, 0.4], "rendition_id": "r-1"}
        """
        let bare = """
        {"rect": [0.1, 0.2, 0.3, 0.4]}
        """
        let decoder = JSONDecoder()
        XCTAssertFalse(try decoder.decode(DocumentRegion.self, from: Data(named.utf8)).isInParentFrame)
        XCTAssertTrue(try decoder.decode(DocumentRegion.self, from: Data(bare.utf8)).isInParentFrame)
    }
}
