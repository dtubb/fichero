#if os(iOS)
import UIKit
import XCTest

/// The canary: does anything run on iPad at all? (#4472)
///
/// `fichero-ipad.xctestplan` existed for a month and never once ran. First it
/// was deliberately empty — zero testTargets — which reports TEST SUCCEEDED
/// having executed nothing. Then a commit noticed "a plan with no targets can
/// never fail" and put `FicheroTests` in it, and the plan went from
/// silently-green to hard-refusing:
///
///     Cannot test target "FicheroTests" on "iPad Pro 13-inch (M5)":
///     FicheroTests does not support iPad Pro 13-inch (M5)
///
/// Both states are the same defect in different clothes. `FicheroTests` and
/// `FicheroUITests` inherit `SDKROOT=macosx` from the project and declare no
/// `SUPPORTED_PLATFORMS`, so nothing on iPad had ever been verified by
/// anything — which is why the inspector-List audit (#4502) had to mark five
/// platform claims unverifiable.
///
/// This suite exists to be the FIRST thing that fails when the target is
/// misconfigured, and to fail with a message that says which. Everything here
/// is deliberately trivial: a canary that needs a working engine, a network, or
/// a fixture cannot tell "the target is wrong" from "the app is broken".
final class IPadTargetCanaryTests: XCTestCase {

    /// If this does not run, nothing else in the plan means anything.
    func testTheTestBundleRunsOnIOS() {
        XCTAssertTrue(true, "reaching this line is the assertion")
    }

    /// The target is iPad-specific, so a run on an iPhone simulator is a
    /// misconfiguration and not a pass. Stated as an assertion rather than a
    /// comment because "we meant iPad" is exactly the kind of intent that
    /// silently stops being true.
    func testItIsRunningOnAnIPadIdiom() {
        XCTAssertEqual(
            UIDevice.current.userInterfaceIdiom,
            .pad,
            """
            This target is for iPad. Running it on an iPhone simulator does not \
            verify what #4472 asked for — check the destination in the scheme, \
            not this test.
            """
        )
    }

    /// A regular-width iPad is the shape the inspector's docked layout assumes.
    /// If this fails the simulator is running in a compact split view, which
    /// changes what every layout assertion in this target means.
    func testTheWindowIsRegularWidth() throws {
        let scene = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first
        let window = try XCTUnwrap(
            scene?.windows.first,
            "no window — the test host app did not launch, which is a target problem"
        )

        XCTAssertEqual(
            window.traitCollection.horizontalSizeClass,
            .regular,
            "iPad full-screen should be regular width; a compact result means a split-view run"
        )
    }
}
#endif
