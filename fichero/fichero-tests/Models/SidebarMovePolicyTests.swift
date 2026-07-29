@testable import Fichero
import XCTest

/// The shared move-eligibility decision behind the drag-drop handler and the
/// compact "Move to Folder" menu (#3014) — a folder is a valid target unless it
/// is the source itself or a descendant of it (no circular moves).
final class SidebarMovePolicyTests: XCTestCase {
    // root ├ A ├ A1 ├ A1a
    //      └ B
    private let tree: [Document] = [
        Document(id: "root", parentId: nil, docType: .folder, fileType: nil, name: "Root"),
        Document(id: "A", parentId: "root", docType: .folder, fileType: nil, name: "A"),
        Document(id: "A1", parentId: "A", docType: .folder, fileType: nil, name: "A1"),
        Document(id: "A1a", parentId: "A1", docType: .folder, fileType: nil, name: "A1a"),
        Document(id: "B", parentId: "root", docType: .folder, fileType: nil, name: "B")
    ]

    private func valid(_ source: String, _ target: String) -> Bool {
        SidebarMovePolicy.isValidTarget(sourceId: source, targetId: target, documents: tree)
    }

    func testSourceIsNotAValidTargetForItself() {
        XCTAssertFalse(valid("A", "A"))
    }

    func testDirectChildIsRejected() {
        // Moving A into its own child A1 would be circular.
        XCTAssertFalse(valid("A", "A1"))
    }

    func testDeepDescendantIsRejected() {
        XCTAssertFalse(valid("A", "A1a"))
    }

    func testSiblingAndAncestorAndUnrelatedAreValid() {
        XCTAssertTrue(valid("A", "B"))       // sibling
        XCTAssertTrue(valid("A", "root"))    // up to root
        XCTAssertTrue(valid("A1", "B"))      // out to another branch
        XCTAssertTrue(valid("A1a", "A"))     // up one level (not circular)
    }

    func testMalformedCyclicParentChainDoesNotHang() {
        // x → y → x is a cycle; the guardCount bound must terminate the walk.
        let cyclic = [
            Document(id: "x", parentId: "y", docType: .folder, fileType: nil, name: "X"),
            Document(id: "y", parentId: "x", docType: .folder, fileType: nil, name: "Y")
        ]
        XCTAssertTrue(SidebarMovePolicy.isValidTarget(sourceId: "z", targetId: "x", documents: cyclic))
    }
}
