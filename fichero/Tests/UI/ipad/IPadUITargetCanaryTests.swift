#if os(iOS)
import UIKit
import XCTest

/// The iPad UI leg of the per-destination canary matrix (#4250, #4472).
///
/// The iPad plan was green for a month having executed nothing (#4472); the
/// unit half got IPadTargetCanaryTests, and this is the UI half of the same
/// defense: `fichero-ui-ipad.xctestplan` selects this class, so the iPad UI
/// plan can never be empty-and-green, and fails loudly when it executes on
/// the wrong device family. Deliberately trivial — it does not launch the
/// app — because a canary that needs a working app cannot tell "the
/// destination is wrong" from "the app is broken".
final class IPadUITargetCanaryTests: XCTestCase {

    /// If this does not run, the iPad UI plan executed nothing.
    func testTheIPadUIBundleExecutes() {
        XCTAssertTrue(true, "reaching this line is the assertion")
    }

    /// The iPhone UI plan selects IOSUITargetCanaryTests instead; a `.phone`
    /// result here means the -destination is wrong, not the app.
    func testItIsRunningOnAnIPadIdiom() {
        XCTAssertEqual(
            UIDevice.current.userInterfaceIdiom,
            .pad,
            """
            fichero-ui-ipad.xctestplan is the iPad UI leg. Running it on an \
            iPhone simulator verifies what the iPhone plan already covers — \
            fix the -destination, not this test.
            """
        )
    }
}
#endif
