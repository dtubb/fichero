#if os(macOS)
import XCTest

/// The Mac leg of the per-destination UI canary matrix (#4250, #4472 class).
///
/// `fichero/Tests/UI/mac/` holds macOS-only UI tests; the platform-agnostic
/// bulk lives in `Tests/UI/general/`. This canary keeps the folder from ever
/// being empty-and-green: if the FicheroUITests target stops compiling this
/// folder, or a plan runs it on the wrong device family, this fails first and
/// says which. Deliberately trivial — no engine, no launch — because a canary
/// that needs a working app cannot tell "the target is wrong" from "the app
/// is broken".
final class MacUITargetCanaryTests: XCTestCase {

    /// If this does not run, the UI/mac folder is not wired into the target.
    func testTheMacUIFolderExecutes() {
        XCTAssertTrue(true, "reaching this line is the assertion")
    }

    /// The plans that run this target claim macOS. `os(macOS)` proves the SDK;
    /// this proves the runtime host, which is what a wrong destination changes.
    func testItIsRunningOnMacOS() {
        XCTAssertFalse(
            ProcessInfo.processInfo.isiOSAppOnMac,
            "an iOS-app-on-Mac host means the destination is wrong, not the app"
        )
    }
}
#endif
