#if os(iOS)
@testable import Fichero
import XCTest

/// Behaviour that can only be checked BY RUNNING ON iPad (#4505).
///
/// The distinction this file exists to hold: an assertion about which
/// affordances the source mounts does not need an iPad and belongs in the Mac
/// target (`InspectorTouchReachabilityTests`) or in a guardrail script. An
/// assertion about what the platform actually DOES needs the platform. Only the
/// second kind belongs here.
///
/// It is a short list on purpose. Padding an iPad target with tests that would
/// pass anywhere is how a suite comes to look like coverage without being any.
final class IPadPlatformBehaviourTests: XCTestCase {

    /// `Copy Name` in the entity inspector wrote through `NSPasteboard` behind
    /// `#if canImport(AppKit)`, so on iPad the Button rendered with an EMPTY
    /// body — a menu item that does nothing (#4421's rule, caught in the wild).
    /// It now goes through `PlatformPasteboard`; this proves that helper
    /// genuinely round-trips on iPad rather than being a second way to do
    /// nothing.
    ///
    /// This is the assertion that makes running on iPad worth the target: it is
    /// `UIPasteboard` underneath, and no macOS run can exercise it.
    func testThePasteboardHelperRoundTripsOnIPad() {
        let unique = "fichero-\(UUID().uuidString)"

        PlatformPasteboard.writeString(unique)

        XCTAssertEqual(
            PlatformPasteboard.string(),
            unique,
            "PlatformPasteboard is the only clipboard path view code may use; on iPad it must work"
        )
    }
}
#endif
