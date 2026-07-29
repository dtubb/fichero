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

    // MARK: - PDF page rows (#4298)

    /// Pages carry per-page granularity (PDF-per-page work): a page row must
    /// resolve to EXACTLY that page's own document id — never the parent PDF
    /// (which the server would fan out to every page, multiplying provider
    /// spend by page count for a paleography ensemble).
    private var documentsWithPDFPages: [Document] {
        documents + [
            Document(id: "pdf", parentId: "/letters", name: "Scan.pdf"),
            Document(id: "pdf-page-2", parentId: "pdf", docType: .page, name: "Scan.pdf - Page 2"),
            Document(id: "pdf-page-3", parentId: "pdf", docType: .page, name: "Scan.pdf - Page 3")
        ]
    }

    func testPageRowResolvesToThatPageOnly() {
        XCTAssertEqual(
            WorkflowRunTargetResolver.resolve(
                clicked: .file("pdf-page-2"),
                selection: [],
                documents: documentsWithPDFPages
            ),
            ["pdf-page-2"]
        )
    }

    func testPageRowDoesNotWidenToParentOrSiblingPages() {
        let resolved = WorkflowRunTargetResolver.resolve(
            clicked: .file("pdf-page-2"),
            selection: [.file("pdf-page-2")],
            documents: documentsWithPDFPages
        )
        XCTAssertEqual(resolved, ["pdf-page-2"])
        XCTAssertFalse(resolved.contains("pdf"))
        XCTAssertFalse(resolved.contains("pdf-page-3"))
    }

    func testParentPDFRowResolvesToTheParentNotItsPages() {
        // Whole-document runs stay the parent's id — the SERVER owns the
        // per-page fan-out for a document-scoped run.
        XCTAssertEqual(
            WorkflowRunTargetResolver.resolve(
                clicked: .file("pdf"),
                selection: [],
                documents: documentsWithPDFPages
            ),
            ["pdf"]
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
