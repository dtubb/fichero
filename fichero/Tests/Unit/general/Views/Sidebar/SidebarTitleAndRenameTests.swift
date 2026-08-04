@testable import Fichero
import XCTest

/// The sidebar's two audit fixes (#116).
///
/// Both are instances of the pattern this codebase keeps rediscovering: a rule
/// applied to every surface but one, or to one of two identical cases. #4415's
/// curation guard reached one caller, #4416's title composer reached every
/// document surface except this one, #4454 fixed Delete on virtual rows and left
/// Rename. None of them were visible from the fixed side.
final class SidebarTitleAndRenameTests: XCTestCase {

    // MARK: - The sidebar composes names through the same composer as everyone else

    /// The defect verbatim: `doc.pageThumbnailLabel ?? doc.name` ignored a
    /// user-set metadata title, rendered an unfiltered storage filename, and
    /// showed a page as a bare "1". The row label, the VoiceOver label and the
    /// help text all derive from this one string, so all three were wrong.
    func testTheSidebarUsesTheTitleComposer() throws {
        let source = try AppSource.text("Models/SidebarItem.swift")

        XCTAssertTrue(
            Self.code(of: source).contains("DocumentTitle.displayName(for: doc, parent: parent)"),
            "the sidebar must compose display names through DocumentTitle, like every other surface"
        )
        XCTAssertFalse(
            Self.code(of: source).contains("doc.pageThumbnailLabel ?? doc.name"),
            "the hand-rolled composition is the #4416 defect"
        )
    }

    /// The parent has to be THREADED or the composer's parent-fallback rung is
    /// dead: a page whose own name is a storage filename would fall through to
    /// "Untitled" instead of borrowing its document's name.
    func testTheBuilderThreadsTheParentSoTheFallbackRungWorks() throws {
        let source = try AppSource.text("Models/SidebarItemBuilder.swift")

        XCTAssertTrue(Self.code(of: source).contains("buildItem($0, parent: doc)"))
        XCTAssertTrue(Self.code(of: source).contains("parent: parent"))
    }

    // MARK: - Rename, the unfixed half of #4454

    /// A virtual row has nothing behind it to rename. Offering it produced a
    /// confirmed action, a log line and no change — which is exactly what
    /// Delete did before #4454 removed it, in the same file, for the same rows.
    func testRenameIsNotOfferedOnVirtualRows() {
        XCTAssertFalse(
            SidebarItem.ItemType.folder(folderPath: "search").canBeRenamed,
            "a virtual folder row has no backing object; Rename could only ever no-op"
        )
    }

    /// And the two predicates must AGREE about virtual rows, which is the
    /// property that was broken: `canBeDeleted` said no and `canBeRenamed` said
    /// yes about the identical row kind.
    func testDeleteAndRenameAgreeAboutVirtualRows() {
        let virtualRow = SidebarItem.ItemType.folder(folderPath: "automation")

        XCTAssertEqual(
            virtualRow.canBeRenamed,
            virtualRow.canBeDeleted,
            "both are 'is there anything behind this row' — they cannot disagree"
        )
    }

    /// The fix must not be "disable everything", which is how a narrowing fix
    /// usually goes wrong. Asserted against the SOURCE rather than by building
    /// each case: every other ItemType carries an associated value whose
    /// initialiser is not this test's business, and a test that has to
    /// construct eight model types to check one predicate is a test that breaks
    /// whenever any of the eight changes.
    func testOnlyTheVirtualRowLostRename() throws {
        let source = try AppSource.text("Views/Sidebar/ItemRow/SidebarItemContextMenu.swift")
        let code = Self.code(of: source)

        // The kinds that keep Rename are still listed on its `true` arm.
        for kind in ["document", "savedSearch", "conversation", "workflow", "libraryHeader"] {
            XCTAssertTrue(
                code.contains("case .document, .savedSearch, .conversation, .workflow"),
                "\(kind) must keep Rename"
            )
        }
        // And `.folder` sits on the false arm beside the kinds that never had it.
        XCTAssertTrue(code.contains("case .comparison, .batch, .activityRun, .folder:"))
    }

    // MARK: - Support

    /// Source with `//` comments removed. Three checks in this repo have now
    /// fired on their own explanations; the comments above mention the very
    /// strings these assertions forbid.
    private static func code(of source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let marker = line.range(of: "//") else { return line }
                return line[line.startIndex..<marker.lowerBound]
            }
            .joined(separator: "\n")
    }
}
