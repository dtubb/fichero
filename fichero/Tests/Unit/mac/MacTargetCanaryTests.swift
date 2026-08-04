#if os(macOS)
import AppKit
import XCTest

/// The Mac leg of the per-destination canary matrix (#4250, #4472 class).
///
/// `fichero/Tests/Unit/mac/` holds the tests that are genuinely macOS-only.
/// Most unit tests are platform-agnostic and live in `Tests/Unit/general/`;
/// this folder exists so a mac-only test has a home that is not "general with
/// an `#if os(macOS)` wrapper", and this canary exists so the folder can never
/// be silently empty-and-green: if the FicheroTests target stops compiling this
/// folder, or a plan runs it on the wrong device family, this is the first
/// failure and it names the misconfiguration.
final class MacTargetCanaryTests: XCTestCase {

    /// If this does not run, the Unit/mac folder is not wired into the target.
    func testTheMacUnitFolderExecutes() {
        XCTAssertTrue(true, "reaching this line is the assertion")
    }

    /// The plan that runs this target claims macOS. Verify at runtime rather
    /// than trusting the build: a unit bundle hosted by the wrong app family
    /// would still compile this file under a multiplatform SDK.
    func testItIsRunningOnMacOS() {
        XCTAssertTrue(
            ProcessInfo.processInfo.isMacCatalystApp == false,
            "FicheroTests is a native macOS bundle; a Catalyst host means the target is misconfigured"
        )
        XCTAssertNotNil(
            NSApplication.shared,
            "no NSApplication — the macOS test host did not launch, which is a target problem"
        )
    }
}
#endif
