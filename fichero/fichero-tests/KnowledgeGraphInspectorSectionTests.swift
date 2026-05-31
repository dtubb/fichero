@testable import Fichero
import XCTest

final class KnowledgeGraphInspectorSectionTests: XCTestCase {

    func testVisibleItemsCapsWhenCollapsed() {
        let items = (1...12).map(String.init)

        let visible = KnowledgeGraphInspectorSection.visibleItems(items, showingAll: false)

        XCTAssertEqual(visible.count, 10)
        XCTAssertEqual(visible, Array(items.prefix(10)))
    }

    func testShowAllButtonTitleReflectsState() {
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.showAllButtonTitle(itemCount: 12, showingAll: false),
            "Show all (12)"
        )
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.showAllButtonTitle(itemCount: 12, showingAll: true),
            "Show less"
        )
        XCTAssertNil(
            KnowledgeGraphInspectorSection.showAllButtonTitle(itemCount: 10, showingAll: false)
        )
    }

    func testFetchButtonHelpersExposeExpectedLabelsAndIcons() {
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.fetchButtonHelp(for: .statements),
            "Get statements"
        )
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.fetchButtonHelp(for: .artifacts),
            "Get artifacts"
        )
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.fetchButtonIcon(for: .statements),
            "quote.bubble"
        )
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.fetchButtonIcon(for: .artifacts),
            "shippingbox"
        )
    }

    func testArtifactsTabIncludesPageArtifactsForParentPDFOnly() {
        let parentPDF = makeDocument(docType: .file, fileType: .pdf)
        XCTAssertTrue(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: parentPDF,
                mode: .artifactsOnly
            )
        )

        let page = makeDocument(docType: .page, fileType: nil, parentId: parentPDF.id)
        XCTAssertFalse(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: page,
                mode: .artifactsOnly
            )
        )

        let folder = makeDocument(docType: .folder, fileType: nil)
        XCTAssertFalse(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: folder,
                mode: .artifactsOnly
            )
        )

        let image = makeDocument(docType: .file, fileType: .image)
        XCTAssertFalse(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: image,
                mode: .artifactsOnly
            )
        )

        XCTAssertFalse(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: parentPDF,
                mode: .pageContentOnly
            )
        )
    }

    private func makeDocument(
        docType: DocType,
        fileType: FileType?,
        parentId: String? = nil
    ) -> Document {
        Document(
            id: UUID().uuidString,
            parentId: parentId,
            docType: docType,
            fileType: fileType,
            name: "Test",
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    }
}
