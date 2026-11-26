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
        // `panes.chrome.one-filter-pattern`: the Entities and Claims list is filtered by one inline field in the
        // shared mini toolbar; the old `kgContentFilterControls` slot and its popover are gone.
        let bar = try source("Views/Library/LibraryView+MiniToolbar.swift")
        XCTAssertEqual(
            bar.components(separatedBy: "accessibilityID: \"kgContentFilterField\"").count - 1, 1,
            "there must be exactly ONE filter field definition, shared by Entities and Claims"
        )
        XCTAssertTrue(bar.contains("effectiveContentKind == .claims ? \"Filter claims\" : \"Filter entities\""))
        let footer = try source("Views/Library/LibraryView+BottomActionBar.swift")
        XCTAssertFalse(footer.contains("kgContentFilterControls"))
    }

    func testSharedFooterHasExactlyOneAddControlPerRender() throws {
        // The essential row builds one add control per render: a Menu (New Folder, Import Files…) when the pane shows
        // documents, else a single "+" Button for the entity or claim in view. The two sit in the two branches of one
        // `if effectiveContentKind == .documents`, so never two "+"s at once (the #4856 regression).
        let footer = try source("Views/Library/LibraryView+BottomActionBar.swift")
        let essentialBody = try XCTUnwrap(
            footer.components(separatedBy: "private var essentialBarButtons: some View {").last
        )
        let scope = try XCTUnwrap(essentialBody.components(separatedBy: "\n    }").first)
        XCTAssertEqual(scope.components(separatedBy: "if effectiveContentKind == .documents {").count - 1, 1)
        XCTAssertEqual(scope.components(separatedBy: "} else {").count - 1, 1)
        XCTAssertEqual(
            scope.components(separatedBy: "performAdd()").count - 1, 2,
            "essentialBarButtons calls performAdd() from the documents Menu's New Folder and from the one other-kind Button"
        )
        XCTAssertEqual(scope.components(separatedBy: "Button { performAdd() }").count - 1, 1)
    }
}
