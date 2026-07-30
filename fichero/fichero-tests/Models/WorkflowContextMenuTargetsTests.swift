@testable import Fichero
import XCTest

final class WorkflowContextMenuTargetsTests: XCTestCase {
    private var sidebarPresentationURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
    }

    func testSidebarContextMenuResolvesFileAndFolderTargetsBeforeShowingWorkflowMenu() throws {
        let source = try String(contentsOf: sidebarPresentationURL)

        XCTAssertTrue(source.contains("WorkflowRunTargetResolver.resolve"))
        XCTAssertFalse(source.contains("if case .document(let doc) = item.itemType"))
        // #4419 INVERTED this. The menu used to be gated on the target list
        // being non-empty, and that gate is how "nothing in Marshall can be
        // run" was produced: a cross-library row resolved to nothing and the
        // whole submenu vanished, which reads as an unsupported feature rather
        // than a failure. The resolver now always yields a target; if it ever
        // cannot, a DISABLED item names the reason.
        XCTAssertFalse(
            source.contains("!workflowTargetIDs.isEmpty"),
            "the Run Workflow submenu must not be gated on a non-empty target list (#4419)"
        )
        XCTAssertTrue(source.contains("resolution.isEmpty"))
        XCTAssertTrue(source.contains("Nothing to run on"))
        XCTAssertTrue(source.contains("resolution.ignoredSelection"))
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
        XCTAssertTrue(source.contains("selectedDocumentIdsForBatch = resolution.targetIds"))
        // Same inversion as the sidebar above (#4419).
        XCTAssertFalse(
            source.contains("!workflowTargetIDs.isEmpty"),
            "the Run Workflow submenu must not be gated on a non-empty target list (#4419)"
        )
        XCTAssertTrue(source.contains("resolution.isEmpty"))
        XCTAssertTrue(source.contains("Nothing to run on"))
        XCTAssertTrue(source.contains("resolution.ignoredSelection"))
    }

    private var sidebarWorkflowURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Sidebar/ItemRow/SidebarItemRow+Workflow.swift")
    }

    private var libraryContextMenuURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Library/LibraryView+ContextMenu.swift")
    }
}
