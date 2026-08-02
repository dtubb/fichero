@testable import Fichero
import XCTest

/// #4099 — the sidebar filter could hide the row that is currently selected.
///
/// The detail pane kept showing the document while its sidebar row vanished:
/// the UI asserting two contradictory things at once, with no way back to the
/// item except clearing the filter.
///
/// Tested through the static, exempt-injected predicate rather than a live
/// `SidebarView`, because the bug IS the predicate. A test that needed a
/// mounted view to reach it would not have been written — which is roughly why
/// it was not.
final class SidebarFilterSelectionTests: XCTestCase {

    private func node(
        _ id: String, _ name: String, children: [SidebarItem]? = nil
    ) -> SidebarItem {
        SidebarItem(
            id: id,
            name: name,
            icon: "folder",
            category: .folder,
            itemType: .folder(folderPath: "/\(name)"),
            children: children,
            libraryId: nil,
            folderPath: "/\(name)",
            sortOrder: 0,
            isFolder: children != nil
        )
    }

    private func leaf(_ id: String, _ name: String) -> SidebarItem {
        node(id, name)
    }

    private func folder(_ id: String, _ name: String, _ children: [SidebarItem]) -> SidebarItem {
        node(id, name, children: children)
    }

    /// A folder of diary years, one of which contains the selected page.
    private var tree: SidebarItem {
        folder("root", "Marshall Diaries", [
            folder("y1893", "1893", [
                leaf("p1", "January"),
                leaf("p2", "February")
            ]),
            folder("y1894", "1894", [
                leaf("p3", "March")
            ])
        ])
    }

    private func filter(_ query: String, exempt: Set<String> = []) -> SidebarItem? {
        SidebarView.filteredSidebarItem(tree, query: query, exempt: exempt)
    }

    private func ids(_ item: SidebarItem?) -> Set<String> {
        guard let item else { return [] }
        return Set([item.id]).union((item.children ?? []).flatMap { ids($0) })
    }

    // MARK: - The bug

    func testSelectedRowSurvivesAFilterItDoesNotMatch() throws {
        // "March" does not contain "Jan" — before the fix it disappeared even
        // while selected, and the detail pane went on showing it.
        let result = try XCTUnwrap(filter("Jan", exempt: ["p3"]))

        XCTAssertTrue(ids(result).contains("p3"), "the selected row must never be filtered away")
    }

    func testTheSelectedRowStaysREACHABLENotJustPresent() throws {
        // A surviving row inside a pruned parent would be unreachable. The
        // existing keep-the-parent rule has to carry the whole chain.
        let result = try XCTUnwrap(filter("Jan", exempt: ["p3"]))
        let surviving = ids(result)

        XCTAssertTrue(surviving.contains("y1894"), "the selected row's parent must survive with it")
        XCTAssertTrue(surviving.contains("root"))
    }

    func testEveryRowOfAMultiSelectionIsExempt() throws {
        // A batch selection that half-vanishes is the same defect, only wider.
        let result = try XCTUnwrap(filter("zzz", exempt: ["p1", "p3"]))
        let surviving = ids(result)

        XCTAssertTrue(surviving.contains("p1"))
        XCTAssertTrue(surviving.contains("p3"))
    }

    // MARK: - It must not become a filter that filters nothing

    func testNonMatchingUnselectedRowsAreStillRemoved() throws {
        // The failure that would look like success: exempting too much turns
        // the filter into a no-op, and every test above would still pass.
        let result = try XCTUnwrap(filter("Jan", exempt: ["p3"]))
        let surviving = ids(result)

        XCTAssertFalse(surviving.contains("p2"), "February matches nothing and is not selected")
        XCTAssertFalse(surviving.contains("y1893") && !surviving.contains("p1"))
    }

    func testWithNoSelectionTheFilterBehavesExactlyAsBefore() throws {
        let result = try XCTUnwrap(filter("Jan"))
        let surviving = ids(result)

        XCTAssertEqual(surviving, ["root", "y1893", "p1"], "unchanged for the no-selection case")
    }

    func testAFilterMatchingNothingWithNoSelectionStillReturnsNil() {
        XCTAssertNil(filter("zzz"), "an empty result must stay empty, not become the whole tree")
    }

    // MARK: - Pre-existing behaviour that must not shift

    func testAMatchingFolderStillKeepsItsWholeSubtree() throws {
        // Searching a folder's own name shows what is inside it. Filtering a
        // matched folder's children too would be a second change riding along
        // on this fix.
        let result = try XCTUnwrap(filter("1893"))

        XCTAssertEqual(ids(result), ["root", "y1893", "p1", "p2"])
    }

    // MARK: - Exemptions must not accumulate

    func testExemptionsAreDerivedPerCallNotStored() throws {
        // NetNewsWire needs `resetFilterExceptions()` because its exceptions
        // are stored. Here they are a parameter, so a stale exemption cannot
        // exist: filtering the same tree with no exempt set prunes the row that
        // was exempt a moment ago.
        XCTAssertTrue(ids(try XCTUnwrap(filter("Jan", exempt: ["p3"]))).contains("p3"))
        XCTAssertFalse(ids(filter("Jan")).contains("p3"))
    }
}
