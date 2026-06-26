@testable import Fichero
import XCTest

/// Tests for `Document` helpers + enums + `AnyCodable` metadata wrapper.
/// Heavy on the business logic that drives navigation + ingest-mode
/// detection (the `metadata["ingest_mode"]` + bookmark-fallback path
/// is non-trivial and is exactly the kind of code where a regression
/// would silently break ingest UI).
final class DocumentModelTests: XCTestCase {

    // MARK: - DocType / FileType / Status enums

    func testDocTypeIcons() {
        XCTAssertEqual(DocType.folder.icon, "folder")
        XCTAssertEqual(DocType.group.icon, "rectangle.stack")
        XCTAssertEqual(DocType.file.icon, "doc")
        XCTAssertEqual(DocType.page.icon, "doc.text")
        XCTAssertEqual(DocType.chunk.icon, "text.quote")
    }

    func testFileTypeRawValuesMatchPython() {
        // These rawValues must match the Python enum exactly — they
        // travel over JSON. Drift = decode failure.
        XCTAssertEqual(FileType.image.rawValue, "image")
        XCTAssertEqual(FileType.pdf.rawValue, "pdf")
        XCTAssertEqual(FileType.text.rawValue, "text")
        XCTAssertEqual(FileType.audio.rawValue, "audio")
        XCTAssertEqual(FileType.video.rawValue, "video")
    }

    func testStatusColors() {
        XCTAssertEqual(Status.pending.color, "gray")
        XCTAssertEqual(Status.processing.color, "blue")
        XCTAssertEqual(Status.completed.color, "green")
        XCTAssertEqual(Status.failed.color, "red")
    }

    func testAllStatusesHaveColor() {
        for status in Status.allCases {
            XCTAssertFalse(status.color.isEmpty)
        }
    }

    // MARK: - sortableFileType

    func testSortableFileTypeForKnownType() {
        let doc = makeDocument(fileType: .pdf)
        XCTAssertEqual(doc.sortableFileType, "pdf")
    }

    func testSortableFileTypeForNilFileType() {
        let doc = makeDocument(fileType: nil)
        // Empty string sorts before any rawValue — consistent placement.
        XCTAssertEqual(doc.sortableFileType, "")
    }

    // MARK: - ingestMode

    func testIngestModeReadsExplicitMetadata() {
        let doc = makeDocument(metadata: ["ingest_mode": AnyCodable("move")])
        XCTAssertEqual(doc.ingestMode, .move)
    }

    func testIngestModeFallsBackToLinkWhenBookmarkPresent() {
        // Legacy docs (no explicit ingest_mode) had bookmark when LINK'd.
        let doc = makeDocument(
            metadata: ["bookmark": AnyCodable("bk-data")]
        )
        XCTAssertEqual(doc.ingestMode, .link)
    }

    func testIngestModeFallsBackToCopyWhenNoMetadata() {
        let doc = makeDocument(metadata: [:])
        XCTAssertEqual(doc.ingestMode, .copy)
    }

    func testIngestModeUnknownRawFallsBackToHeuristic() {
        // If the metadata key holds garbage, fall through to the
        // bookmark heuristic rather than crash or return a default.
        let doc = makeDocument(metadata: ["ingest_mode": AnyCodable("bogus")])
        // Now falls back to copy (no bookmark present).
        XCTAssertEqual(doc.ingestMode, .copy)
    }

    func testIsLinkedAndIsMoved() {
        let linked = makeDocument(metadata: ["ingest_mode": AnyCodable("link")])
        let moved = makeDocument(metadata: ["ingest_mode": AnyCodable("move")])
        let copied = makeDocument(metadata: ["ingest_mode": AnyCodable("copy")])
        XCTAssertTrue(linked.isLinked)
        XCTAssertFalse(linked.isMoved)
        XCTAssertFalse(moved.isLinked)
        XCTAssertTrue(moved.isMoved)
        XCTAssertFalse(copied.isLinked)
        XCTAssertFalse(copied.isMoved)
    }

    // MARK: - isNavigableContainer

    func testIsNavigableContainerForFolder() {
        let folder = makeDocument(docType: .folder)
        XCTAssertTrue(folder.isNavigableContainer)
    }

    func testIsNavigableContainerForPDF() {
        let pdf = makeDocument(docType: .file, fileType: .pdf)
        XCTAssertTrue(pdf.isNavigableContainer)
    }

    func testIsNavigableContainerForImageIsFalse() {
        let img = makeDocument(docType: .file, fileType: .image)
        XCTAssertFalse(img.isNavigableContainer)
    }

