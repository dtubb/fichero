import XCTest

/// spec: library-sharing §`sharing.ios.unpaired-phone-opens-on-connect` (#5396 item 8). The tier
/// glyphs (alpha, beta, dev) are explained by a Mac-only legend window; on a phone they are internal
/// markers, so the chrome is Mac-only. A source scan, since the iOS branch does not compile here.
final class IOSNoTierChromeTests: XCTestCase {

    func testTierChromeIsMacOnly() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent("App/Menus/ViewMenuCommands.swift"),
            encoding: .utf8)
        XCTAssertTrue(
            source.contains("var shouldShowTierChrome: Bool {\n        #if os(macOS)\n        activeBuildTier != .release\n        #else\n        false\n        #endif"),
            "shouldShowTierChrome must be false off the Mac (#5396).")
    }
}
