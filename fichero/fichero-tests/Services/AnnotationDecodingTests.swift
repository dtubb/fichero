@testable import Fichero
import XCTest

/// Tests for AnnotationKind + DocumentAnnotation decode/display logic.
/// AnnotationServiceTests covers matchesSearch + endpoint wiring, but the
/// tolerant custom decoders (unknown-kind fallback, decodeIfPresent defaults)
/// and the geometry/computed helpers were untested. All headless value logic.
final class AnnotationDecodingTests: XCTestCase {

    // MARK: - AnnotationKind: tolerant decode + display

    func testKindDecodesKnownRawValues() throws {
        let cases: [(String, AnnotationKind)] = [
            ("highlight", .highlight), ("note", .note), ("rating", .rating),
            ("bookmark", .bookmark), ("comment", .comment), ("unknown", .unknown)
        ]
        for (raw, expected) in cases {
            let decoded = try JSONDecoder().decode(AnnotationKind.self,
                                                   from: Data("\"\(raw)\"".utf8))
            XCTAssertEqual(decoded, expected, "raw=\(raw)")
        }
    }

    /// An unrecognized backend kind must degrade to .unknown, never throw.
    func testKindUnknownRawFallsBackToUnknown() throws {
        for raw in ["\"sticker\"", "\"HIGHLIGHT\"", "\"\""] {
            let decoded = try JSONDecoder().decode(AnnotationKind.self,
                                                   from: Data(raw.utf8))
            XCTAssertEqual(decoded, .unknown, "raw=\(raw)")
        }
    }

    func testKindIcons() {
        XCTAssertEqual(AnnotationKind.highlight.icon, "highlighter")
        XCTAssertEqual(AnnotationKind.note.icon, "note.text")
        XCTAssertEqual(AnnotationKind.rating.icon, "star")
        XCTAssertEqual(AnnotationKind.bookmark.icon, "bookmark")
        XCTAssertEqual(AnnotationKind.comment.icon, "bubble.left")
        XCTAssertEqual(AnnotationKind.unknown.icon, "questionmark.circle")
    }

    func testKindLabels() {
        XCTAssertEqual(AnnotationKind.highlight.label, "Highlight")
        XCTAssertEqual(AnnotationKind.comment.label, "Comment")
        // .unknown gets a friendly name rather than "Unknown".
        XCTAssertEqual(AnnotationKind.unknown.label, "Annotation")
    }

    // MARK: - DocumentAnnotation: snake_case decode + defaults

    func testAnnotationDecodesSnakeCaseAndAllLinkArrays() throws {
        let json = Data("""
        {
            "id": "a-1",
            "document_id": "doc-9",
            "page_id": "p-1",
            "page_index": 2,
            "char_start": 10,
            "char_end": 25,
            "bbox": [1.0, 2.0, 30.0, 40.0],
            "kind": "highlight",
            "text": "hi",
            "tags": ["x"],
            "linked_claim_ids": ["c1"],
            "linked_entity_ids": ["e1"],
            "linked_note_ids": ["n1"],
            "created_by": "me",
            "created_at": "2026-05-10T10:00:00Z"
        }
        """.utf8)
        let ann = try JSONDecoder().decode(DocumentAnnotation.self, from: json)
        XCTAssertEqual(ann.id, "a-1")
        XCTAssertEqual(ann.documentId, "doc-9")   // ← document_id
        XCTAssertEqual(ann.pageIndex, 2)           // ← page_index
        XCTAssertEqual(ann.charStart, 10)
        XCTAssertEqual(ann.charEnd, 25)
        XCTAssertEqual(ann.kind, .highlight)
        XCTAssertEqual(ann.linkedClaimIds, ["c1"])
        XCTAssertEqual(ann.linkedEntityIds, ["e1"])
        XCTAssertEqual(ann.linkedNoteIds, ["n1"])
        XCTAssertEqual(ann.createdBy, "me")
    }

    /// Minimal payload: absent arrays default to [], absent kind → .unknown.
    func testAnnotationMinimalPayloadAppliesDefaults() throws {
        let json = Data("""
        { "id": "a-2" }
        """.utf8)
        let ann = try JSONDecoder().decode(DocumentAnnotation.self, from: json)
        XCTAssertEqual(ann.id, "a-2")
        XCTAssertNil(ann.documentId)
        XCTAssertEqual(ann.kind, .unknown)          // missing kind → .unknown
        XCTAssertEqual(ann.tags, [])
        XCTAssertEqual(ann.linkedClaimIds, [])
        XCTAssertEqual(ann.linkedEntityIds, [])
        XCTAssertEqual(ann.linkedNoteIds, [])
    }

