@testable import Fichero
import XCTest

@MainActor
final class AnnotationServiceTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testAnnotationServiceWiresDetailCropAndPromoteEndpoints() throws {
        let source = try Self.appSource("Services/AnnotationService.swift")

        XCTAssertTrue(source.contains("client.api.getAnnotationApiAnnotationsAnnotationIdGet"))
        XCTAssertTrue(source.contains("client.api.getCropApiAnnotationsAnnotationIdCropGet"))
        XCTAssertTrue(source.contains("client.api.promoteToClaimApiAnnotationsAnnotationIdPromoteToClaimPost"))
        XCTAssertTrue(source.contains("client.api.deleteAnnotationApiAnnotationsAnnotationIdDelete"))
        XCTAssertFalse(source.contains("URLRequest("))
        XCTAssertFalse(source.contains("URLSession"))
        XCTAssertFalse(source.contains("URL(string:"))
    }

    func testDocumentInspectorAnnotationsTabWiresRowActions() throws {
        // Row actions migrated from DocumentInspectorAnnotationsTab to AnnotationsInspectorPane
        // as part of the Store-pattern refactor. The tab now delegates via AnnotationStore.
        let source = try Self.appSource("Views/Library/Inspector/AnnotationsInspectorPane.swift")

        XCTAssertTrue(source.contains("annotationStore.cropAnnotation(id: annotation.id)"))
        XCTAssertTrue(source.contains("annotationStore.reload()"))
        XCTAssertTrue(source.contains("\"annotation.delete\""))
        XCTAssertTrue(source.contains("@Environment(LibraryManager.self) private var libraryManager"))
        XCTAssertTrue(source.contains("libraryManager.getLibrary(id: windowState.libraryId)"))
        XCTAssertTrue(source.contains("guard let documentId = annotation.documentId else { return }"))
        XCTAssertFalse(source.contains("LibraryManager.shared"))
        XCTAssertFalse(source.contains("URLRequest("))
        XCTAssertFalse(source.contains("URLSession"))
        XCTAssertFalse(source.contains("URL(string:"))
    }

    func testInspectorListDetailPanesUseExpectedSplitLayout() throws {
        let artifactsSource = try Self.appSource("Views/Library/Inspector/ArtifactsInspectorPane.swift")
        let citationsSource = try Self.appSource("Views/Library/Inspector/CitationsInspectorPane.swift")
        let annotationsSource = try Self.appSource("Views/Library/Inspector/AnnotationsInspectorPane.swift")
        let notesSource = try Self.appSource("Views/Notes/NotesInspectorPane.swift")

        XCTAssertTrue(artifactsSource.contains("PlatformVSplitView {"))
        XCTAssertTrue(citationsSource.contains("PlatformVSplitView {"))
        XCTAssertTrue(annotationsSource.contains("PlatformVSplitView {"))
        XCTAssertTrue(notesSource.contains("PlatformVSplitView {"))
        XCTAssertFalse(artifactsSource.contains("PlatformHSplitView {"))
        XCTAssertFalse(citationsSource.contains("PlatformHSplitView {"))
        XCTAssertFalse(annotationsSource.contains("PlatformHSplitView {"))
        XCTAssertFalse(notesSource.contains("PlatformHSplitView {"))
    }

    func testInspectorEmptyStatesAreTopAligned() throws {
        let detailPaths = [
            "Views/Library/Inspector/ArtifactDetailView.swift",
            "Views/Library/Inspector/CitationDetailView.swift",
            "Views/Library/Inspector/AnnotationDetailView.swift",
            "Views/Notes/NoteDetailView.swift"
        ]

        for path in detailPaths {
            let source = try Self.appSource(path)
            XCTAssertTrue(
                source.contains(".frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)"),
                path
            )
        }
    }

    func testAnnotationServiceUsesExplicitPageAndFolderScopeFields() throws {
        let source = try Self.appSource("Services/AnnotationService.swift")

        XCTAssertTrue(source.contains("query: .init(pageId: pageId)"))
        XCTAssertTrue(source.contains("query: .init(folderId: folderId)"))
        XCTAssertTrue(source.contains("pageId: pageId"))
        XCTAssertTrue(source.contains("folderId: folderId"))
        XCTAssertTrue(source.contains("folderAnnotation(from:"))
    }

    func testDocumentInspectorAnnotationsTabSelectsScopeFromDocumentType() throws {
        let source = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorAnnotationsTab.swift")

        XCTAssertTrue(source.contains("case .folder:"))
        XCTAssertTrue(source.contains("return .folder(document.id)"))
        XCTAssertTrue(source.contains("case .page:"))
        XCTAssertTrue(source.contains("return .page(document.id)"))
        // Scope loading now goes through AnnotationStore.loadAnnotations(for:force:).
        XCTAssertTrue(source.contains("await annotationStore.loadAnnotations(for: annotationScope, force: true)"))
    }

    func testAnnotationStoreFiltersChangeEventsByLoadedScope() throws {
        let source = try Self.appSource("Models/AnnotationStore.swift")

        XCTAssertTrue(source.contains("guard eventTouchesLoadedScope(event) else { return }"))
        XCTAssertTrue(source.contains("case .document(let id), .page(let id), .folder(let id):"))
        XCTAssertTrue(source.contains("return ids.contains(id)"))
    }

    func testReaderSurfacesDoNotForceReloadAfterAddNote() throws {
        let documentReader = try Self.appSource("Views/Library/Reading/DocumentTextReader.swift")
        let pageContent = try Self.appSource("Views/Library/Reading/PageContentPane.swift")
        let pdfToolbar = try Self.appSource("Views/Library/Reading/PDFPageWithToolbar.swift")
        let imageViewer = try Self.appSource("Views/Library/ImageViewer/ImageViewerComponents.swift")

        XCTAssertFalse(documentReader.contains("await annotationStore.loadAnnotations(for: .document(document.id), force: true)"))
        XCTAssertFalse(pageContent.contains("await annotationStore.loadAnnotations(for: .page(doc.id), force: true)"))
        XCTAssertFalse(pdfToolbar.contains("await annotationStore.loadAnnotations(for: .document(documentId), force: true)"))
        XCTAssertFalse(imageViewer.contains("await annotationStore.loadAnnotations(for: .document(documentId), force: true)"))
    }

    func testFolderScopedAnnotationsHideRevealDependentActions() throws {
        // Reveal/hide logic lives in AnnotationListView after the store migration.
        let source = try Self.appSource("Views/Library/Inspector/AnnotationListView.swift")
        XCTAssertTrue(source.contains("annotation.canRevealSource && (annotation.hasRegion || annotation.hasSpan)"))
        XCTAssertFalse(source.contains("URLRequest("))
        XCTAssertFalse(source.contains("URLSession"))
        XCTAssertFalse(source.contains("URL(string:"))
    }

    func testMatchesSearchByText() {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "d1",
            text: "River crossing at Quibdó",
            tags: ["fieldwork"]
        )
        XCTAssertTrue(AnnotationService.matchesSearch(annotation, query: "quibd"))
    }

    func testMatchesSearchByTag() {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "d1",
            text: "note",
            tags: ["speaker-compare"]
        )
        XCTAssertTrue(AnnotationService.matchesSearch(annotation, query: "speaker"))
    }

    func testMatchesSearchByLinkedClaimId() {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "d1",
            text: "note",
            linkedClaimIds: ["claim-abc-123"]
        )
        XCTAssertTrue(AnnotationService.matchesSearch(annotation, query: "abc-123"))
    }

    func testMatchesSearchReturnsFalseWhenNoFieldMatches() {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "d1",
            text: "Local tax records",
            tags: ["archive"]
        )
        XCTAssertFalse(AnnotationService.matchesSearch(annotation, query: "mining"))
    }

    // MARK: - Source-navigation mapping (#3432)

    func testAnnotationSourceNavigationMapsFullAnchor() throws {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "doc-9",
            pageLabel: "p. 4",
            charStart: 10,
            charEnd: 25,
            bbox: [0.1, 0.2, 0.3, 0.4]
        )

        let request = try XCTUnwrap(AnnotationSourceNavigation.request(for: annotation))
        XCTAssertEqual(request.documentId, "doc-9")
        XCTAssertEqual(request.pageLabel, "p. 4")
        XCTAssertEqual(request.charStart, 10)
        XCTAssertEqual(request.charEnd, 25)
        XCTAssertEqual(request.bbox, [0.1, 0.2, 0.3, 0.4])
    }

    func testAnnotationSourceNavigationNilWithoutDocumentAnchor() {
        // No document id → no anchor, so selection/reveal is a safe no-op rather
        // than routing an unresolvable request.
        let annotation = DocumentAnnotation(id: "a2", pageLabel: "p. 1")
        XCTAssertNil(AnnotationSourceNavigation.request(for: annotation))
    }
}
