@testable import Fichero
import XCTest

/// #4856: split out of `KGTableFilterBarPlacementTests` (#5052). What remains are the ABSENCE and
/// COUNT guardrails: a content view draws no filter bar of its own, and the shared footer holds
/// exactly one filter slot and exactly one add control. Neither is observable without a mounted
/// footer, so they scan the source.
final class KGFilterBarGuardrailTests: XCTestCase {

    private func source(_ relativePath: String) throws -> String {
        try AppSource.code(relativePath)
    }

    // MARK: - Neither content view draws a second bar of its own any more

    func testEntitiesContentDeclaresNoFilterBarOfItsOwn() throws {
        let content = try source("Views/Library/ViewModes/Table/EntitiesLibraryContent.swift")
        XCTAssertFalse(content.contains("filterBar"),
                        "#4856: the entities table must not draw its own bottom bar any more")
        XCTAssertFalse(content.contains("PaneFilterBar("),
                        "#4856: the shared PaneFilterBar strip is no longer used by this content view")
    }

    func testClaimsContentDeclaresNoFilterBarOfItsOwn() throws {
        let content = try source("Views/Library/ViewModes/Table/ClaimsLibraryContent.swift")
        XCTAssertFalse(content.contains("filterBar"),
                        "#4856: the claims table must not draw its own bottom bar any more")
        XCTAssertFalse(content.contains("PaneFilterBar("),
                        "#4856: the shared PaneFilterBar strip is no longer used by this content view")
    }

    // MARK: - The shared footer is the ONE place that draws the filter and the add control

    func testSharedFooterDeclaresOneFilterSlotUsedByBothContentKinds() throws {
        let footer = try source("Views/Library/LibraryView+BottomActionBar.swift")
        XCTAssertEqual(
            footer.components(separatedBy: "private var kgContentFilterControls").count - 1, 1,
            "there must be exactly ONE filter-slot definition, shared by Entities and Claims"
        )
    }

    func testSharedFooterHasExactlyOneAddControlPerRender() throws {
        // The essential row must build the add Button exactly once — never two "+"s for the
        // one content kind that is actually mounted (the literal #4856 regression: a folder
        // "+" and a content-specific "New Entity"/"New Claim" button present at once).
        let footer = try source("Views/Library/LibraryView+BottomActionBar.swift")
        let essentialBody = try XCTUnwrap(
            footer.components(separatedBy: "private var essentialBarButtons: some View {").last
        )
        let scope = try XCTUnwrap(essentialBody.components(separatedBy: "\n    }").first)
        XCTAssertEqual(
            scope.components(separatedBy: "performAdd()").count - 1, 1,
            "essentialBarButtons must call performAdd() from exactly one Button"
        )
    }
}
