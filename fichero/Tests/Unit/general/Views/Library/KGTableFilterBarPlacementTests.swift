@testable import Fichero
import XCTest

/// #4850: the Entities/Claims table filter bar belongs at the BOTTOM,
/// matching the Library pane's own filter (`MiniToolbarPlacement.
/// preferredForReader`), and both tables must stay identical to each other.
/// Source-scan — `body` is a `some View` with no seam to inspect child
/// ordering at runtime without a hosting harness this suite does not have
/// (the same limitation this codebase's other SwiftUI-shape tests accept).
final class KGTableFilterBarPlacementTests: XCTestCase {

    private func bodyText(_ relativePath: String) throws -> String {
        let source = try AppSource.code(relativePath)
        let start = try XCTUnwrap(
            source.range(of: "var body: some View {"),
            "\(relativePath) no longer declares `body` where expected"
        )
        let end = try XCTUnwrap(
            source.range(of: "\n    }", range: start.upperBound..<source.endIndex),
            "could not find the end of \(relativePath)'s body"
        )
        return String(source[start.upperBound..<end.lowerBound])
    }

    func testEntitiesTableFilterBarIsAfterTheTableNotBeforeIt() throws {
        let body = try bodyText("Views/Library/ViewModes/Table/EntitiesLibraryContent.swift")
        let tableRange = try XCTUnwrap(body.range(of: "EntitiesTableView("))
        let filterBarRange = try XCTUnwrap(body.range(of: "filterBar"))
        XCTAssertTrue(
            filterBarRange.lowerBound > tableRange.lowerBound,
            "the filter bar must come AFTER the table (bottom), not before it (top)"
        )
    }

    func testClaimsTableFilterBarIsAfterTheTableNotBeforeIt() throws {
        let body = try bodyText("Views/Library/ViewModes/Table/ClaimsLibraryContent.swift")
        let tableRange = try XCTUnwrap(body.range(of: "ClaimsTableView("))
        let filterBarRange = try XCTUnwrap(body.range(of: "filterBar"))
        XCTAssertTrue(
            filterBarRange.lowerBound > tableRange.lowerBound,
            "the filter bar must come AFTER the table (bottom), not before it (top)"
        )
    }

    /// Both tables reuse the shared `PaneFilterBar` component (#4362) at the
    /// bottom placement, rather than a hand-placed strip — keeps them
    /// identical and matches the Library pane's own filter chrome.
    func testBothTablesReuseThePaneFilterBarComponentAtBottomPlacement() throws {
        let entities = try AppSource.code("Views/Library/ViewModes/Table/EntitiesLibraryContent.swift")
        let claims = try AppSource.code("Views/Library/ViewModes/Table/ClaimsLibraryContent.swift")
        XCTAssertEqual(
            entities.components(separatedBy: "PaneFilterBar(placement: .bottom)").count - 1, 1
        )
        XCTAssertEqual(
            claims.components(separatedBy: "PaneFilterBar(placement: .bottom)").count - 1, 1
        )
    }
}
