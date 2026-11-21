@testable import Fichero
import XCTest

/// The iPhone drill-down from a file (#6566, owner ruling 2026-11-13):
/// Sidebar → Items → Source → Reader → Info. `CompactDocumentStep` is the pure map of which
/// steps each screen offers; the stack's Back always returns one screen.
final class CompactDocumentStepTests: XCTestCase {
    func testSourceOffersReaderAndInfo() {
        XCTAssertEqual(CompactDocumentStep.source.next, [.reader, .info])
    }

    func testReaderOffersInfo() {
        XCTAssertEqual(CompactDocumentStep.reader.next, [.info])
    }

    func testInfoOffersNothingFurther() {
        XCTAssertEqual(CompactDocumentStep.info.next, [])
    }

    /// From a file, Reader and Info are both reachable.
    func testReaderAndInfoReachableFromSource() {
        let reachable = Set(CompactDocumentStep.source.next)
        XCTAssertTrue(reachable.contains(.reader))
        XCTAssertTrue(reachable.contains(.info))
    }

    /// Every step has a title for its button and bar.
    func testEveryStepHasATitle() {
        XCTAssertEqual(CompactDocumentStep.allCases.map(\.title), ["Source", "Reader", "Info"])
    }
}
