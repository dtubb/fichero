@testable import Fichero
import SwiftUI
import XCTest

final class MiniToolbarMetricPolicyTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

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
    @MainActor func testWorkflowMiniToolbarButtonIsInstantiable() {
        let enabled = WorkflowMiniToolbarButton(isEnabled: true, action: {}, showRunOnSelection: true)
        let disabled = WorkflowMiniToolbarButton(isEnabled: false, action: {}, showRunOnSelection: false)
        _ = enabled
        _ = disabled
    }

    // #2460: Mini-toolbar visibility preference key and default are stable.
    // Changing the key silently breaks persisted user preference on existing installs.
    func testMiniToolbarVisibilityPreferenceIsDefaultOn() {
        XCTAssertEqual(MiniToolbarPreferences.toolbarVisibilityKey, "fichero.ui.showMiniToolbar")
        XCTAssertTrue(MiniToolbarPreferences.toolbarVisibilityDefault)
    }

    func testVisibilityConsumersUseSharedPreferenceConstant() throws {
        let toolbarSource = try Self.appSource("Views/Toolbars/MiniToolbar.swift")
        XCTAssertTrue(toolbarSource.contains("MiniToolbarPreferences.toolbarVisibilityKey"))

        let menuSource = try Self.appSource("Views/Menu/ViewMenuCommands.swift")
        XCTAssertTrue(menuSource.contains("MiniToolbarPreferences.toolbarVisibilityKey"))
    }

    // #2475: Sidebar bottom bar must meet the 52/44 touch tier on iPhone/iPad.
    func testSidebarBottomBarTouchTierMeetsTouchMinimum() {
        let metrics = MiniToolbarMetricPolicy.metrics(isMac: false, isTV: false)
        XCTAssertGreaterThanOrEqual(
            metrics.touchTargetSide,
            44,
            "Sidebar bottom bar requires ≥44pt tap targets on touch platforms"
        )
        XCTAssertGreaterThanOrEqual(
            metrics.standardHeight,
            44,
            "Sidebar bottom bar height must be ≥44pt on touch platforms"
        )
    }

    func testSidebarBottomBarMacMetricsDoNotInflateTouchTier() {
        let macMetrics = MiniToolbarMetricPolicy.metrics(isMac: true, isTV: false)
        let touchMetrics = MiniToolbarMetricPolicy.metrics(isMac: false, isTV: false)
        XCTAssertLessThan(
            macMetrics.touchTargetSide,
            touchMetrics.touchTargetSide,
            "Mac cursor targets are intentionally smaller than touch targets"
        )
    }

    func testMiniToolbarCollapsesSplitButtonsToMenu() throws {
        let source = try Self.appSource("Views/Toolbars/MiniToolbar.swift")

        XCTAssertTrue(source.contains("ViewThatFits(in: .horizontal)"))
        XCTAssertTrue(source.contains("splitButtonsMenu(for: actions)"))
        XCTAssertTrue(source.contains("Menu {"))
    }

    func testReadingPaneZoomControlsCollapseToMenu() throws {
        let source = try Self.appSource("Views/ContentView+ViewBuilders.swift")

        XCTAssertTrue(source.contains("ViewThatFits(in: .horizontal)"))
        XCTAssertTrue(source.contains("zoomMenu"))
        XCTAssertTrue(source.contains("Reset Zoom"))
    }
}
