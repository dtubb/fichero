@testable import Fichero
import XCTest

/// Escape during a Shape-tool polygon or baseline (`source.editor.draw-shapes`): the preview's exit
/// command asks the window to abandon the drawing FIRST, and only when there was none does Escape do
/// what it always did (clear marquees, the selection, the adding mode). What breaks without this: an
/// Escape that leaves half a polygon waiting for the next click, or one that throws the selection away
/// along with the drawing.
@MainActor
final class ShapeDrawingEscapeTests: XCTestCase {
    func testEscapeAbandonsADrawingInProgressAndNothingElse() {
        let state = WindowState(libraryId: UUID())
        XCTAssertFalse(state.abandonDrawing(), "nothing drawn: Escape does what it always did")
        state.drawingPoints = [[0.1, 0.1], [0.3, 0.1]]
        XCTAssertTrue(state.abandonDrawing(), "a drawing in progress is what this Escape is for")
        XCTAssertEqual(state.drawingPoints, [], "and nothing of it is kept to be finished later")
        XCTAssertFalse(state.abandonDrawing(), "the next Escape is the usual one")
    }
}