    /// A bogus kind string inside an annotation also degrades to .unknown.
    func testAnnotationUnknownKindDegrades() throws {
        let json = Data("""
        { "id": "a-3", "kind": "scribble" }
        """.utf8)
        let ann = try JSONDecoder().decode(DocumentAnnotation.self, from: json)
        XCTAssertEqual(ann.kind, .unknown)
    }

    // MARK: - Computed geometry / scope helpers

    func testHasRegionRequiresFourBboxValues() {
        XCTAssertTrue(DocumentAnnotation(id: "a", bbox: [0, 0, 1, 1]).hasRegion)
        XCTAssertTrue(DocumentAnnotation(id: "a", bbox: [0, 0, 1, 1, 2]).hasRegion)
        XCTAssertFalse(DocumentAnnotation(id: "a", bbox: [0, 0, 1]).hasRegion)
        XCTAssertFalse(DocumentAnnotation(id: "a", bbox: nil).hasRegion)
    }

    func testHasSpanRequiresBothEndpoints() {
        XCTAssertTrue(DocumentAnnotation(id: "a", charStart: 1, charEnd: 5).hasSpan)
        XCTAssertFalse(DocumentAnnotation(id: "a", charStart: 1, charEnd: nil).hasSpan)
        XCTAssertFalse(DocumentAnnotation(id: "a", charStart: nil, charEnd: 5).hasSpan)
        XCTAssertFalse(DocumentAnnotation(id: "a").hasSpan)
    }

    func testScopeAndRevealFlags() {
        XCTAssertTrue(DocumentAnnotation(id: "a", folderId: "f-1").isFolderScoped)
        XCTAssertFalse(DocumentAnnotation(id: "a").isFolderScoped)
        XCTAssertTrue(DocumentAnnotation(id: "a", documentId: "d-1").canRevealSource)
        XCTAssertFalse(DocumentAnnotation(id: "a").canRevealSource)
    }
}

/// The 2026-08-23 regression, pinned: the engine moved annotations to a typed
/// `anchor` and the HAND-WRITTEN decoder kept reading only the retired
/// `bbox` — written with anchors, read back without, every symptom a valid
/// nil. These decode real wire shapes.
final class AnnotationAnchorDecodingTests: XCTestCase {
    private func decode(_ json: String) throws -> DocumentAnnotation {
        try JSONDecoder().decode(DocumentAnnotation.self, from: Data(json.utf8))
    }

    func testAnchorRectDecodesAndDrivesHasRegion() throws {
        let annotation = try decode("""
        {"id": "a1", "document_id": "d1",
         "anchor": {"document_id": "d1", "space": "normalized",
                    "rect": [0.1, 0.2, 0.3, 0.1], "rendition_id": "r9"}}
        """)
        XCTAssertEqual(annotation.anchor?.rect, [0.1, 0.2, 0.3, 0.1])
        XCTAssertEqual(annotation.anchor?.renditionId, "r9")
        XCTAssertTrue(annotation.hasRegion)
        XCTAssertEqual(annotation.regionRect, [0.1, 0.2, 0.3, 0.1])
    }

    func testPixelSpaceAnchorIsNeverDrawnAsFractions() throws {
        // The engine-side lesson of the same morning (21ba500f9): a PDF rect
        // at x=72 POINTS scaled as a fraction lands off the page. A pixel
        // anchor is honest data but not a drawable fraction.
        let annotation = try decode("""
        {"id": "a2", "document_id": "d1",
         "anchor": {"document_id": "d1", "space": "pixel", "rect": [72, 144, 200, 24]}}
        """)
        XCTAssertNil(annotation.regionRect)
        XCTAssertFalse(annotation.hasRegion)
    }

    func testLegacyBboxRowsStillCarryTheirRegion() throws {
        let annotation = try decode("""
        {"id": "a3", "document_id": "d1", "bbox": [0.2, 0.2, 0.4, 0.2]}
        """)
        XCTAssertEqual(annotation.regionRect, [0.2, 0.2, 0.4, 0.2])
        XCTAssertTrue(annotation.hasRegion)
    }

    func testSpanOnlyAnchorHasNoRegionButKeepsItsSpan() throws {
        let annotation = try decode("""
        {"id": "a4", "document_id": "d1",
         "anchor": {"document_id": "d1", "char_start": 10, "char_end": 24}}
        """)
        XCTAssertFalse(annotation.hasRegion)
        XCTAssertEqual(annotation.anchor?.charStart, 10)
    }
}
