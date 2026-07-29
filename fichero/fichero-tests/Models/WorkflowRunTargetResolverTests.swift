@testable import Fichero
import XCTest

final class WorkflowRunTargetResolverTests: XCTestCase {
    private let documents = [
        Document(id: "a", parentId: "/letters", name: "A"),
        Document(id: "b", parentId: "/letters", name: "B"),
        Document(id: "nested", parentId: "/letters/nested", name: "Nested"),
        Document(id: "outside", parentId: "/outside", name: "Outside"),
        Document(id: "folder", parentId: "/letters", docType: .folder, name: "Folder")
    ]

    func testFileResolvesToItself() {
        XCTAssertEqual(
            WorkflowRunTargetResolver.resolve(
                clicked: .file("a"), selection: [], documents: documents
            ),
            ["a"]
        )
    }

    func testFolderIncludesOnlyDirectFiles() {
        XCTAssertEqual(
            WorkflowRunTargetResolver.resolve(
                clicked: .folder("/letters"), selection: [], documents: documents
            ),
            ["a", "b"]
        )
    }

    func testNestedFilesAreExcluded() {
        XCTAssertFalse(
            WorkflowRunTargetResolver.resolve(
                clicked: .folder("/letters"), selection: [], documents: documents
            ).contains("nested")
        )
    }

    func testFolderResolvesCachedDirectChildrenOutsideParentViewDocuments() {
        let parentViewDocuments = [
            Document(id: "/archive", docType: .folder, name: "Archive")
        ]
        let currentLibraryDocuments = parentViewDocuments + [
            Document(id: "letter", parentId: "/archive/letters", name: "Letter")
        ]

        XCTAssertTrue(
            WorkflowRunTargetResolver.resolve(
                clicked: .folder("/archive/letters"),
                selection: [],
                documents: parentViewDocuments
            ).isEmpty
        )
        XCTAssertEqual(
            WorkflowRunTargetResolver.resolve(
                clicked: .folder("/archive/letters"),
                selection: [],
                documents: currentLibraryDocuments
            ),
            ["letter"]
        )
    }

    func testSelectedFileAndFolderUnionIsDeduplicated() {
        XCTAssertEqual(
            WorkflowRunTargetResolver.resolve(
                clicked: .folder("/letters"),
                selection: [.file("a"), .folder("/letters")],
                documents: documents
            ),
            ["a", "b"]
        )
    }

    func testSelectedFilesFollowDocumentOrder() {
        XCTAssertEqual(
            WorkflowRunTargetResolver.resolve(
                clicked: .file("b"),
                selection: [.file("a"), .file("b")],
                documents: documents
            ),
            ["a", "b"]
        )
    }

    func testUnselectedClickIgnoresUnrelatedSelection() {
        XCTAssertEqual(
            WorkflowRunTargetResolver.resolve(
                clicked: .folder("/letters"),
                selection: [.file("outside")],
                documents: documents
            ),
            ["a", "b"]
        )
    }

    func testSelectedForeignFileIsExcludedFromCurrentLibraryTargets() {
        XCTAssertEqual(
            WorkflowRunTargetResolver.resolve(
                clicked: .file("a"),
                selection: [.file("a"), .file("foreign-library-document")],
                documents: documents
            ),
            ["a"]
        )
    }

    func testEmptyFolderResolvesToNoDocuments() {
        XCTAssertTrue(
            WorkflowRunTargetResolver.resolve(
                clicked: .folder("/empty"), selection: [], documents: documents
            ).isEmpty
        )
    }
}
