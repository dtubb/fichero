@testable import Fichero
import XCTest

/// Delete Pass (#5227): the Making section sends `segment.pass_delete` with the pass id under the engine's
/// key, and offers nothing for a pass still read from an older result, which the engine refuses as
/// provisional. What breaks without these: the button sends a body the action rejects, or shows on every
/// unconverted page and fails there.
final class PassDeletionTests: XCTestCase {
    func testTheParamsCarryThePassIdUnderTheEnginesKey() throws {
        let data = try JSONEncoder().encode(PassDeleteParams(passId: "p1"))
        XCTAssertEqual(try JSONSerialization.jsonObject(with: data) as? [String: String], ["pass_id": "p1"])
    }

    func testAPassStillReadFromAnOlderResultIsNotOffered() {
        XCTAssertFalse(PassDeletion.canDelete("legacy:artifact-1"))
        XCTAssertTrue(PassDeletion.canDelete("2f1c9e"))
    }
}
