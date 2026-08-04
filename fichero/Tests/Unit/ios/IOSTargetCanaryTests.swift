#if os(iOS)
import UIKit
import XCTest

/// The iPhone leg of the per-destination canary matrix (#4250, #4472 class).
///
/// `fichero-ios.xctestplan` runs FicheroIOSTests on an iPhone simulator. This
/// canary is the first thing that fails when the plan executes on the wrong
/// device family, and it says so in the failure rather than leaving a green
/// run that verified a different platform than the one the plan is named for.
/// Deliberately trivial: a canary that needs an engine or a fixture cannot
/// tell "the destination is wrong" from "the app is broken".
final class IOSTargetCanaryTests: XCTestCase {

    /// If this does not run, nothing else in the plan means anything.
    func testTheIOSUnitBundleExecutes() {
        XCTAssertTrue(true, "reaching this line is the assertion")
    }

    /// This plan is the iPhone leg; iPad has its own plan and its own canary
    /// (IPadTargetCanaryTests). A `.pad` result here means the destination in
    /// the invocation is wrong, not the app.
    func testItIsRunningOnAnIPhoneIdiom() {
        XCTAssertEqual(
            UIDevice.current.userInterfaceIdiom,
            .phone,
            """
            fichero-ios.xctestplan is the iPhone leg. Running it on an iPad \
            simulator double-counts the iPad plan and verifies nothing new — \
            fix the -destination, not this test.
            """
        )
    }
}
#endif
