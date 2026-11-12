@testable import Fichero
import SwiftUI
import Testing

/// A click never continues the last drag (#4601, `library.canvas.a-click-never-continues-the-last-drag`): SwiftUI
/// skips `onEnded` on a cancelled drag, so the board finishes what is left at the next press.
@MainActor
struct CanvasLeftoverDragTests {
    @Test("nothing left, one card left, or a carried selection left")
    func whatThePressFinds() {
        #expect(CanvasLeftoverDrag.at(press: nil, carried: 0) == .none)
        #expect(CanvasLeftoverDrag.at(press: "a", carried: 0) == .single("a"))
        #expect(CanvasLeftoverDrag.at(press: "a", carried: 2) == .group("a"))
    }
}
