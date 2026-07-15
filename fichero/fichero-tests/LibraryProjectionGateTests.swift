@testable import Fichero
import XCTest

/// Covers the spatial-projection gate from #3867: `refreshLibraryProjection`
/// (a full documents+entities map through SpatialLibraryProjector) must run
/// only for the canvas/space modes that actually render it, and be skipped in
/// icon/list/table where the projection is never shown.
@MainActor
final class LibraryProjectionGateTests: XCTestCase {
    func testSpatialModesNeedTheProjection() {
        XCTAssertTrue(LibraryView.usesSpatialProjection(.canvas))
        XCTAssertTrue(LibraryView.usesSpatialProjection(.space))
        // Legacy alias that normalizes to canvas — still spatial.
        XCTAssertTrue(LibraryView.usesSpatialProjection(.workspace))
    }

    func testFlatModesSkipTheProjection() {
        XCTAssertFalse(LibraryView.usesSpatialProjection(.icon))
        XCTAssertFalse(LibraryView.usesSpatialProjection(.list))
        XCTAssertFalse(LibraryView.usesSpatialProjection(.table))
    }
}
