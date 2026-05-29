@testable import Fichero
import XCTest

final class KnowledgeGraphInspectorSectionTests: XCTestCase {

    func testVisibleItemsCapsWhenCollapsed() {
        let items = (1...12).map(String.init)

        let visible = KnowledgeGraphInspectorSection.visibleItems(items, showingAll: false)

        XCTAssertEqual(visible.count, 10)
        XCTAssertEqual(visible, Array(items.prefix(10)))
    }

    func testShowAllButtonTitleReflectsState() {
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.showAllButtonTitle(itemCount: 12, showingAll: false),
            "Show all (12)"
        )
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.showAllButtonTitle(itemCount: 12, showingAll: true),
            "Show less"
        )
        XCTAssertNil(
            KnowledgeGraphInspectorSection.showAllButtonTitle(itemCount: 10, showingAll: false)
        )
    }

    func testFetchButtonHelpersExposeExpectedLabelsAndIcons() {
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.fetchButtonHelp(for: .statements),
            "Get statements"
        )
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.fetchButtonHelp(for: .artifacts),
            "Get artifacts"
        )
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.fetchButtonIcon(for: .statements),
            "quote.bubble"
        )
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.fetchButtonIcon(for: .artifacts),
            "shippingbox"
        )
    }
}
