@testable import Fichero
import XCTest

/// The `fichero://` scheme MUST be registered with the OS (#3788).
///
/// This is the test that was never written, and its absence is the whole bug: the
/// app mints `fichero://pair` and `fichero://invite` links, offers Copy and Share
/// buttons for them, and has complete `onOpenURL` receive paths on both platforms —
/// but `CFBundleURLTypes` was declared NOWHERE, so nothing claimed the scheme and a
/// tapped link did nothing. #2399 ("tappable pair link") shipped dead on arrival.
///
/// These assert against `Bundle.main`, which in this test bundle is the HOST APP
/// (TEST_HOST = Fichero.app). So this checks the REAL, MERGED product Info.plist —
/// the thing the OS actually reads — not a source file that may or may not reach the
/// build. If someone removes the registration, this fails.
final class URLSchemeRegistrationTests: XCTestCase {

    private func urlTypes() throws -> [[String: Any]] {
        let raw = Bundle.main.object(forInfoDictionaryKey: "CFBundleURLTypes")
        return try XCTUnwrap(
            raw as? [[String: Any]],
            "CFBundleURLTypes is missing from the built app. Nothing claims fichero://, "
            + "so every pairing/invite link the app generates is dead when tapped (#3788)."
        )
    }

    private func schemes() throws -> [String] {
        try urlTypes().flatMap { ($0["CFBundleURLSchemes"] as? [String]) ?? [] }
    }

    /// The load-bearing assertion.
    func testBuiltAppClaimsTheFicheroScheme() throws {
        XCTAssertTrue(
            try schemes().contains("fichero"),
            "The built app does not claim the 'fichero' scheme. Links minted by "
            + "SessionStore/RemoteClientPairing cannot open the app."
        )
    }

    /// The scheme is what the pairing/invite links are actually built on — if the two
    /// ever drift apart, links break silently, so pin them to each other.
    func testTheRegisteredSchemeIsTheOneOurLinksUse() throws {
        // A representative link of each kind the app mints.
        for link in ["fichero://pair?payload=abc", "fichero://invite?token=abc"] {
            let scheme = try XCTUnwrap(URL(string: link)?.scheme)
            XCTAssertTrue(
                try schemes().contains(scheme),
                "The app mints \(link) but does not register '\(scheme)'."
            )
        }
    }

    /// A URL type needs a role, or Launch Services may ignore the declaration.
    func testURLTypeDeclaresAViewerRole() throws {
        let ficheroType = try XCTUnwrap(
            try urlTypes().first { ($0["CFBundleURLSchemes"] as? [String])?.contains("fichero") == true }
        )
        XCTAssertEqual(ficheroType["CFBundleTypeRole"] as? String, "Viewer")
    }
}
