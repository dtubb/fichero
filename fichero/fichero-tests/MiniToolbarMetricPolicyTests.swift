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

    // Glass treatment is visual-only; the static metric accessors on MiniToolbar
    // must continue to delegate to MiniToolbarMetricPolicy unchanged. (#2041)
    func testMiniToolbarStaticHeightMatchesMacPolicy() {
        let policy = MiniToolbarMetricPolicy.metrics(isMac: true, isTV: false)
        XCTAssertEqual(MiniToolbar<EmptyView, EmptyView>.standardHeight, policy.standardHeight)
        XCTAssertEqual(MiniToolbar<EmptyView, EmptyView>.touchTargetSide, policy.touchTargetSide)
    }

    // #2415: WorkflowMiniToolbarButton must be constructable in both enabled and
    // disabled states. Behavioural gating by FeatureManager is exercised in
    // FeatureManagerTests.testWorkflowRunOnSelectionDefault.
    func testWorkflowMiniToolbarButtonIsInstantiable() {
        let enabled = WorkflowMiniToolbarButton(isEnabled: true, action: {})
        let disabled = WorkflowMiniToolbarButton(isEnabled: false, action: {})
        _ = enabled
        _ = disabled
    }
}
