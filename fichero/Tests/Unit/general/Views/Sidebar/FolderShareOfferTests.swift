@testable import Fichero
import XCTest

/// Gating of Share… on a folder row (## 824): never the always-there project, never a library another host serves, and only with
/// Multi-user on. Not run on the Pro; the builder/M4 runs it.
final class FolderShareOfferTests: XCTestCase {
    func testTheAlwaysThereProjectIsNeverOffered() {
        XCTAssertFalse(FolderShareOffer.isOffered(multiuser: true, isAlwaysThere: true, hostIsLocal: true))
    }

    func testAProjectAnotherHostServesIsNotOffered() {
        XCTAssertFalse(FolderShareOffer.isOffered(multiuser: true, isAlwaysThere: false, hostIsLocal: false))
    }

    func testMultiuserOffIsNotOffered() {
        XCTAssertFalse(FolderShareOffer.isOffered(multiuser: false, isAlwaysThere: false, hostIsLocal: true))
    }

    func testAHostedProjectWithMultiuserOnIsOffered() {
        XCTAssertTrue(FolderShareOffer.isOffered(multiuser: true, isAlwaysThere: false, hostIsLocal: true))
    }
}
