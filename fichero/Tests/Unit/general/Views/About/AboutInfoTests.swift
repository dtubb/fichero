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
        // PEP 440 re-padded for display (2026-09-02): one About box must not
        // show the same release as two different-looking versions.
        XCTAssertEqual(AboutInfo.engineVersionLine("2026.7.8b2"), "Server 2026.07.08-beta.2")
        XCTAssertEqual(AboutInfo.engineVersionLine("2026.9.3"), "Server 2026.09.03")
        XCTAssertEqual(AboutInfo.engineVersionLine("2026.9.3.2"), "Server 2026.09.03.2")
        XCTAssertEqual(AboutInfo.dateStyleVersion("1.2"), "1.2")  // non-date passes through
    }

    /// `dateStyleVersion` (the display re-padding) pinned directly: single-digit
    /// month/day gain a leading zero; a beta suffix is preserved (b1 drops the
    /// number, b2+ keeps it); and anything not date-shaped passes through untouched
    /// so a non-calendar version is never mangled.
    func testDateStyleVersionPadsSingleDigitMonthAndDay() {
        XCTAssertEqual(AboutInfo.dateStyleVersion("2026.9.3"), "2026.09.03")
        XCTAssertEqual(AboutInfo.dateStyleVersion("2026.09.03"), "2026.09.03")  // already padded, idempotent
        XCTAssertEqual(AboutInfo.dateStyleVersion("2026.12.31"), "2026.12.31")
    }

    func testDateStyleVersionPreservesBetaSuffix() {
        XCTAssertEqual(AboutInfo.dateStyleVersion("2026.9.3b1"), "2026.09.03-beta")
        XCTAssertEqual(AboutInfo.dateStyleVersion("2026.9.3b2"), "2026.09.03-beta.2")
    }

    func testDateStyleVersionPassesThroughNonDateShapes() {
        XCTAssertEqual(AboutInfo.dateStyleVersion("1.2.3"), "1.2.3")   // year not 4 digits
        XCTAssertEqual(AboutInfo.dateStyleVersion("1.0"), "1.0")       // too few parts
        XCTAssertEqual(AboutInfo.dateStyleVersion("dev"), "dev")       // not numeric
    }

    func testEngineVersionLineIsOmittedWhenMissing() {
        XCTAssertNil(AboutInfo.engineVersionLine(nil))
    }

    func testEngineVersionLineIsOmittedWhenEmpty() {
        XCTAssertNil(AboutInfo.engineVersionLine(" "))
    }

    /// #4094: a failed connection is the SAME rendered state as "not yet
    /// connected" — the health-check failure paths clear `backendVersion` to
    /// nil, so About omits the Server row entirely. No dangling "Server —"
    /// placeholder, and nothing that pretends to still be loading.
    func testEngineVersionLineIsOmittedAfterConnectionFailure() {
        let versionAfterFailedHealthCheck: String? = nil
        XCTAssertNil(AboutInfo.engineVersionLine(versionAfterFailedHealthCheck))
    }

    func testCopyrightLineUsesBundleValue() {
        XCTAssertEqual(
            AboutInfo.copyrightLine(bundleValue: "© 2026 Daniel Tubb · MIT License", fallback: "fallback"),
            "© 2026 Daniel Tubb · MIT License"
        )
    }

    func testCopyrightLineFallsBackWhenBundleValueMissing() {
        let fallback = "© 2025–2026 Daniel Tubb · MIT License"
        XCTAssertEqual(
            AboutInfo.copyrightLine(bundleValue: " ", fallback: fallback),
            fallback
        )
    }

    func testAcknowledgementsHaveUniqueNamesAndHTTPSLinks() {
        let acknowledgements = AboutAcknowledgements.entries
        XCTAssertEqual(Set(acknowledgements.map(\.name)).count, acknowledgements.count)

        for acknowledgement in acknowledgements {
            XCTAssertFalse(acknowledgement.name.isEmpty)
            XCTAssertFalse(acknowledgement.license.isEmpty)
            XCTAssertEqual(acknowledgement.url.scheme, "https")
            XCTAssertFalse(acknowledgement.url.host?.isEmpty ?? true)
        }
    }

    func testAboutLinksUseCanonicalRepositoryURLs() {
        XCTAssertEqual(AboutLinks.repository.absoluteString, "https://github.com/dtubb/fichero")
        XCTAssertEqual(
            AboutLinks.license.absoluteString,
            "https://github.com/dtubb/fichero/blob/main/LICENSE"
        )
    }
}
