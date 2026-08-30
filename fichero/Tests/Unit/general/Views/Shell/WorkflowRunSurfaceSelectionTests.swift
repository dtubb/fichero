@testable import Fichero
import Foundation
import Testing

/// #4523 live regression (2026-08-04): one file selected in the SIDEBAR, run
/// Transcribe Paleography, and the engine processed the whole folder — six
/// documents. The scope resolver was right, the editor's widening dialog was
/// wired, and the run still widened, because the sidebar's file selection
/// never reached the WINDOW's selection: `preservedDocumentSelection` was
/// written only by `handleBrowserSelectionChange` (library pane), and a
/// sidebar click CLEARS `browserSelection` on the way in. So every launch
/// surface saw an empty selection.
struct WorkflowRunSurfaceSelectionTests {

    // MARK: - The rule itself, pure

    @Test("a sidebar-selected FILE becomes the window's run selection")
    func sidebarFileFeedsWindowSelection() {
        let file = Document(id: "doc-1", parentId: "folder-1", docType: .file, name: "EAP-01.tif")
        #expect(ContentView.windowSelectionAfterSidebarApply(file) == ["doc-1"])
    }

    @Test("a sidebar-selected FOLDER is a browse context, never a silent scope")
    func sidebarFolderContributesNothing() {
        let folder = Document(id: "folder-1", parentId: nil, docType: .folder, name: "Diaries")
        #expect(ContentView.windowSelectionAfterSidebarApply(folder) == nil)
    }

    @Test("a page selected in the sidebar runs alone too")
    func sidebarPageFeedsWindowSelection() {
        let page = Document(id: "page-3", parentId: "doc-1", docType: .page, name: "p3")
        #expect(ContentView.windowSelectionAfterSidebarApply(page) == ["page-3"])
    }

    // MARK: - Structural pins (view glue a unit test cannot click)

    private func source(_ relativePath: String) throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    /// The sidebar-apply path must actually WRITE the rule's answer into
    /// `preservedDocumentSelection` — the pure rule passing while nothing
    /// calls it is exactly how `widensBeyondSelection` regressed (#4523).
    @Test("the sidebar apply path writes the preserved selection")
    func applyPathWritesPreservedSelection() throws {
        let stateEvents = try source("Views/Shell/ContentView/ContentView+StateEvents.swift")
        #expect(
            stateEvents.contains("applySidebarSelectedDocument(doc)"),
            "handleSidebarItemChange stopped routing through the sidebar-apply helper"
        )
        let apply = try source("Views/Shell/ContentView/ContentView+SidebarRunSelection.swift")
        #expect(apply.contains("windowSelectionAfterSidebarApply(doc)"))
        #expect(
            apply.contains("windowState.preservedDocumentSelection = selected"),
            "the apply helper stopped writing the window's preserved run selection"
        )
    }

    /// Every run passes through ONE dispatch chokepoint that states its
    /// launch surface and scope. `surface:` is a required parameter, so the
    /// compiler pins the callers; this pins the log line itself — the thing
    /// that made the 2026-08-04 widened run undiagnosable was that no log
    /// named the surface that sent it.
    @Test("the dispatch chokepoint logs surface and scope")
    func chokepointLogsSurfaceAndScope() throws {
        let service = try source("Services/WorkflowStreamService.swift")
        #expect(service.contains("workflow-run: surface="))
        #expect(service.contains("inputs.selected_doc_ids="))
    }
}
