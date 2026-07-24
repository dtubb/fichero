@testable import Fichero
import XCTest

final class WorkflowContextMenuTargetsTests: XCTestCase {
    private var sidebarPresentationURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
    }

    func testSidebarContextMenuResolvesFileAndFolderTargetsBeforeShowingWorkflowMenu() throws {
        let source = try String(contentsOf: sidebarPresentationURL)

        XCTAssertTrue(source.contains("WorkflowRunTargetResolver.resolve"))
        XCTAssertFalse(source.contains("if case .document(let doc) = item.itemType"))
        XCTAssertTrue(source.contains("!workflowTargetIDs.isEmpty"))
    }

    func testSidebarWorkflowExecutorSendsAllResolvedTargetsInOneRequest() throws {
        let source = try String(contentsOf: sidebarWorkflowURL)

        XCTAssertTrue(source.contains("func runWorkflowOnDocuments("))
        XCTAssertTrue(source.contains("docIds: [String]"))
        XCTAssertTrue(source.contains("inputs: [\"selected_doc_ids\": request.docIds]"))
    }

    func testLibraryContextMenuResolvesClickedFolderBeforeBatchWorkflow() throws {
        let source = try String(contentsOf: libraryContextMenuURL)

        XCTAssertTrue(source.contains("WorkflowRunTargetResolver.resolve"))
        XCTAssertTrue(source.contains("selectedDocumentIdsForBatch = workflowTargetIDs"))
        XCTAssertTrue(source.contains("!workflowTargetIDs.isEmpty"))
    }

    private var sidebarWorkflowURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Sidebar/ItemRow/SidebarItemRow+Workflow.swift")
    }

    private var libraryContextMenuURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Library/LibraryView+ContextMenu.swift")
    }
}
