@testable import Fichero
import XCTest

@MainActor
final class EditorViewDisplayRoutingTests: XCTestCase {
    func testPageDocumentWithoutParentPDFRoutesToStorageDisplayForViewing() {
        let doc = Document(
            id: "page-1",
            parentId: "manifest-1",
            docType: .page,
            fileType: .image,
            name: "Page 1",
            path: "files/marshall/page-1.jpg",
            sequence: 1
        )

        let route = EditorView.previewRoute(for: doc, isEditing: false)

        XCTAssertEqual(route, .storageDisplay(documentId: "page-1"))
        XCTAssertFalse(route.usesImageEditingPreviewForViewing)
    }

    func testImageBackedPageWithSequenceStillRoutesToStorageDisplay() {
        let doc = Document(
            id: "image-page-1",
            parentId: "image-folder-1",
            docType: .page,
            fileType: .image,
            name: "Image Page 1",
            path: "files/marshall/page-1.jpg",
            sequence: 7
        )

        let route = EditorView.previewRoute(for: doc, isEditing: false)

        XCTAssertEqual(route, .storageDisplay(documentId: "image-page-1"))
    }

    func testPDFBackedPageRoutesToStorageDisplay() {
        let doc = Document(
            id: "pdf-page-1",
            parentId: "pdf-1",
            docType: .page,
            fileType: nil,
            name: "PDF Page 7",
            path: nil,
            sequence: 7
        )

        let route = EditorView.previewRoute(for: doc, isEditing: false)

        XCTAssertEqual(route, .storageDisplay(documentId: "pdf-page-1"))
    }

    func testPlainFolderRoutesToContainerPlaceholder() {
        let doc = Document(
            id: "folder-1",
            docType: .folder,
            fileType: nil,
            name: "Folder"
        )

        let route = EditorView.previewRoute(for: doc, isEditing: false)

        XCTAssertEqual(route, .container)
    }

    func testMediaBackedFolderCanPreviewItsRepresentativeImage() {
        let doc = Document(
            id: "split-source-1",
            docType: .folder,
            fileType: .image,
            name: "Split Source",
            path: "files/source.jpg"
        )

        let route = EditorView.previewRoute(for: doc, isEditing: false)

        XCTAssertEqual(route, .storageDisplay(documentId: "split-source-1"))
    }

    func testNoPathImageRoutesToStorageDisplayForViewing() {
        let doc = Document(
            id: "image-1",
            docType: .file,
            fileType: .image,
            name: "Imported Image",
            path: nil
        )

        let route = EditorView.previewRoute(for: doc, isEditing: false)

        XCTAssertEqual(route, .storageDisplay(documentId: "image-1"))
        XCTAssertFalse(route.usesImageEditingPreviewForViewing)
    }

    func testPackageRelativeImagePathRoutesToStorageDisplayForViewing() {
        let doc = Document(
            id: "image-1",
            docType: .file,
            fileType: .image,
            name: "Imported Image",
            path: "files/marshall/page-1.jpg"
        )

        let route = EditorView.previewRoute(for: doc, isEditing: false)

        XCTAssertEqual(route, .storageDisplay(documentId: "image-1"))
        XCTAssertFalse(route.usesImageEditingPreviewForViewing)
    }

    func testDocxWithExtractedTextRoutesToAnnotatableText() {
        let doc = Document(
            id: "docx-1",
            docType: .file,
            fileType: .word,
            name: "Report.docx",
            path: "files/report.docx",
            pageContent: "Body text to annotate."
        )

        let route = EditorView.previewRoute(for: doc, isEditing: false)

        XCTAssertEqual(route, .text(content: "Body text to annotate."))
    }

    func testDocxWithoutTextFallsBackToQuickLook() {
        let doc = Document(
            id: "docx-2",
            docType: .file,
            fileType: .word,
            name: "Empty.docx",
            path: "files/empty.docx",
            pageContent: nil
        )

        XCTAssertEqual(EditorView.previewRoute(for: doc, isEditing: false), .quickLook)
    }

    func testPDFFileIsNotDivertedToTextEvenWithContent() {
        // A PDF file routes to its storage display, not the text reader, even if
        // page_content happens to be populated.
        let doc = Document(
            id: "pdf-file-1",
            docType: .file,
            fileType: .pdf,
            name: "Doc.pdf",
            path: "files/doc.pdf",
            pageContent: "extracted"
        )

        XCTAssertEqual(EditorView.previewRoute(for: doc, isEditing: false), .storageDisplay(documentId: "pdf-file-1"))
    }

    func testImageEditingRouteIsOptIn() {
        let doc = Document(
            id: "image-1",
            docType: .file,
            fileType: .image,
            name: "Imported Image",
            path: nil
        )

        let viewingRoute = EditorView.previewRoute(for: doc, isEditing: false)
        let editingRoute = EditorView.previewRoute(for: doc, isEditing: true)

        XCTAssertEqual(viewingRoute, .storageDisplay(documentId: "image-1"))
        #if os(macOS)
        XCTAssertEqual(editingRoute, .imageEditor(documentId: "image-1"))
        XCTAssertTrue(editingRoute.usesImageEditingPreviewForViewing)
        #else
        XCTAssertEqual(editingRoute, .storageDisplay(documentId: "image-1"))
        XCTAssertFalse(editingRoute.usesImageEditingPreviewForViewing)
        #endif
    }
}
