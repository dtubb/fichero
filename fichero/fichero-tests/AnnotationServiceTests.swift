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
        XCTAssertTrue(source.contains("guard let documentId = annotation.documentId else { return }"))
        XCTAssertFalse(source.contains("URLRequest("))
        XCTAssertFalse(source.contains("URLSession"))
        XCTAssertFalse(source.contains("URL(string:"))
    }

    func testInspectorListDetailPanesUseExpectedSplitLayout() throws {
        let artifactsSource = try Self.appSource("Views/Library/Inspector/ArtifactsInspectorPane.swift")
        let citationsSource = try Self.appSource("Views/Library/Inspector/CitationsInspectorPane.swift")
        let annotationsSource = try Self.appSource("Views/Library/Inspector/AnnotationsInspectorPane.swift")
        let notesSource = try Self.appSource("Views/Notes/NotesInspectorPane.swift")

        XCTAssertTrue(artifactsSource.contains("PlatformHSplitView {"))
        XCTAssertTrue(citationsSource.contains("PlatformHSplitView {"))
        XCTAssertTrue(annotationsSource.contains("PlatformVSplitView {"))
        XCTAssertTrue(notesSource.contains("PlatformVSplitView {"))
        XCTAssertFalse(artifactsSource.contains("PlatformVSplitView {"))
        XCTAssertFalse(citationsSource.contains("PlatformVSplitView {"))
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
}
