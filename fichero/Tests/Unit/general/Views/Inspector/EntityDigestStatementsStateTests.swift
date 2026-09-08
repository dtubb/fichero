@testable import Fichero
import XCTest

/// spec: kg-entity-inspector — `kg.entity.empty.no-claims` (D).
///
/// The entity's statements list shows the spinner while loading, an
/// entity-named "no statements" line once loaded with none, and the list
/// otherwise — never a blank pane or a stale list. The rule is pure so it is
/// pinned here without a rendered view.
final class EntityDigestStatementsStateTests: XCTestCase {

    func testLoadingWhenEmptyAndStillLoading() {
        XCTAssertEqual(
            EntityDigestContent.statementsState(isLoading: true, isEmpty: true),
            .loading,
            "an empty list mid-load shows the spinner, not the empty line"
        )
    }

    func testEmptyWhenLoadedWithNoClaims() {
        XCTAssertEqual(
            EntityDigestContent.statementsState(isLoading: false, isEmpty: true),
            .empty,
            "loaded with zero claims shows the entity-named 'no statements' line"
        )
    }

    func testListWheneverThereAreClaims() {
        XCTAssertEqual(
            EntityDigestContent.statementsState(isLoading: false, isEmpty: false),
            .list
        )
        XCTAssertEqual(
            EntityDigestContent.statementsState(isLoading: true, isEmpty: false),
            .list,
            "existing rows stay visible on a refresh — no flash to spinner"
        )
    }
}
