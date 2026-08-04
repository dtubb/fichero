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
