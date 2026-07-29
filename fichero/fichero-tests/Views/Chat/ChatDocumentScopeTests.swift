@testable import Fichero
import XCTest

/// The shared chat-scope attach handler (#3015) — drop and the compact composer
/// attach button both route document ids through `ChatDocumentScope.attaching`.
final class ChatDocumentScopeTests: XCTestCase {
    func testAttachAddsNewIds() {
        let scope = ChatDocumentScope.attaching(["a", "b"], to: [])
        XCTAssertEqual(scope, ["a", "b"])
    }

    func testAttachIsDeduplicatedAndUnions() {
        let scope = ChatDocumentScope.attaching(["b", "c"], to: ["a", "b"])
        XCTAssertEqual(scope, ["a", "b", "c"])
    }

    func testAttachIgnoresBlankIds() {
        let scope = ChatDocumentScope.attaching(["", "  ", "a"], to: [])
        XCTAssertEqual(scope, ["a"])
    }

    func testAttachEmptyLeavesScopeUnchanged() {
        XCTAssertEqual(ChatDocumentScope.attaching([], to: ["a"]), ["a"])
    }
}
