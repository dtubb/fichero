@testable import Fichero
import XCTest

/// Source-surface tests for the Library bottom action bar's mini-toolbar
/// unification (#3057, parent #2670): the bar routes through the shared
/// `AdaptiveMiniToolbarRow` and its overflow menu mirrors the secondary
/// actions, while keeping the existing glass chrome + touch-target metrics.
/// Mirrors `WorkflowImportExportSurfaceTests` (deterministic, token-free).
final class LibraryBottomActionBarSurfaceTests: XCTestCase {
    /// Every Swift file under a directory, concatenated.
    ///
    /// Naming ONE file makes a guard fail on a file SPLIT while the app is
    /// correct — the #4353 split moved the bottom bar out of LibraryView.swift
    /// into LibraryView+BottomActionBar.swift and all nine of these failed
    /// against working code. The invariant is "the app does this", not "this
    /// file does this".
    private static func appSources(inDirectory relativePath: String) throws -> String {
        let dir = try appRoot().appendingPathComponent(relativePath)
        let files = try FileManager.default.subpathsOfDirectory(atPath: dir.path)
            .filter { $0.hasSuffix(".swift") }
        return try files
            .map { try String(contentsOf: dir.appendingPathComponent($0), encoding: .utf8) }
            .joined(separator: "\n")
    }

    private static func appRoot() throws -> URL {
        try AppSource.root()
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testBottomBarRoutesThroughAdaptiveMiniToolbarRow() throws {
        let source = try Self.appSources(inDirectory: "Views/Library")
        // The bar is rewrapped on the shared component, not a hand-rolled HStack.
        XCTAssertTrue(source.contains("AdaptiveMiniToolbarRow {"))
        XCTAssertTrue(source.contains("overflowMenu: {"))
        // The overflow menu is the bar's own `overflowMenu:` closure, carrying the sort menu and the row attributes.
        XCTAssertTrue(source.contains("librarySortMenu(iconOnly: false)"))
        // Flat on macOS (`panes.chrome.bars-flush-on-mac`): the shared pane-bar surface, with the shared touch-target metrics.
        XCTAssertTrue(source.contains(".paneBarSurface()"))
        XCTAssertTrue(source.contains("bottomBarTouchTarget"))
    }

    func testOverflowMenuMirrorsSecondaryActions() throws {
        let source = try Self.appSources(inDirectory: "Views/Library")
        // `panes.chrome.one-filter-pattern`: the bar holds Metadata · Sort · Filter; Export is File › Export and Run
        // Workflow left the bar, so the overflow menu mirrors what the inline cluster holds.
        XCTAssertTrue(source.contains("LibraryRowAttributesMenu(raw: $rowAttributesRaw, contentLines: $rowContentLinesRaw)"))
        XCTAssertTrue(source.contains("DatasetFilterClusterMenu(store: datasetStore, documentStore: documentStore)"))
        XCTAssertTrue(source.contains("CanvasControlStripMenu()"))
        XCTAssertFalse(source.contains("Label(\"Export BibTeX\""))
        XCTAssertFalse(source.contains("Label(\"Run Workflow\""))
    }

    func testWorkflowPickerUsesActiveLibraryWorkflows() throws {
        let pickerSource = try Self.appSource("Views/Workflow/Library/WorkflowPickerSheet.swift")

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
            WorkflowSidebarItem(id: "wf-b", name: "Beta"),
            WorkflowSidebarItem(
                id: "wf-child",
                name: "Internal Child",
                isDirectlyRunnable: false
            )
        ]
        XCTAssertTrue(LibraryView.workflowIsRunnable(workflowId: "wf-a", in: workflows))
        XCTAssertTrue(LibraryView.workflowIsRunnable(workflowId: "wf-b", in: workflows))
        // An id from a different library (or a stale menu) is refused, not sent.
        XCTAssertFalse(LibraryView.workflowIsRunnable(workflowId: "wf-from-other-library", in: workflows))
        XCTAssertFalse(LibraryView.workflowIsRunnable(workflowId: "wf-a", in: []))
        XCTAssertFalse(LibraryView.workflowIsRunnable(workflowId: "wf-child", in: workflows))
    }

    func testRunBatchWorkflowExecutesThroughTheMenuSourceLibrary() throws {
        // Locks the fix: both the menu list and the execution derive from the
        // SAME reference (`activeLibraryReference` / its workflowStreamService),
        // never the environment's shared service, so they can't diverge.
        // #4024: the menu-list wiring now lives in LibraryView+ContextMenu.swift,
        // and the execution wiring in LibraryView+BatchWorkflow.swift — read both.
        let source = try Self.appSource("Views/Library/LibraryView+ContextMenu.swift")
            + Self.appSource("Views/Library/LibraryView+BatchWorkflow.swift")
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
        // #4024: batch-workflow document refresh logic moved to LibraryView+BatchWorkflow.swift.
        let source = try Self.appSource("Views/Library/LibraryView+BatchWorkflow.swift")

        XCTAssertTrue(source.contains("await store.refreshDocumentsByIds([documentId])"))
        XCTAssertTrue(source.contains("await documentStore.refreshDocumentsByIds(selectedDocumentIdsForBatch)"))
    }

    func testEssentialTierHoldsPrimaryVerbs() throws {
        let source = try Self.appSources(inDirectory: "Views/Library")
        let start = try XCTUnwrap(source.range(of: "private var essentialBarButtons: some View"))
        let end = try XCTUnwrap(source.range(of: "private var secondaryBarButtons: some View"))
        let block = String(source[start.upperBound..<end.lowerBound])
        // New Folder / Delete / Import are the always-inline essential verbs.
        // The add control became content-aware (#4856): its label is `addButtonLabel`, which is
        // "New Folder" for documents.
        XCTAssertTrue(block.contains("New Folder") || block.contains(".accessibilityLabel(addButtonLabel)"))
        XCTAssertTrue(source.contains("case .documents: return \"New Folder\""))
        XCTAssertTrue(block.contains("Delete"))
        XCTAssertTrue(block.contains("Import"))
    }

    func testLiveUpdatesPillUsesTopInsetInsteadOfOverlayingRows() throws {
        let source = try Self.appSources(inDirectory: "Views/Library")

        // Promoted private -> internal in the 2026-08-13 LibraryView file split.
        XCTAssertTrue(source.contains("var liveUpdatesPausedInset: some View"))
        XCTAssertTrue(source.contains(".safeAreaInset(edge: .top, spacing: 0)"))
        XCTAssertTrue(source.contains("first row from peeking"))
        XCTAssertFalse(source.contains(".overlay(alignment: .top) { liveUpdatesPausedOverlay }"))
    }
}
