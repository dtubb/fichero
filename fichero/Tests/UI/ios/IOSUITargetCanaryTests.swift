#if os(iOS)
import UIKit
import XCTest

/// The iPhone UI leg of the per-destination canary matrix (#4250, #4472 class).
///
/// FicheroIOSUITests is the first UI-testing bundle that can run on the iOS
/// device families at all; `fichero-ui-ios.xctestplan` selects this class so
/// the iPhone UI plan can never be empty-and-green, and fails loudly when it
/// executes on the wrong device family. Deliberately trivial — it does not
/// launch the app — because a canary that needs a working app cannot tell
/// "the destination is wrong" from "the app is broken".
final class IOSUITargetCanaryTests: XCTestCase {

    /// If this does not run, the iPhone UI plan executed nothing.
    func testTheIOSUIBundleExecutes() {
        XCTAssertTrue(true, "reaching this line is the assertion")
    }

    /// The iPad UI plan selects IPadUITargetCanaryTests instead; a `.pad`
    /// result here means the -destination is wrong, not the app.
    func testItIsRunningOnAnIPhoneIdiom() {
        XCTAssertEqual(
            UIDevice.current.userInterfaceIdiom,
            .phone,
            """
            fichero-ui-ios.xctestplan is the iPhone UI leg. Running it on an \
            iPad simulator double-counts the iPad plan and verifies nothing \
            new — fix the -destination, not this test.
            """
        )
    }
}
#endif
