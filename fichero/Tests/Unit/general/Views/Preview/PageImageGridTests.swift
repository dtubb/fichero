@testable import Fichero
import SwiftUI
import XCTest

/// Tests for PageImageGrid.gridColumns (#2090 Tier 2) — the pure column-config
/// helper for the shared N-up page grid. The only unit-testable seam of the
/// otherwise-declarative view; pins the count and the min-1 clamp that stops a
/// bad column count from producing an empty (crashing) LazyVGrid config.
final class PageImageGridTests: XCTestCase {

    func testColumnCountMatchesRequested() {
        XCTAssertEqual(PageImageGrid.gridColumns(count: 1).count, 1)
        XCTAssertEqual(PageImageGrid.gridColumns(count: 2).count, 2)
        XCTAssertEqual(PageImageGrid.gridColumns(count: 3).count, 3)
        XCTAssertEqual(PageImageGrid.gridColumns(count: 4).count, 4)
    }

    /// Zero or negative columns clamp to one — never an empty grid config.
    func testColumnCountClampsToAtLeastOne() {
        XCTAssertEqual(PageImageGrid.gridColumns(count: 0).count, 1)
        XCTAssertEqual(PageImageGrid.gridColumns(count: -5).count, 1)
    }

    /// The PageLayoutMode grid modes feed straight into gridColumns.
    func testMatchesPageLayoutModeColumns() {
        XCTAssertEqual(PageImageGrid.gridColumns(count: PageLayoutMode.threeUp.columns).count, 3)
        XCTAssertEqual(PageImageGrid.gridColumns(count: PageLayoutMode.fourUp.columns).count, 4)
    }
}
