import CoreGraphics
import Foundation
import simd
import SwiftUI

// MARK: - Canvas move/resize, and their undo (#3084 / #4409)

/// Split out of `CanvasInteractionController` by cohesion: the two mutations
/// that register with the window `UndoManager`, plus the resize primitive they
/// support.
///
/// They share ONE pattern deliberately — undo applies the inverse and
/// re-registers, so redo replays the change. #4409 requires a resize to be
/// undoable "like any other mutation", and the way to guarantee that is to use
/// the same pattern rather than to write a second one.
extension CanvasInteractionController {

    // MARK: Move + undo (#3084)

    /// Persist a single item's snapped position — the undo/redo primitive and any
    /// programmatic move. Reuses the exactly-one-row persist.
    @discardableResult
    func moveItem(id: String, to worldPosition: SIMD3<Double>) async -> Bool {
        await persistSingleRow(id: id, to: snap(worldPosition), rollbackTo: nil)
    }

    // MARK: - Resize + undo (#4409)

    /// Persist a card's new size. Goes through the SAME exactly-one-row persist
    /// as a move, so a resize can never become the pin-all-visible batch that
    /// #3084 called save-poison.
    @discardableResult
    func resizeItem(id: String, to size: CGSize, at worldPosition: SIMD3<Double>) async -> Bool {
        await persistSingleRow(id: id, to: worldPosition, size: size, rollbackTo: nil)
    }

    /// Register a resize with the window `UndoManager`, exactly as a move is —
    /// #4409 requires resizing to be undoable "like any other mutation", and
    /// the way to guarantee that is to use the same pattern rather than a
    /// second one. Undo restores `origin` and registers the inverse, so redo
    /// replays the resize.
    func registerResizeUndo(
        id: String,
        at worldPosition: SIMD3<Double>,
        origin: CGSize,
        destination: CGSize,
        undoManager: UndoManager?
    ) {
        guard let undoManager, origin != destination else { return }
        undoManager.registerUndo(withTarget: self) { controller in
            MainActor.assumeIsolated {
                Task { await controller.resizeItem(id: id, to: origin, at: worldPosition) }
                controller.registerResizeUndo(
                    id: id, at: worldPosition, origin: destination, destination: origin, undoManager: undoManager
                )
            }
        }
        undoManager.setActionName("Resize")
    }

    /// Register a drag move with the window `UndoManager` (position before/after,
    /// #3084). The canonical move pattern: undoing moves back to `from` and
    /// re-registers the inverse, so redo replays the move — repeatable both ways.
    func registerMoveUndo(id: String, origin: SIMD3<Double>, destination: SIMD3<Double>, undoManager: UndoManager?) {
        guard let undoManager, origin != destination else { return }
        undoManager.registerUndo(withTarget: self) { controller in
            // UndoManager invokes the handler on the thread that called undo()
            // (main, for UI), so assume main-actor isolation to reach the
            // @MainActor controller. Undoing moves back to `origin` and registers
            // the inverse, so redo replays the move — repeatable both directions.
            MainActor.assumeIsolated {
                Task { await controller.moveItem(id: id, to: origin) }
                controller.registerMoveUndo(id: id, origin: destination, destination: origin, undoManager: undoManager)
            }
        }
        undoManager.setActionName("Move")
    }
}
