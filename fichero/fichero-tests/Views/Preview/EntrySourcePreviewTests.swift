@testable import Fichero
import XCTest

/// Preview-layers milestone 1 (#27, Daniel 2026-08-15): selecting an
/// extracted entry must preview its SOURCE page with the entry's bbox
/// highlighted — never repeat the entry's text in the preview pane.
@MainActor
final class EntrySourcePreviewTests: XCTestCase {
    private func entry(
        bbox: [Int]? = [100, 200, 400, 300],
        metadata: [String: AnyCodable] = ["source_document_id": AnyCodable("page-7")]
    ) -> Document {
        Document(
            id: "entry-1",
            parentId: "page-7-parent",
            docType: .file,
            name: "1919-01-03",
            bbox: bbox,
            metadata: metadata,
            pageContent: "High river. San José arrived at Paimadó.",
            prototypeKey: "diary_entry",
            nodeKind: "entry"
        )
    }

    func testEntryNodeRoutesToSourcePagePreviewNotItsOwnText() {
        let route = EditorView.previewRoute(for: entry(), isEditing: false)
        XCTAssertEqual(route, .entrySource)
        // Edit mode must not hijack an entry into the image editor either.
        XCTAssertEqual(EditorView.previewRoute(for: entry(), isEditing: true), .entrySource)
    }

    func testNonEntryTextDocumentStillRoutesToText() {
        let doc = Document(
            id: "note-1",
            docType: .file,
            name: "notes.txt",
            pageContent: "plain text"
        )
        XCTAssertEqual(
            EditorView.previewRoute(for: doc, isEditing: false),
            .text(content: "plain text")
        )
    }

    func testSourceDocumentIdPrefersStampedProvenanceOverTreeParent() {
        XCTAssertEqual(EntrySourcePreview.sourceDocumentId(of: entry()), "page-7")
        XCTAssertEqual(
            EntrySourcePreview.sourceDocumentId(of: entry(metadata: [:])),
            "page-7-parent",
            "older runs predate the source_document_id stamp — the tree parent is the fallback"
        )
    }

    func testNormalizedHighlightScalesPixelBboxByStampedPageDimensions() {
        let boxes = EntrySourcePreview.normalizedHighlight(
            bbox: [100, 200, 400, 300],
            sourceMetadata: ["width": AnyCodable(2000), "height": AnyCodable(1000)]
        )
        XCTAssertEqual(boxes.count, 1)
        XCTAssertEqual(boxes[0], [0.05, 0.2, 0.2, 0.3])
    }

    func testNormalizedHighlightAcceptsDoubleEncodedDimensions() {
        // JSON numbers can decode as Double — a bare `as? Int` would drop them.
        let boxes = EntrySourcePreview.normalizedHighlight(
            bbox: [0, 0, 500, 500],
            sourceMetadata: ["width": AnyCodable(1000.0), "height": AnyCodable(500.0)]
        )
        XCTAssertEqual(boxes, [[0, 0, 0.5, 1.0]])
    }

    func testNormalizedHighlightIsEmptyWithoutBboxOrDimensions() {
        // No bbox recorded (bbox_basis says why) → no guessed box.
        XCTAssertTrue(EntrySourcePreview.normalizedHighlight(
            bbox: nil,
            sourceMetadata: ["width": AnyCodable(2000), "height": AnyCodable(1000)]
        ).isEmpty)
        // No page dimensions → no box either.
        XCTAssertTrue(EntrySourcePreview.normalizedHighlight(
            bbox: [1, 2, 3, 4],
            sourceMetadata: [:]
        ).isEmpty)
        // Degenerate dimensions must not divide by zero.
        XCTAssertTrue(EntrySourcePreview.normalizedHighlight(
            bbox: [1, 2, 3, 4],
            sourceMetadata: ["width": AnyCodable(0), "height": AnyCodable(0)]
        ).isEmpty)
    }
}

// MARK: - Frame gate (2026-08-23)

extension EntrySourcePreviewTests {
    /// A region measured on a NAMED rendition must not highlight on the
    /// parent's base image — a plausible band in the wrong frame is the
    /// misplaced-spread-band bug's class. The pixel-bbox fallback still runs.
    func testRenditionNamedRegionNeverHighlightsOnTheParent() {
        var entry = Document(id: "e1", name: "Entry")
        entry.regionInParent = DocumentRegion(
            rect: [0.1, 0.2, 0.3, 0.4], space: "normalized",
            confidence: nil, method: nil, note: nil, renditionId: "r-crop"
        )
        XCTAssertTrue(EntrySourcePreview.highlight(for: entry, sourceMetadata: [:]).isEmpty)

        entry.regionInParent?.renditionId = nil
        XCTAssertEqual(
            EntrySourcePreview.highlight(for: entry, sourceMetadata: [:]),
            [[0.1, 0.2, 0.3, 0.4]]
        )
    }
}
