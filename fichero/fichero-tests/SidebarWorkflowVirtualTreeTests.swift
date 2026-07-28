@testable import Fichero
import XCTest

/// #4186 — the library tree must carry workflows ONLY as engine-mirrored
/// document nodes (presets under the locked "Default Workflows" container),
/// never as the client-built virtual hierarchy.
///
/// The virtual hierarchy (grouping workflow.folder_path into `.workflow`-
/// category folders) DUPLICATED the mirror tree: unlocked "Books"/
/// "Catalogue"/… folders at the tree root whose click switched the window
/// into the workflow surface (Daniel's 2026-07-27 report). The engine heal
/// (b2b9f6899) re-homes the mirror rows, but the virtual folders derive
/// from workflow.folder_path and would sit at root forever — the client
/// append is the only place this can be fixed.
///
/// Source-inspection on purpose (precedent: LibrarySelectionStrengthTests):
/// `buildLibraryGroup` needs a live LibraryReference, so the assertion pins
/// the one construction site instead.
final class SidebarWorkflowVirtualTreeTests: XCTestCase {

    private func builderSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero/Models/SidebarItemBuilder.swift")
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

    func testSharedHierarchyMachineryStaysAvailable() throws {
        // buildWorkflowHierarchy itself stays: it is tested shared machinery
        // and the one-line reversal point if #4186 needs revisiting.
        let source = try builderSource()
        XCTAssertTrue(source.contains("static func buildWorkflowHierarchy"))
    }
}
