@testable import Fichero
import XCTest

/// #6449: the Inspector's reading field filled four lines with its own scrollbar while the pane below it was empty.
/// Its height now follows the container's.
final class InspectorReadingFieldHeightTests: XCTestCase {
    func testTheFieldFollowsTheContainerHeight() {
        let tall = InspectorReadingEdit.fieldHeight(container: 900)
        let short = InspectorReadingEdit.fieldHeight(container: 500)
        XCTAssertEqual(tall, 900 - InspectorReadingEdit.reservedBesideField)
        XCTAssertEqual(short, 500 - InspectorReadingEdit.reservedBesideField)
        XCTAssertEqual(tall - short, 400, "resize the container by 400 and the field follows by 400")
    }

    func testTheFieldIsNeverUnderItsMinimum() {
        XCTAssertEqual(InspectorReadingEdit.fieldHeight(container: 0), InspectorReadingEdit.minimumFieldHeight)
        XCTAssertEqual(InspectorReadingEdit.fieldHeight(container: 150), InspectorReadingEdit.minimumFieldHeight)
    }
}
