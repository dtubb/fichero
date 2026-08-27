@testable import Fichero
import XCTest

final class ActionInvokeResultTests: XCTestCase {
    func testDecodesActionResultWireKeys() throws {
        let result = try JSONDecoder().decode(
            ActionInvokeResult.self,
            from: Data(#"{"ok":true,"audit_id":"audit-1","changed_domains":["documents","claims"]}"#.utf8)
        )

        XCTAssertTrue(result.succeeded)
        XCTAssertEqual(result.auditId, "audit-1")
        XCTAssertEqual(result.changedDomains, ["documents", "claims"])
    }
}
