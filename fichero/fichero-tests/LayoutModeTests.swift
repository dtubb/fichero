@testable import Fichero
import SwiftUI
import XCTest

/// Tests for the `LayoutMode` enum that drives the main-content area's
/// content-vs-preview split. Tiny enum but central — toolbar picker,
/// View menu, and @SceneStorage all key off these raw values.
final class LayoutModeTests: XCTestCase {

    func testAllCasesCovered() {
        XCTAssertEqual(LayoutMode.allCases.count, 3)
        XCTAssertTrue(LayoutMode.allCases.contains(.none))
        XCTAssertTrue(LayoutMode.allCases.contains(.standard))
        XCTAssertTrue(LayoutMode.allCases.contains(.widescreen))
    }

    // Raw values are what @SceneStorage persists. If any of these
    // change accidentally, every user's saved window state breaks.
    func testRawValuesAreStable() {
        XCTAssertEqual(LayoutMode.none.rawValue, "None")
        XCTAssertEqual(LayoutMode.standard.rawValue, "Standard")
        XCTAssertEqual(LayoutMode.widescreen.rawValue, "Widescreen")
    }

    func testIdReturnsRawValue() {
        for mode in LayoutMode.allCases {
            XCTAssertEqual(mode.id, mode.rawValue)
        }
    }

    // SF Symbols — wrong name = blank icon = silent UI bug.
    func testIconNames() {
        XCTAssertEqual(LayoutMode.none.icon, "square")
        XCTAssertEqual(LayoutMode.standard.icon, "rectangle.split.1x2")
        XCTAssertEqual(LayoutMode.widescreen.icon, "rectangle.split.2x1")
    }

    func testDescriptions() {
        XCTAssertFalse(LayoutMode.none.description.isEmpty)
        XCTAssertFalse(LayoutMode.standard.description.isEmpty)
        XCTAssertFalse(LayoutMode.widescreen.description.isEmpty)
    }

    func testKeyboardShortcuts() {
        XCTAssertEqual(LayoutMode.none.keyboardShortcut, "0")
        XCTAssertEqual(LayoutMode.standard.keyboardShortcut, "1")
        XCTAssertEqual(LayoutMode.widescreen.keyboardShortcut, "2")
    }

    func testWidescreenPanePlanKeepsCanvasAndReadingWhenLibraryIsHidden() {
        let plan = WidescreenPanePlan.make(
            showDocumentGrid: false,
            showDocumentCanvas: true,
            showReadingPane: true
        )

        XCTAssertFalse(plan.showsLibraryPane)
        XCTAssertTrue(plan.showsCanvasPane)
        XCTAssertTrue(plan.showsReadingPane)
        XCTAssertFalse(plan.showsLibraryDivider)
        XCTAssertTrue(plan.showsCanvasReadingDivider)
    }

    func testWidescreenPanePlanShowsLibraryDividerOnlyWhenLibraryHasANeighbor() {
        let listOnly = WidescreenPanePlan.make(
            showDocumentGrid: true,
            showDocumentCanvas: false,
            showReadingPane: false
        )
        XCTAssertFalse(listOnly.showsLibraryDivider)

        let listWithCanvas = WidescreenPanePlan.make(
            showDocumentGrid: true,
            showDocumentCanvas: true,
            showReadingPane: false
        )
        XCTAssertTrue(listWithCanvas.showsLibraryDivider)
        XCTAssertFalse(listWithCanvas.showsCanvasReadingDivider)
    }

    func testCompactShellRootsAtDetailAndHidesSidebarColumn() {
        XCTAssertEqual(ContentView.defaultPreferredCompactColumn, .detail)

        XCTAssertFalse(
            ContentView.shouldRenderSidebarColumn(
                horizontalSizeClass: .compact,
                showSidebar: true,
                columnVisibility: .all
            )
        )

        let policy = ContentView.shellCollapsePolicy(
            windowWidth: 900,
            horizontalSizeClass: .compact,
            sidebarVisible: true,
            inspectorVisible: true,
            detailMinWidth: 600
        )

        XCTAssertTrue(policy.collapseSidebar)
        XCTAssertFalse(policy.collapseInspector)
    }

    func testInspectorPlacementAdaptsToCompactWidth() {
        XCTAssertEqual(InspectorPlacement.adaptiveDefault(horizontalSizeClass: .compact), .sheet)
        XCTAssertEqual(InspectorPlacement.adaptiveDefault(horizontalSizeClass: .regular), .docked)
    }

    func testReadingWorkspacePaneToggleShowsPaneByEnteringWidescreen() {
        let fromNone = ReadingWorkspacePaneTogglePolicy.toggledPane(
            layoutMode: .none,
            paneFlag: false
        )
        let fromStandard = ReadingWorkspacePaneTogglePolicy.toggledPane(
            layoutMode: .standard,
            paneFlag: true
        )

        XCTAssertEqual(fromNone.layoutMode, .widescreen)
        XCTAssertTrue(fromNone.paneVisible)
        XCTAssertEqual(fromStandard.layoutMode, .widescreen)
        XCTAssertTrue(fromStandard.paneVisible)
    }

