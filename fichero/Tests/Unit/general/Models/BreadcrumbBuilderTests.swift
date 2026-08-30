import XCTest

@testable import Fichero

final class BreadcrumbBuilderTests: XCTestCase {

    func testBreadcrumbWithNoParent() {
        let doc = Document(name: "File.pdf")
        let lookup: BreadcrumbBuilder.DocumentLookup = { _ in nil }

        let result = BreadcrumbBuilder.buildBreadcrumb(from: doc, parentLookup: lookup)

        XCTAssertEqual(result, "Library › File.pdf")
    }

    func testBreadcrumbWithSingleParent() {
        let folder = Document(id: "folder-1", name: "Folder A")
        let file = Document(id: "file-1", parentId: "folder-1", name: "File.pdf")

        let lookup: BreadcrumbBuilder.DocumentLookup = { id in
            id == "folder-1" ? folder : nil
        }

        let result = BreadcrumbBuilder.buildBreadcrumb(from: file, parentLookup: lookup)

        XCTAssertEqual(result, "Library › Folder A › File.pdf")
    }

    func testBreadcrumbWithNestedHierarchy() {
        let root = Document(id: "root", name: "Collection")
        let subFolder = Document(id: "subfolder", parentId: "root", name: "Box 3")
        let file = Document(id: "file", parentId: "subfolder", name: "Letter 12")

        let lookup: BreadcrumbBuilder.DocumentLookup = { id in
            switch id {
            case "root": return root
            case "subfolder": return subFolder
            default: return nil
            }
        }

        let result = BreadcrumbBuilder.buildBreadcrumb(from: file, parentLookup: lookup)

        XCTAssertEqual(result, "Library › Collection › Box 3 › Letter 12")
    }

    func testBreadcrumbWithPageLabel() {
        let folder = Document(id: "folder-1", name: "Folder A")
        let file = Document(id: "file-1", parentId: "folder-1", name: "Document.pdf")

        let lookup: BreadcrumbBuilder.DocumentLookup = { id in
            id == "folder-1" ? folder : nil
        }

        let result = BreadcrumbBuilder.buildBreadcrumb(from: file, parentLookup: lookup, pageLabel: "p.4")

        XCTAssertEqual(result, "Library › Folder A › Document.pdf › p.4")
    }

    func testBuildBreadcrumbForLibraryModeWithRoot() {
        let doc = Document(name: "Library")
        let lookup: BreadcrumbBuilder.DocumentLookup = { _ in nil }

        let result = BreadcrumbBuilder.buildBreadcrumbForLibraryMode(document: doc, parentLookup: lookup)

        XCTAssertEqual(result, "Library")
    }

    func testBuildBreadcrumbForLibraryModeWithFolder() {
        let folder = Document(id: "folder-1", name: "Folder A")
        let lookup: BreadcrumbBuilder.DocumentLookup = { _ in nil }

        let result = BreadcrumbBuilder.buildBreadcrumbForLibraryMode(document: folder, parentLookup: lookup)

        XCTAssertEqual(result, "Folder A")
    }

    func testBuildBreadcrumbForLibraryModeNilDocument() {
        let lookup: BreadcrumbBuilder.DocumentLookup = { _ in nil }

        let result = BreadcrumbBuilder.buildBreadcrumbForLibraryMode(document: nil, parentLookup: lookup)

        XCTAssertEqual(result, "Library")
    }

    /// This test used to assert `"Library › Folder A › page_0004 › p.4"` —
    /// which is #4416 in miniature, pinned as correct: the page contributed its
    /// STORAGE name (`page_0004`) and the label was appended on top, so the
    /// page appeared twice. The expectation is corrected, not the code
    /// loosened.
    func testBuildBreadcrumbForLibraryModeWithPageLabel() {
        let folder = Document(id: "folder-1", name: "Folder A")
        let page = Document(id: "page-1", parentId: "folder-1", docType: .page, name: "page_0004", sequence: 4)
        let lookup: BreadcrumbBuilder.DocumentLookup = { id in
            id == "folder-1" ? folder : nil
        }

        let result = BreadcrumbBuilder.buildBreadcrumbForLibraryMode(
            document: page,
            pageLabel: "p.4",
            parentLookup: lookup
        )

        XCTAssertEqual(result, "Library › Folder A › Page 4")
        XCTAssertFalse(result.contains("page_0004"), "a storage name is never user-facing")
    }

    func testBreadcrumbWithMissingParent() {
        let file = Document(id: "file-1", parentId: "missing-parent", name: "File.pdf")
        let lookup: BreadcrumbBuilder.DocumentLookup = { _ in nil }

        let result = BreadcrumbBuilder.buildBreadcrumb(from: file, parentLookup: lookup)

        // When parent is missing, it stops traversal at the file
        XCTAssertEqual(result, "Library › File.pdf")
    }

    func testBreadcrumbEmptyPageLabel() {
        let doc = Document(name: "Document.pdf")
        let lookup: BreadcrumbBuilder.DocumentLookup = { _ in nil }

        let result = BreadcrumbBuilder.buildBreadcrumb(from: doc, parentLookup: lookup, pageLabel: nil)

        XCTAssertEqual(result, "Library › Document.pdf")
    }

    // MARK: - Clickable segments (#1928)

    func testSegmentsNilDocumentIsRootOnly() {
        let segments = BreadcrumbBuilder.buildSegments(from: nil, parentLookup: { _ in nil })

        XCTAssertEqual(segments.map(\.name), ["Library"])
        XCTAssertTrue(segments[0].isRoot)
        XCTAssertNil(segments[0].documentId)
        XCTAssertTrue(segments[0].isNavigable)
    }

    func testSegmentsCarryNavigableDocumentIds() {
        let root = Document(id: "root", name: "Collection")
        let subFolder = Document(id: "subfolder", parentId: "root", name: "Box 3")
        let file = Document(id: "file", parentId: "subfolder", name: "Letter 12")
        let lookup: BreadcrumbBuilder.DocumentLookup = { id in
            switch id {
            case "root": return root
            case "subfolder": return subFolder
            default: return nil
            }
        }

        let segments = BreadcrumbBuilder.buildSegments(from: file, parentLookup: lookup)

        XCTAssertEqual(segments.map(\.name), ["Library", "Collection", "Box 3", "Letter 12"])
        XCTAssertEqual(segments.map(\.documentId), [nil, "root", "subfolder", "file"])
        XCTAssertTrue(segments.allSatisfy(\.isNavigable))
    }

    func testSegmentsPageLeafIsNonNavigable() {
        let file = Document(id: "file-1", name: "Document.pdf")

        let segments = BreadcrumbBuilder.buildSegments(
            from: file,
            parentLookup: { _ in nil },
            pageLabel: "p.4"
        )

        XCTAssertEqual(segments.map(\.name), ["Library", "Document.pdf", "p.4"])
        let leaf = segments.last!
        XCTAssertNil(leaf.documentId)
        XCTAssertFalse(leaf.isRoot)
        XCTAssertFalse(leaf.isNavigable)
    }

    func testSegmentsStopAtMissingParent() {
        let file = Document(id: "file-1", parentId: "missing", name: "File.pdf")

        let segments = BreadcrumbBuilder.buildSegments(from: file, parentLookup: { _ in nil })

        XCTAssertEqual(segments.map(\.name), ["Library", "File.pdf"])
    }
}
