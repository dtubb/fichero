import Foundation
import XCTest

@testable import Fichero

// #3372: the QR/deep-link `library_path` is attacker-supplied, so it must be
// confirmed against the server's accessible-library set before it is persisted.
// `isLibraryConfirmed` is the pure decision that gate hinges on; these tests
// pin its behaviour without needing a live engine.
final class RemoteClientPairingLibraryConfirmTests: XCTestCase {
    func testConfirmedWhenAdvertisedPathIsAccessible() {
        let accessible = ["/Users/testuser/Archive/Open.fichero", "/Users/testuser/Other.fichero"]
        XCTAssertTrue(
            RemoteClientPairing.isLibraryConfirmed(
                advertised: "/Users/testuser/Archive/Open.fichero",
                in: accessible
            )
        )
    }

    func testForgedPathIsRejected() {
        let accessible = ["/Users/testuser/Archive/Open.fichero"]
        XCTAssertFalse(
            RemoteClientPairing.isLibraryConfirmed(
                advertised: "/Users/attacker/Evil.fichero",
                in: accessible
            )
        )
    }

    func testRejectedWhenServerReportsNoAccessibleLibraries() {
        XCTAssertFalse(
            RemoteClientPairing.isLibraryConfirmed(
                advertised: "/Users/testuser/Archive/Open.fichero",
                in: []
            )
        )
    }

    // Trailing-slash / whitespace variance between the QR value and the server's
    // reported path must not read as a forgery.
    func testTrailingSlashAndWhitespaceVarianceStillMatches() {
        let accessible = ["/Users/testuser/Archive/Open.fichero/"]
        XCTAssertTrue(
            RemoteClientPairing.isLibraryConfirmed(
                advertised: "  /Users/testuser/Archive/Open.fichero  ",
                in: accessible
            )
        )
    }

    // The default macOS APFS volume is case-insensitive, so a case difference
    // between the QR value and the server's reported path is the same library,
    // not a forgery — it must still confirm.
    func testCaseDifferenceStillMatchesOnCaseInsensitiveVolume() {
        let accessible = ["/Users/the user/Archive/Open.fichero"]
        XCTAssertTrue(
            RemoteClientPairing.isLibraryConfirmed(
                advertised: "/Users/testuser/Archive/Open.fichero",
                in: accessible
            )
        )
    }

    // Manual host entry carries no advertised library — nothing to confirm here;
    // the library picker (same endpoint) gates access afterwards.
    func testNilOrEmptyAdvertisedPathSkipsConfirmation() {
        XCTAssertTrue(RemoteClientPairing.isLibraryConfirmed(advertised: nil, in: []))
        XCTAssertTrue(RemoteClientPairing.isLibraryConfirmed(advertised: "   ", in: []))
    }
}
