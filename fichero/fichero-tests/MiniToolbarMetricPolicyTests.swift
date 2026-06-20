@testable import Fichero
import XCTest

final class MiniToolbarMetricPolicyTests: XCTestCase {
    func testMacMetricsPreserveCompactPaneToolbar() {
        XCTAssertEqual(
            MiniToolbarMetricPolicy.metrics(isMac: true, isTV: false),
            MiniToolbarMetrics(standardHeight: 44, touchTargetSide: 28)
        )
    }

    func testTouchPlatformMetricsUseReachableHitTargets() {
        XCTAssertEqual(
            MiniToolbarMetricPolicy.metrics(isMac: false, isTV: false),
            MiniToolbarMetrics(standardHeight: 52, touchTargetSide: 44)
        )
    }

    func testTVMetricsAllowLargerFocusChrome() {
        XCTAssertEqual(
            MiniToolbarMetricPolicy.metrics(isMac: false, isTV: true),
            MiniToolbarMetrics(standardHeight: 64, touchTargetSide: 44)
        )
    }
}
