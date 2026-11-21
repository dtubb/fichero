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
}
