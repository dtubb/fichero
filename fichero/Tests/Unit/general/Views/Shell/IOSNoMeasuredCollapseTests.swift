import XCTest

/// spec: modes-to-panes §`m2p.ios.no-measured-collapse` (iOS I1, review item 3). On iOS the
/// sidebar/inspector collapse policy is fed no measured width and the shell has no hard minimum
/// width, so Stage Manager free resize cannot start a measure-and-collapse feedback loop. A source
/// scan, because the iOS branch does not compile into the Mac test host.
final class IOSNoMeasuredCollapseTests: XCTestCase {

    func testIOSBranchesFeedNoMeasuredWidthToTheCollapsePolicy() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Shell/ContentView/ContentView+StateLayout.swift"),
            encoding: .utf8)
        XCTAssertTrue(
            source.contains("var shellCollapseWidth: Double {\n        #if os(macOS)\n        measuredWindowWidth\n        #else\n        0\n        #endif"),
            "shellCollapseWidth must be the measured width on macOS and 0 elsewhere (iOS I1).")
        XCTAssertTrue(
            source.contains("windowWidth: shellCollapseWidth,"),
            "shellCollapsePolicy must read shellCollapseWidth, never measuredWindowWidth directly.")
        XCTAssertTrue(
            source.contains("#if !os(macOS)\n        // No hard minimum on iOS"),
            "shellWindowMinWidth must be 0 on iOS (iOS I1).")
    }
}
