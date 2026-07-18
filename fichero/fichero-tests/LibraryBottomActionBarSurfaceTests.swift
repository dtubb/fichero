@testable import Fichero
import XCTest

/// Source-surface tests for the Library bottom action bar's mini-toolbar
/// unification (#3057, parent #2670): the bar routes through the shared
/// `AdaptiveMiniToolbarRow` and its overflow menu mirrors the secondary
/// actions, while keeping the existing glass chrome + touch-target metrics.
/// Mirrors `WorkflowImportExportSurfaceTests` (deterministic, token-free).
final class LibraryBottomActionBarSurfaceTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testBottomBarRoutesThroughAdaptiveMiniToolbarRow() throws {
        let source = try Self.appSource("Views/Library/LibraryView.swift")
        // The bar is rewrapped on the shared component, not a hand-rolled HStack.
        XCTAssertTrue(source.contains("AdaptiveMiniToolbarRow {"))
        XCTAssertTrue(source.contains("overflowMenu: {"))
        XCTAssertTrue(source.contains("bottomBarOverflowMenu"))
        // Existing glass chrome + shared touch-target metrics preserved (#2474/#2550).
        XCTAssertTrue(source.contains(".glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))"))
        XCTAssertTrue(source.contains("bottomBarTouchTarget"))
    }

    func testOverflowMenuMirrorsSecondaryActions() throws {
        let source = try Self.appSource("Views/Library/LibraryView.swift")
        // The overflow menu carries the secondary verbs as Labels with the SAME
        // underlying actions as the inline buttons.
        XCTAssertTrue(source.contains("Label(\"Export BibTeX\", systemImage: \"square.and.arrow.up\")"))
        XCTAssertTrue(source.contains("Label(\"Run Workflow\", systemImage: \"bolt\")"))
        XCTAssertTrue(source.contains("exportSelectedBibtex()"))
        XCTAssertTrue(source.contains("showWorkflowPicker = true"))
    }

    func testWorkflowPickerUsesActiveLibraryWorkflows() throws {
        let pickerSource = try Self.appSource("Views/Workflow/WorkflowPickerSheet.swift")

        XCTAssertTrue(pickerSource.contains("@Environment(LibraryManager.self) private var libraryManager"))
        XCTAssertTrue(pickerSource.contains("@Environment(WindowState.self) private var windowState"))
        XCTAssertTrue(pickerSource.contains("libraryManager.getLibrary(id: windowState.libraryId)"))
    }

    // MARK: - Run-Workflow library-context coherence (#3820)

    func testWorkflowIsRunnableOnlyWhenPresentInExecutionLibrary() {
        // A single library item's Run-Workflow menu must offer only workflows
        // resolvable in the library it executes against — otherwise the engine
        // 400s on an unknown workflow_id (the #3820 root cause).
        let workflows = [
            WorkflowSidebarItem(id: "wf-a", name: "Alpha"),
            WorkflowSidebarItem(id: "wf-b", name: "Beta")
        ]
        XCTAssertTrue(LibraryView.workflowIsRunnable(workflowId: "wf-a", in: workflows))
        XCTAssertTrue(LibraryView.workflowIsRunnable(workflowId: "wf-b", in: workflows))
        // An id from a different library (or a stale menu) is refused, not sent.
        XCTAssertFalse(LibraryView.workflowIsRunnable(workflowId: "wf-from-other-library", in: workflows))
        XCTAssertFalse(LibraryView.workflowIsRunnable(workflowId: "wf-a", in: []))
    }

    func testRunBatchWorkflowExecutesThroughTheMenuSourceLibrary() throws {
        // Locks the fix: both the menu list and the execution derive from the
        // SAME reference (`activeLibraryReference` / its workflowStreamService),
        // never the environment's shared service, so they can't diverge.
        let source = try Self.appSource("Views/Library/LibraryView+FilterAndBatch.swift")
        XCTAssertTrue(source.contains("activeLibraryReference?.workflowStore.workflows"))
        XCTAssertTrue(source.contains("guard let library = activeLibraryReference"))
        XCTAssertTrue(source.contains("let stream = library.workflowStreamService"))
        XCTAssertTrue(source.contains("try await stream.execute("))
        XCTAssertTrue(source.contains("Self.workflowIsRunnable(workflowId: workflowId, in: workflows)"))
    }

    func testSidebarRunWorkflowBindsListAndExecutionToRowLibrary() throws {
        // Sweep guardrail (#3820 follow-up): the sidebar single-item Run-Workflow
        // entry point is the reference-correct pattern — it lists AND executes
        // from the SAME `library` reference, so it can never send a workflow_id
        // the execution library can't resolve. Lock that so it can't regress
        // into the environment-shared-service divergence #3820 fixed elsewhere.
        let rowSource = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow.swift")
        // List source: the row's own library workflowStore.
        XCTAssertTrue(rowSource.contains("var workflowStore: WorkflowStore? { library?.workflowStore }"))

        let runSource = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Workflow.swift")
        // Execution: the SAME library's stream service (not the environment's).
        XCTAssertTrue(runSource.contains("let stream = library.workflowStreamService"))
        XCTAssertTrue(runSource.contains("try await stream.execute("))
    }

    func testBatchWorkflowRefreshesDocumentsAsWorkflowStepsComplete() throws {
        let source = try Self.appSource("Views/Library/LibraryView+FilterAndBatch.swift")

        XCTAssertTrue(source.contains("await store.refreshDocumentsByIds([documentId])"))
        XCTAssertTrue(source.contains("await documentStore.refreshDocumentsByIds(selectedDocumentIdsForBatch)"))
    }

    func testEssentialTierHoldsPrimaryVerbs() throws {
        let source = try Self.appSource("Views/Library/LibraryView.swift")
        let start = try XCTUnwrap(source.range(of: "private var essentialBarButtons: some View"))
        let end = try XCTUnwrap(source.range(of: "private var secondaryBarButtons: some View"))
        let block = String(source[start.upperBound..<end.lowerBound])
        // New Folder / Delete / Import are the always-inline essential verbs.
        XCTAssertTrue(block.contains("New Folder"))
        XCTAssertTrue(block.contains("Delete"))
        XCTAssertTrue(block.contains("Import"))
    }

    func testLiveUpdatesPillUsesTopInsetInsteadOfOverlayingRows() throws {
        let source = try Self.appSource("Views/Library/LibraryView.swift")

        XCTAssertTrue(source.contains("private var liveUpdatesPausedInset: some View"))
        XCTAssertTrue(source.contains(".safeAreaInset(edge: .top, spacing: 0)"))
        XCTAssertTrue(source.contains("first row from peeking"))
        XCTAssertFalse(source.contains(".overlay(alignment: .top) { liveUpdatesPausedOverlay }"))
    }
}
