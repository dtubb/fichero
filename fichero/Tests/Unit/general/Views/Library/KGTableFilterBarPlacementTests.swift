@testable import Fichero
import XCTest

/// #4856 supersedes #4850's "filter bar belongs at the bottom" ruling: the Entities/Claims
/// filter no longer draws its OWN second bar at all — the maintainer's own evidence (build
/// 2026.09.20 (10)) showed #4850's fix landing as a bar stacked directly above the pane's
/// existing footer, spending two bar-heights and offering two ways to add something. The
/// filter and the add control now live in the ONE shared bottom bar's slots
/// (`LibraryView+BottomActionBar.swift`), content-aware by `effectiveContentKind`.
///
/// Source-scan — `body` is a `some View` with no seam to inspect child ordering at runtime
/// without a hosting harness this suite does not have (the same limitation this codebase's
/// other SwiftUI-shape tests accept; see `LibraryPaneHeadOwnWindowTests` for the same shape).
final class KGTableFilterBarPlacementTests: XCTestCase {

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

    // MARK: - Both content views take their filter text/type and their add trigger from outside

    func testEntitiesContentReadsItsFilterAndAddFromExternalBindings() throws {
        let content = try source("Views/Library/ViewModes/Table/EntitiesLibraryContent.swift")
        XCTAssertTrue(content.contains("@Binding var filterText: String"))
        XCTAssertTrue(content.contains("@Binding var filterType: String?"))
        XCTAssertTrue(content.contains("@Binding var addRequested: Bool"))
        XCTAssertTrue(content.contains("onAvailableTypesChanged"),
                      "the content must report its own loaded types UP to the shared footer's type menu")
    }

    func testClaimsContentReadsItsFilterAndAddFromExternalBindings() throws {
        let content = try source("Views/Library/ViewModes/Table/ClaimsLibraryContent.swift")
        XCTAssertTrue(content.contains("@Binding var filterText: String"))
        XCTAssertTrue(content.contains("@Binding var filterType: String?"))
        XCTAssertTrue(content.contains("@Binding var addRequested: Bool"))
        XCTAssertTrue(content.contains("onAvailableTypesChanged"),
                      "the content must report its own loaded types UP to the shared footer's type menu")
    }

    // MARK: - The shared footer is the ONE place that draws the filter and the add control

    func testSharedFooterDeclaresOneFilterSlotUsedByBothContentKinds() throws {
        let footer = try source("Views/Library/LibraryView+BottomActionBar.swift")
        XCTAssertEqual(
            footer.components(separatedBy: "private var kgContentFilterControls").count - 1, 1,
            "there must be exactly ONE filter-slot definition, shared by Entities and Claims"
        )
        XCTAssertTrue(footer.contains("kgContentFilterText"))
        XCTAssertTrue(footer.contains("kgContentFilterType"))
        XCTAssertTrue(footer.contains("kgContentAvailableTypes"))
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
