import XCTest

@testable import Fichero

/// Coverage for the About window's version-line formatting (#2557 hardening) —
/// the bundle-independent formatter behind "Version X (build)".
final class AboutInfoTests: XCTestCase {

    func testBothPresent() {
        XCTAssertEqual(
            AboutInfo.versionLine(shortVersion: "2026.07.03-beta", build: "2026070301"),
            "Version 2026.07.03-beta (2026070301)"
        )
    }

    func testMissingShortVersionFallsBackToDash() {
        XCTAssertEqual(AboutInfo.versionLine(shortVersion: nil, build: "42"), "Version — (42)")
    }

    func testMissingBuildFallsBackToDash() {
        XCTAssertEqual(AboutInfo.versionLine(shortVersion: "1.0", build: nil), "Version 1.0 (—)")
    }

    func testBothMissingFallBackToDashes() {
        XCTAssertEqual(AboutInfo.versionLine(shortVersion: nil, build: nil), "Version — (—)")
    }

    func testEmptyVersionValuesFallBackToDashes() {
        XCTAssertEqual(AboutInfo.versionLine(shortVersion: "", build: " "), "Version — (—)")
    }

    func testEngineVersionLineUsesVersion() {
        XCTAssertEqual(AboutInfo.engineVersionLine("2026.7.8b2"), "Engine 2026.7.8b2")
    }

    func testEngineVersionLineIsOmittedWhenMissing() {
        XCTAssertNil(AboutInfo.engineVersionLine(nil))
    }

    func testEngineVersionLineIsOmittedWhenEmpty() {
        XCTAssertNil(AboutInfo.engineVersionLine(" "))
    }

    func testCopyrightLineUsesBundleValue() {
        XCTAssertEqual(
            AboutInfo.copyrightLine(bundleValue: "© 2026 Daniel Tubb · MIT License", fallback: "fallback"),
            "© 2026 Daniel Tubb · MIT License"
        )
    }

    func testCopyrightLineFallsBackWhenBundleValueMissing() {
        XCTAssertEqual(
            AboutInfo.copyrightLine(bundleValue: " ", fallback: "fallback"),
            "fallback"
        )
    }
}
