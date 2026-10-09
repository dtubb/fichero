import CoreGraphics
import Foundation
import simd

// MARK: - Cards never move unless the person asks (#5629, `library.canvas.cards-move-only-when-asked`)

/// Remembers where every card on an open board was first drawn, so nothing the person did not ask
/// for can move it.
///
/// Ruled 2026-10-09: a card moves only when the person moves it (a drag, an Arrange, a move made in
/// another window, which is someone's drag too). Everything else that used to re-lay the board
/// leaves the cards where they are: the pane resizing (the default grid's column count follows the
/// pane), a card added to the folder (the column count follows the card count), page shapes landing
/// (they set the grid's spacing), a refresh, a selection, a zoom.
///
/// The rule this keeps:
/// - a card with a SAVED place is drawn there: saved places are what a person (or Arrange) chose;
/// - a card already on the board keeps the place it was first drawn at;
/// - the first time the board has cards, it takes the default layout as resolved;
/// - a card that arrives later takes the first FREE cell of the grid the board opened with, so it
///   shifts nothing.
///
/// One instance per canvas view, held in `@State`. A reference type on purpose: the view's body calls
/// `pin` while resolving the board, and recording here is not a SwiftUI state change, so it cannot
/// cause an update loop. Calling `pin` twice with the same input gives the same board.
@MainActor
final class CanvasPlacementMemory {
    /// The scope these places belong to. A different scope starts afresh.
    private(set) var scope: String?
    /// Where each card was last drawn on this board.
    private(set) var positions: [String: SIMD3<Double>] = [:]
    /// The grid the board opened with: where later cards find free cells.
    private(set) var grid: (columns: Int, cell: CGSize)?

    /// A grid cell, for finding the free ones.
    private struct Cell: Hashable {
        let column: Int
        let line: Int
    }

    /// `state` with every card held where it already is.
    ///
    /// - Parameters:
    ///   - state: the board as `CanvasSceneState.resolve` lays it out NOW.
    ///   - scope: the board's layout scope (a folder id or `wholeLibraryRoomId`).
    ///   - savedIds: the cards with a saved place; those always take it.
    ///   - columns: the default grid's column count `state` was resolved with.
    ///   - cell: the default grid's cell pitch `state` was resolved with.
    func pin(
        _ state: CanvasSceneState,
        scope: String,
        savedIds: Set<String>,
        columns: Int,
        cell: CGSize
    ) -> CanvasSceneState {
        if scope != self.scope {
            self.scope = scope
            positions = [:]
            grid = nil
        }
        var result = state
        let opening = positions.isEmpty
        if grid == nil, !state.placeables.isEmpty {
            grid = (columns, cell)
        }
        var onBoard: [String: SIMD3<Double>] = [:]
        var newcomers: [Int] = []
        for index in result.placeables.indices {
            let placeable = result.placeables[index]
            if savedIds.contains(placeable.id) {
                onBoard[placeable.id] = placeable.position
            } else if let kept = positions[placeable.id] {
                result.placeables[index].position = kept
                onBoard[placeable.id] = kept
            } else if opening {
                onBoard[placeable.id] = placeable.position
            } else {
                newcomers.append(index)
            }
        }
        if !newcomers.isEmpty, let grid {
            var taken = Set(onBoard.values.map { Self.cell(of: $0, pitch: grid.cell) })
            var slot = 0
            for index in newcomers {
                var position: SIMD3<Double>
                repeat {
                    position = CanvasGridPlacement.position(index: slot, columns: grid.columns, cell: grid.cell)
                    slot += 1
                } while taken.contains(Self.cell(of: position, pitch: grid.cell))
                taken.insert(Self.cell(of: position, pitch: grid.cell))
                result.placeables[index].position = position
                onBoard[result.placeables[index].id] = position
            }
        }
        // Merged, not replaced: a card a filter hides for a moment comes back where it was.
        positions.merge(onBoard) { _, now in now }
        return result
    }

    /// The grid cell nearest a position.
    private static func cell(of position: SIMD3<Double>, pitch: CGSize) -> Cell {
        let width = max(Double(pitch.width), 0.001), height = max(Double(pitch.height), 0.001)
        return Cell(column: Int((position.x / width).rounded()), line: Int((position.y / height).rounded()))
    }
}
