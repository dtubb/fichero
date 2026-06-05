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

        let route = EditorView.previewRoute(for: doc, parentPDFPath: nil, isEditing: false)

        XCTAssertEqual(route, .storageDisplay(documentId: "page-1"))
        XCTAssertFalse(route.usesImageEditingPreviewForViewing)
    }

    func testNoPathImageRoutesToStorageDisplayForViewing() {
        let doc = Document(
            id: "image-1",
            docType: .file,
            fileType: .image,
            name: "Imported Image",
            path: nil
        )

        let route = EditorView.previewRoute(for: doc, parentPDFPath: nil, isEditing: false)

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

        let route = EditorView.previewRoute(for: doc, parentPDFPath: nil, isEditing: false)

        XCTAssertEqual(route, .storageDisplay(documentId: "image-1"))
        XCTAssertFalse(route.usesImageEditingPreviewForViewing)
    }

    func testImageEditingRouteIsOptIn() {
        let doc = Document(
            id: "image-1",
            docType: .file,
            fileType: .image,
            name: "Imported Image",
            path: nil
        )

        let viewingRoute = EditorView.previewRoute(for: doc, parentPDFPath: nil, isEditing: false)
        let editingRoute = EditorView.previewRoute(for: doc, parentPDFPath: nil, isEditing: true)

        XCTAssertEqual(viewingRoute, .storageDisplay(documentId: "image-1"))
        XCTAssertEqual(editingRoute, .imageEditor(documentId: "image-1"))
        XCTAssertTrue(editingRoute.usesImageEditingPreviewForViewing)
    }
}
