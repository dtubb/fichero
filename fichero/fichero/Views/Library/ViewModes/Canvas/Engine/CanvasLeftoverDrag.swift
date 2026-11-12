import Foundation

/// What a new press finds left of the last drag (#4601, `library.canvas.a-click-never-continues-the-last-drag`).
/// SwiftUI never calls `onEnded` on a CANCELLED drag (a competing recognizer, the window losing focus), so its state
/// stayed set and the next click moved the previously dragged card instead of selecting. At every mouse-down the board
/// finishes what is left: a single card is saved where it was left and selected as its release would have, a carried
/// selection goes back where it started. Pure: the board asks, this answers.
enum CanvasLeftoverDrag: Equatable {
    case none
    /// One card mid-drag: flush it through the controller (saved, selected on drop).
    case single(String)
    /// A carried selection mid-drag: every card back to its origin; nothing was saved.
    case group(String)

    static func at(press draggingNodeId: String?, carried: Int) -> CanvasLeftoverDrag {
        guard let draggingNodeId else { return .none }
        return carried > 0 ? .group(draggingNodeId) : .single(draggingNodeId)
    }
}
