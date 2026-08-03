@testable import Fichero
import XCTest

@MainActor
final class AnnotationServiceTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static func appRoot() throws -> URL {
        try AppSource.root()
    }

    private static func swiftFiles(under relativeDir: String, namePrefix: String? = nil) throws -> [URL] {
        let root = try appRoot().appendingPathComponent(relativeDir)
        let files = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)?
            .compactMap { $0 as? URL }
            .filter { $0.pathExtension == "swift" } ?? []
        guard let namePrefix else { return files }
        return files.filter { $0.lastPathComponent.hasPrefix(namePrefix) }
    }

    func testAnnotationServiceWiresDetailCropAndPromoteEndpoints() throws {
        let source = try [
            Self.appSource("Services/AnnotationService.swift"),
            Self.appSource("Services/AnnotationService+Detail.swift"),
            Self.appSource("Services/AnnotationService+Crop.swift"),
            Self.appSource("Services/AnnotationService+Promote.swift"),
            Self.appSource("Services/AnnotationService+Delete.swift")
        ].joined(separator: "\n")

        XCTAssertTrue(source.contains("client.api.getAnnotationApiAnnotationsAnnotationIdGet"))
        XCTAssertTrue(source.contains("client.api.getCropApiAnnotationsAnnotationIdCropGet"))
        XCTAssertTrue(source.contains("client.api.promoteToClaimApiAnnotationsAnnotationIdPromoteToClaimPost"))
        XCTAssertTrue(source.contains("client.api.deleteAnnotationApiAnnotationsAnnotationIdDelete"))
    }

    func testDocumentInspectorAnnotationsTabWiresRowActions() throws {
        // Row actions migrated from DocumentInspectorAnnotationsTab to AnnotationsInspectorPane
        // as part of the Store-pattern refactor. The tab now delegates via AnnotationStore.
        let source = try Self.appSource("Views/Inspector/Notes/Annotations/AnnotationsInspectorPane.swift")

        XCTAssertTrue(source.contains("annotationStore.cropAnnotation(id: annotation.id)"))
        XCTAssertTrue(source.contains("annotationStore.delete(id: annotation.id)"))
        XCTAssertTrue(source.contains("annotationStore.updateText(id: annotation.id, text: text)"))
        XCTAssertTrue(source.contains("annotationStore.promoteToClaim(id: annotation.id)"))
        XCTAssertFalse(source.contains("annotationStore.reload()"))
        XCTAssertFalse(source.contains("\"annotation.delete\""))
        XCTAssertFalse(source.contains("@Environment(LibraryManager.self) private var libraryManager"))
        XCTAssertFalse(source.contains("libraryManager.getLibrary(id: windowState.libraryId)"))
        XCTAssertFalse(source.contains("guard let documentId = annotation.documentId else { return }"))
        XCTAssertFalse(source.contains("LibraryManager.shared"))
    }

    func testInspectorListDetailPanesUseExpectedSplitLayout() throws {
        let artifactsSource = try Self.appSource("Views/Inspector/Artifacts/ArtifactsInspectorPane.swift")
        let citationsSource = try Self.appSource("Views/Inspector/Knowledge/Citations/CitationsInspectorPane.swift")
        let annotationsSource = try Self.appSource("Views/Inspector/Notes/Annotations/AnnotationsInspectorPane.swift")
        let notesSource = try Self.appSource("Views/Inspector/Notes/NotesInspectorPane.swift")

        XCTAssertTrue(artifactsSource.contains("InspectorListDetailSplit {"))
        XCTAssertTrue(citationsSource.contains("InspectorListDetailSplit {"))
        XCTAssertTrue(annotationsSource.contains("InspectorListDetailSplit {"))
        XCTAssertTrue(notesSource.contains("InspectorListDetailSplit {"))
    }

    /// #4447: the four panes above were each checked by NAME for the
    /// hand-rolled split view they replaced — a FIFTH inspector pane hand-
    /// rolling `PlatformHSplitView` would have passed untested. The
    /// invariant ("every inspector pane uses the shared
    /// `InspectorListDetailSplit`, never a raw `PlatformHSplitView`") is
    /// about the Inspector surface as a whole, so this sweeps the directory.
    /// Verified zero occurrences under `Views/Inspector/` before landing.
    func testNoInspectorPaneAnywhereHandRollsASplitView() throws {
        let files = try Self.swiftFiles(under: "Views/Inspector")
        XCTAssertFalse(files.isEmpty, "the sweep must actually read files")

        var offenders: [String] = []
        for file in files {
            let source = try String(contentsOf: file, encoding: .utf8)
            if source.contains("PlatformHSplitView {") {
                offenders.append(file.lastPathComponent)
            }
        }
        XCTAssertTrue(offenders.isEmpty, "hand-rolled PlatformHSplitView in: \(offenders.joined(separator: ", "))")
    }

    /// #4447: the two networking bans above (annotation service endpoints,
    /// Inspector row-action wiring) each only ever read ONE named file (or a
    /// closed list of siblings) — a NEW `AnnotationService+*.swift` split, or
    /// a new Inspector view, could still reach for raw `URLSession` and pass.
    /// Two scopes, because the invariant is genuinely two different ones:
    /// the annotation service family stays on the typed client, and no
    /// Inspector VIEW ever touches networking directly (that's the service
    /// layer's job). Verified zero occurrences in both scopes before landing.
    func testNoAnnotationServiceFileOrInspectorViewTouchesRawNetworking() throws {
        let serviceFiles = try Self.swiftFiles(under: "Services", namePrefix: "AnnotationService")
        let inspectorFiles = try Self.swiftFiles(under: "Views/Inspector")
        XCTAssertFalse(serviceFiles.isEmpty, "the sweep must actually read files")
        XCTAssertFalse(inspectorFiles.isEmpty, "the sweep must actually read files")

        let bannedPatterns = ["URLRequest(", "URLSession", "URL(string:"]
        var offenders: [String] = []
        for file in serviceFiles + inspectorFiles {
            let source = try String(contentsOf: file, encoding: .utf8)
            if bannedPatterns.contains(where: source.contains) {
                offenders.append(file.lastPathComponent)
            }
        }
        XCTAssertTrue(offenders.isEmpty, "raw networking in: \(offenders.joined(separator: ", "))")
    }

    func testInspectorEmptyStatesAreTopAligned() throws {
        let detailPaths = [
            "Views/Inspector/Artifacts/ArtifactDetailView.swift",
            "Views/Inspector/Knowledge/Citations/CitationDetailView.swift",
            "Views/Inspector/Notes/Annotations/AnnotationDetailView.swift",
            "Views/Inspector/Notes/NoteDetailView.swift"
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
        let source = try [
            Self.appSource("Services/AnnotationService+List.swift"),
            Self.appSource("Services/AnnotationService+Create.swift")
        ].joined(separator: "\n")

        XCTAssertTrue(source.contains("query: .init(pageId: pageId)"))
        XCTAssertTrue(source.contains("query: .init(folderId: folderId)"))
        XCTAssertTrue(source.contains("pageId: pageId"))
        XCTAssertTrue(source.contains("folderId: folderId"))
        XCTAssertTrue(source.contains("folderAnnotation(from:"))
    }

    func testDocumentInspectorAnnotationsTabSelectsScopeFromDocumentType() throws {
        let source = try Self.appSource("Views/Inspector/Notes/DocumentInspectorAnnotationsTab.swift")

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
        let documentReader = try Self.appSource("Views/Reader/Page/DocumentTextReader.swift")
        let pageContent = try [
            Self.appSource("Views/Reader/Page/PageContentPane.swift"),
            Self.appSource("Views/Reader/Page/PageContentPane+Annotations.swift")
        ].joined(separator: "\n")
        let pdfToolbar = try Self.appSource("Views/Preview/PDFViewer/PDFPageWithToolbar.swift")
        let imageViewer = try [
            Self.appSource("Views/Preview/ImageViewer/ImageViewerComponents.swift"),
            Self.appSource("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        ].joined(separator: "\n")

        XCTAssertTrue(documentReader.contains("await annotationStore.loadAnnotations(for: .document(document.id), force: true)"))
        XCTAssertTrue(pageContent.contains("await annotationStore.loadAnnotations(for: .page(id), force: true)"))
        XCTAssertTrue(pdfToolbar.contains("await annotationStore.loadAnnotations(for: .document(documentId), force: true)"))
        XCTAssertTrue(imageViewer.contains("await annotationStore.loadAnnotations(for: .document(documentId), force: true)"))
    }

    func testFolderScopedAnnotationsHideRevealDependentActions() throws {
        // Reveal/hide logic lives in AnnotationListView after the store migration.
        let source = try Self.appSource("Views/Inspector/Notes/Annotations/AnnotationListView.swift")
        XCTAssertTrue(source.contains("annotation.canRevealSource && (annotation.hasRegion || annotation.hasSpan)"))
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
