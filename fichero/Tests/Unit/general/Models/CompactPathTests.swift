@testable import Fichero
import XCTest

/// `ios.nav.one-path` (#6944): the iPhone's ONE path, tested with no view.
final class CompactPathTests: XCTestCase {
    func testOpeningAnItemPushesItAndBackPopsItAlone() {
        var path = CompactPath()
        path.open(item: "a")
        XCTAssertEqual(path.steps, [.item("a")])
        path.back()
        XCTAssertEqual(path.steps, [])
        XCTAssertNil(path.itemId)
    }

    func testReaderAndInfoStackOnTheItemAndBackReturnsOneLevelEachTime() {
        var path = CompactPath()
        path.open(item: "a")
        path.push(.reader)
        path.push(.info)
        XCTAssertEqual(path.steps, [.item("a"), .reader, .info])
        XCTAssertEqual(path.itemId, "a", "pushing Reader and Info does not replace the item")
        path.back()
        XCTAssertEqual(path.steps, [.item("a"), .reader])
        path.back()
        XCTAssertEqual(path.steps, [.item("a")])
    }

    func testOpeningAnotherItemReplacesTheItemAndWhatSitsOnIt() {
        var path = CompactPath()
        path.set([.folder("f"), .item("a"), .reader])
        path.open(item: "b")
        XCTAssertEqual(path.steps, [.folder("f"), .item("b")])
    }

    func testOpeningTheSameItemTwiceChangesNothing() {
        var path = CompactPath()
        path.set([.item("a"), .info])
        path.open(item: "a")
        XCTAssertEqual(path.steps, [.item("a"), .info])
    }

    func testLegalAndIllegalPaths() {
        XCTAssertTrue(CompactPath.isValid([]))
        XCTAssertTrue(CompactPath.isValid([.folder("a"), .folder("b"), .item("c"), .reader, .info]))
        XCTAssertTrue(CompactPath.isValid([.item("c"), .info]))
        XCTAssertFalse(CompactPath.isValid([.reader]), "Reader needs an item under it")
        XCTAssertFalse(CompactPath.isValid([.item("a"), .folder("b")]), "a folder never sits on an item")
        XCTAssertFalse(CompactPath.isValid([.item("a"), .item("b")]), "at most one item")
        XCTAssertFalse(CompactPath.isValid([.item("a"), .info, .reader]), "Reader is pushed before Info")
    }

    // MARK: - ios.nav.folders-push, ios.nav.back-is-one-step (#6945)

    func testFoldersPushAndBackReturnsOneFolderAtATime() {
        var path = CompactPath()
        path.pushFolder("A", from: "root")
        path.pushFolder("B", from: "A")
        XCTAssertEqual(path.steps, [.folder("A"), .folder("B")])
        XCTAssertEqual(path.currentFolderId, "B")
        path.back()
        XCTAssertEqual(path.currentFolderId, "A", "Back shows A's list")
        path.back()
        XCTAssertEqual(path.steps, [])
        XCTAssertEqual(path.currentFolderId, "root", "Back from the first folder shows the list it was pushed from")
    }

    func testAFolderIsNotPushedOnAnItemOrTwice() {
        var path = CompactPath()
        path.pushFolder("A", from: "root")
        path.pushFolder("A", from: "A")
        XCTAssertEqual(path.steps, [.folder("A")])
        path.open(item: "x")
        path.pushFolder("B", from: "A")
        XCTAssertEqual(path.steps, [.folder("A"), .item("x")])
    }

    func testBackFromAnItemInAFolderShowsThatFolder() {
        var path = CompactPath()
        path.pushFolder("A", from: "root")
        path.open(item: "x")
        path.push(.reader)
        path.back()
        path.back()
        XCTAssertEqual(path.steps, [.folder("A")])
        XCTAssertEqual(path.currentFolderId, "A")
    }
}
