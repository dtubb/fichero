@testable import Fichero
import XCTest

final class WorkflowContextMenuTargetsTests: XCTestCase {
    private func sidebarPresentationURL() throws -> URL {
        try AppSource.root().appendingPathComponent("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
    }

    private func sidebarWorkflowMenuURL() throws -> URL {
        try AppSource.root().appendingPathComponent("Views/Sidebar/ItemRow/SidebarItemRow+WorkflowMenu.swift")
    }

    func testSidebarContextMenuResolvesFileAndFolderTargetsBeforeShowingWorkflowMenu() throws {
        // Menu body stayed in +Presentation.swift; the resolver members moved
        // to +WorkflowMenu.swift at the 400-line split (2026-08-15). Read both
        // so the anchors keep guarding the SAME behaviour across the move.
        let source = try String(contentsOf: sidebarPresentationURL())
        let resolverSource = try String(contentsOf: sidebarWorkflowMenuURL())

        XCTAssertTrue(resolverSource.contains("WorkflowRunTargetResolver.resolve"))
        XCTAssertFalse(resolverSource.contains("if case .document(let doc) = item.itemType"))
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

    /// 2026-08-15: a one-row right-click ran on 63 documents because a live
    /// gallery selection widened the run with nothing in the menu saying so.
    /// Both run surfaces must state a wider-than-clicked scope BEFORE the
    /// click, and log the domain counts at fire time.
    func testBothRunSurfacesStateMultiDocumentScopeInTheMenu() throws {
        for url in [try sidebarPresentationURL(), try libraryContextMenuURL()] {
            let source = try String(contentsOf: url)
            XCTAssertTrue(
                source.contains("Runs on \\(resolution.targetIds.count) documents"),
                "\(url.lastPathComponent) must state a >1-document scope in the menu"
            )
        }
        for url in [try sidebarWorkflowMenuURL(), try libraryContextMenuURL()] {
            let source = try String(contentsOf: url)
            XCTAssertTrue(
                source.contains("contextMenu run: clicked="),
                "\(url.lastPathComponent) must log scope provenance at fire time"
            )
        }
    }

    func testSidebarWorkflowExecutorSendsAllResolvedTargetsInOneRequest() throws {
        let source = try String(contentsOf: sidebarWorkflowURL())

        XCTAssertTrue(source.contains("func runWorkflowOnDocuments("))
        XCTAssertTrue(source.contains("docIds: [String]"))
        XCTAssertTrue(source.contains("inputs: [\"selected_doc_ids\": request.docIds]"))
    }

    func testLibraryContextMenuResolvesClickedFolderBeforeBatchWorkflow() throws {
        let source = try String(contentsOf: libraryContextMenuURL())

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

    private func sidebarWorkflowURL() throws -> URL {
        try AppSource.root().appendingPathComponent("Views/Sidebar/ItemRow/SidebarItemRow+Workflow.swift")
    }

    private func libraryContextMenuURL() throws -> URL {
        try AppSource.root().appendingPathComponent("Views/Library/LibraryView+ContextMenu.swift")
    }
}