    func testIsNavigableContainerForPageIsFalse() {
        // A PDF page is itself not navigable (we preview, not navigate).
        let page = makeDocument(docType: .page)
        XCTAssertFalse(page.isNavigableContainer)
    }

    // MARK: - AnyCodable

    func testAnyCodableEncodesAndDecodesBool() throws {
        let original = AnyCodable(true)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AnyCodable.self, from: data)
        XCTAssertEqual(decoded.value as? Bool, true)
    }

    func testAnyCodableEncodesAndDecodesInt() throws {
        let original = AnyCodable(42)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AnyCodable.self, from: data)
        XCTAssertEqual(decoded.value as? Int, 42)
    }

    func testAnyCodableEncodesAndDecodesString() throws {
        let original = AnyCodable("hello")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AnyCodable.self, from: data)
        XCTAssertEqual(decoded.value as? String, "hello")
    }

    func testAnyCodableHandlesNestedArray() throws {
        let json = "[1, \"two\", true]".data(using: .utf8)!
        let decoded = try JSONDecoder().decode(AnyCodable.self, from: json)
        let arr = decoded.value as? [Any]
        XCTAssertNotNil(arr)
        XCTAssertEqual(arr?[0] as? Int, 1)
        XCTAssertEqual(arr?[1] as? String, "two")
        XCTAssertEqual(arr?[2] as? Bool, true)
    }

    func testAnyCodableHandlesNestedDict() throws {
        let json = "{\"name\": \"Asprilla\", \"age\": 42}".data(using: .utf8)!
        let decoded = try JSONDecoder().decode(AnyCodable.self, from: json)
        let dict = decoded.value as? [String: Any]
        XCTAssertEqual(dict?["name"] as? String, "Asprilla")
        XCTAssertEqual(dict?["age"] as? Int, 42)
    }

    func testAnyCodableHandlesNull() throws {
        let json = "null".data(using: .utf8)!
        let decoded = try JSONDecoder().decode(AnyCodable.self, from: json)
        XCTAssertTrue(decoded.value is NSNull)
    }

    // MARK: - Sibling Image Navigation (#2420)

    func testNavigableSiblingsIncludesOnlyImagesAndPagesWhenCurrentIsImage() {
        let image1 = makeDocument(id: "img-1", fileType: .image)
        let image2 = makeDocument(id: "img-2", fileType: .image)
        let pdf = makeDocument(id: "pdf-1", fileType: .pdf)
        let text = makeDocument(id: "txt-1", fileType: .text)
        let siblings = navigableFolderSiblings(for: image1, in: [image1, pdf, image2, text])
        XCTAssertEqual(siblings.map(\.id), ["img-1", "img-2"])
    }

    func testNavigableSiblingsIncludesOnlyImagesAndPagesWhenCurrentIsPage() {
        let page1 = makeDocument(id: "page-1", docType: .page)
        let page2 = makeDocument(id: "page-2", docType: .page)
        let pdf = makeDocument(id: "pdf-1", fileType: .pdf)
        let siblings = navigableFolderSiblings(for: page1, in: [pdf, page1, page2])
        XCTAssertEqual(siblings.map(\.id), ["page-1", "page-2"])
    }

    func testNavigableSiblingsIncludesAllDocumentsWhenCurrentIsNotImageOrPage() {
        let pdf = makeDocument(id: "pdf-1", fileType: .pdf)
        let image = makeDocument(id: "img-1", fileType: .image)
        let text = makeDocument(id: "txt-1", fileType: .text)
        let siblings = navigableFolderSiblings(for: pdf, in: [pdf, image, text])
        XCTAssertEqual(siblings.map(\.id), ["pdf-1", "img-1", "txt-1"])
    }

    func testNavigableSiblingsPreservesDisplayOrder() {
        let image1 = makeDocument(id: "img-1", fileType: .image)
        let image2 = makeDocument(id: "img-2", fileType: .image)
        let image3 = makeDocument(id: "img-3", fileType: .image)
        let siblings = navigableFolderSiblings(for: image2, in: [image1, image2, image3])
        XCTAssertEqual(siblings.map(\.id), ["img-1", "img-2", "img-3"])
    }

    // MARK: - Helper

    private func makeDocument(
        id: String = "test-id",
        docType: DocType = .file,
        fileType: FileType? = nil,
        metadata: [String: AnyCodable] = [:]
    ) -> Document {
        Document(
            id: id,
            parentId: nil,
            docType: docType,
            fileType: fileType,
            name: "test.txt",
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: metadata,
            pageContent: nil,
            sortOrder: 0,
            createdAt: Date(),
            updatedAt: Date()
        )
    }
}
