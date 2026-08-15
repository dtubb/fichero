@testable import Fichero
import XCTest

/// #4186 — the library tree must carry workflows ONLY as engine-mirrored
/// document nodes (presets under the locked "Default Workflows" container),
/// never as the client-built virtual hierarchy.
///
/// The virtual hierarchy (grouping workflow.folder_path into `.workflow`-
/// category folders) DUPLICATED the mirror tree: unlocked "Books"/
/// "Catalogue"/… folders at the tree root whose click switched the window
/// into the workflow surface (the user's 2026-07-27 report). The engine heal
/// (b2b9f6899) re-homes the mirror rows, but the virtual folders derive
/// from workflow.folder_path and would sit at root forever — the client
/// append is the only place this can be fixed.
///
/// Source-inspection on purpose (precedent: LibrarySelectionStrengthTests):
/// `buildLibraryGroup` needs a live LibraryReference, so the assertion pins
/// the one construction site instead.
final class SidebarWorkflowVirtualTreeTests: XCTestCase {

    private func builderSource() throws -> String {
        let url = try AppSource.root().appendingPathComponent("Models/SidebarItemBuilder.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testLibraryGroupDoesNotBuildTheVirtualWorkflowHierarchy() throws {
        let source = try builderSource()
        XCTAssertFalse(
            source.contains("let workflowItems = buildWorkflowHierarchy"),
            "buildLibraryGroup must not re-grow the virtual workflow tree — "
                + "mirror doc nodes are the ONE sidebar representation (#4186)."
        )
        XCTAssertTrue(
            source.contains("deliberately NOT appended here (#4186)"),
            "The removal must stay documented at the construction site."
        )
    }

    func testVirtualHierarchyMachineryStaysDeleted() throws {
        // Supersedes the "stays available as a reversal point" pin: the views
        // audit (2026-08-10) deleted buildWorkflowHierarchy outright — a
        // dormant re-entry point for the #4186 duplicate client-side workflow
        // hierarchy is exactly how the duplicate would grow back. Workflows
        // reach the tree as engine-mirrored document nodes, and nothing else.
        let url = try AppSource.root()
            .appendingPathComponent("Models/SidebarItemBuilder+Sections.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(
            source.contains("static func buildWorkflowHierarchy"),
            "the dormant virtual-hierarchy builder came back (#4186)"
        )
        XCTAssertTrue(
            source.contains("buildWorkflowHierarchy deleted"),
            "the deletion must stay documented at the site"
        )
    }
}

/// #4186 spinner port — the sidebar run-spinner/progress used to key off the
/// virtual `.workflow` rows; with those gone, mirror DOC rows must carry the
/// run-state. The engine mirrors each workflow into a SAME-ID document node,
/// so the row's run-state id is the doc id for mirrors, the workflow id for
/// (surface-side) workflow items, and nil for everything else.
final class SidebarRowRunStateIdTests: XCTestCase {

    func testWorkflowItemUsesWorkflowId() {
        let item = SidebarItem.fromWorkflow(
            WorkflowSidebarItem(id: "wf-1", name: "Transcribe"),
            libraryId: UUID()
        )
        XCTAssertEqual(SidebarItemRow.runStateWorkflowId(for: item), "wf-1")
    }

    func testWorkflowMirrorDocRowUsesItsDocumentId() {
        let mirror = Document(
            id: "wf-1", docType: .file, name: "Transcribe", prototypeKey: "workflow"
        )
        let item = SidebarItem.fromDocument(mirror, libraryId: UUID())
        XCTAssertEqual(SidebarItemRow.runStateWorkflowId(for: item), "wf-1")
    }

    func testPlainDocumentAndFolderRowsHaveNoRunState() {
        let doc = Document(id: "d1", docType: .file, name: "Doc")
        XCTAssertNil(SidebarItemRow.runStateWorkflowId(
            for: SidebarItem.fromDocument(doc, libraryId: UUID())
        ))
        let folder = Document(id: "f1", docType: .folder, name: "Folder")
        XCTAssertNil(SidebarItemRow.runStateWorkflowId(
            for: SidebarItem.fromDocument(folder, libraryId: UUID())
        ))
    }
}