    func testReadingWorkspacePaneToggleOnlyHidesInWidescreen() {
        let hidden = ReadingWorkspacePaneTogglePolicy.toggledPane(
            layoutMode: .widescreen,
            paneFlag: true
        )
        let shown = ReadingWorkspacePaneTogglePolicy.toggledPane(
            layoutMode: .widescreen,
            paneFlag: false
        )

        XCTAssertEqual(hidden.layoutMode, .widescreen)
        XCTAssertFalse(hidden.paneVisible)
        XCTAssertEqual(shown.layoutMode, .widescreen)
        XCTAssertTrue(shown.paneVisible)
    }

    func testSelectionPromotesToDetailWhenPreviewPaneIsVisible() {
        XCTAssertTrue(
            BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(
                layoutMode: .widescreen,
                selectedDocumentId: "page-1",
                currentDetailDocumentId: "folder-1"
            )
        )

        XCTAssertTrue(
            BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(
                layoutMode: .standard,
                selectedDocumentId: "image-1",
                currentDetailDocumentId: nil
            )
        )
    }

    func testSelectionPromotesEvenWhenPreviewPaneIsHidden() {
        XCTAssertTrue(
            BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(
                layoutMode: .none,
                selectedDocumentId: "page-1",
                currentDetailDocumentId: "folder-1"
            )
        )
    }

    func testSelectionDoesNotPromoteWhenAlreadyCurrent() {
        XCTAssertFalse(
            BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(
                layoutMode: .widescreen,
                selectedDocumentId: "page-1",
                currentDetailDocumentId: "page-1"
            )
        )

        XCTAssertFalse(
            BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(
                layoutMode: .widescreen,
                selectedDocumentId: nil,
                currentDetailDocumentId: "folder-1"
            )
        )
    }

    func testCanvasDocumentUsesSelectedPreviewableChildOverFolderInspector() {
        let folder = Document(id: "folder-1", docType: .folder, name: "Diary")
        let page = Document(
            id: "page-1",
            parentId: "folder-1",
            docType: .page,
            fileType: .image,
            name: "Page 1"
        )

        let resolved = CanvasDocumentPolicy.documentForCanvas(
            selectedDocumentIds: ["page-1"],
            documents: [page],
            detailDocument: folder,
            inspectorDocument: folder
        )

        XCTAssertEqual(resolved?.id, "page-1")
    }

    func testCanvasDocumentShowsPlainFolderOrGroupAsContainerPlaceholder() {
        let folder = Document(id: "folder-1", docType: .folder, name: "Diary")
        let group = Document(id: "group-1", docType: .group, name: "Chapter")

        let folderResult = CanvasDocumentPolicy.documentForCanvas(
            selectedDocumentIds: [],
            documents: [],
            detailDocument: folder,
            inspectorDocument: folder
        )
        let groupResult = CanvasDocumentPolicy.documentForCanvas(
            selectedDocumentIds: [],
            documents: [],
            detailDocument: group,
            inspectorDocument: group
        )

        XCTAssertEqual(folderResult?.id, "folder-1")
        XCTAssertEqual(groupResult?.id, "group-1")
    }

    func testCanvasDocumentCanPreviewImageBackedFolder() {
        let imageFolder = Document(
            id: "image-folder",
            docType: .folder,
            fileType: .image,
            name: "Imported image folder"
        )

        let resolved = CanvasDocumentPolicy.documentForCanvas(
            selectedDocumentIds: [],
            documents: [],
            detailDocument: imageFolder,
            inspectorDocument: imageFolder
        )

        XCTAssertEqual(resolved?.id, "image-folder")
    }

    func testImageBackedPageDoesNotUsePDFCanvas() {
        let imagePage = Document(
            id: "image-page",
            docType: .page,
            fileType: .image,
            name: "Imported image page",
            path: "files/nc/page.jpg",
            sequence: 2
        )

        XCTAssertFalse(CanvasDocumentPolicy.shouldUsePDFCanvas(for: imagePage))
    }

    func testPDFBackedPageUsesPDFCanvas() {
        let pdfPage = Document(
            id: "pdf-page",
            docType: .page,
            fileType: nil,
            name: "PDF page",
            sequence: 2
        )
        let pdfFile = Document(
            id: "pdf-file",
            docType: .file,
            fileType: .pdf,
            name: "Source.pdf",
            path: "/tmp/source.pdf"
        )

        XCTAssertTrue(CanvasDocumentPolicy.shouldUsePDFCanvas(for: pdfPage))
        XCTAssertTrue(CanvasDocumentPolicy.shouldUsePDFCanvas(for: pdfFile))
    }

    func testSpatialDocumentSelectionParsesDocumentNodeIds() {
        XCTAssertEqual(
            SpatialDocumentSelection.documentId(forNodeId: "doc-page-1"),
            "page-1"
        )
        XCTAssertEqual(
            SpatialDocumentSelection.documentId(forNodeId: "doc:page-2"),
            "page-2"
        )
    }

    func testSpatialDocumentSelectionIgnoresUnknownNodeIds() {
        XCTAssertNil(SpatialDocumentSelection.documentId(forNodeId: nil))
        XCTAssertNil(SpatialDocumentSelection.documentId(forNodeId: "entity-1"))
        XCTAssertNil(SpatialDocumentSelection.documentId(forNodeId: ""))
    }
}
