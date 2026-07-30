import CoreGraphics
import Foundation
import simd

// MARK: - Default placement for row-less placeables (#4290)

/// Where a placeable sits when it has NO saved `CanvasItemLayout` row.
///
/// Why this is a choice rather than one rule: `SpatialLibraryProjector` lays
/// documents out with a golden-angle phyllotaxis on the **XZ** plane — the right
/// shape for the 3D 'Space' floor, where the camera looks across x and z and y
/// is height. The 2D ortho renderer projects `(x, −y)` and IGNORES z, so every
/// one of those defaults collapses onto the single line `y = 0`: a whole folder
/// rendered as one row, cards piled within a card's width of each other (#4290).
///
/// So the two renderers ask for different defaults. 3D keeps `.backendPosition`
/// (its plane is the one the projector was written for); 2D asks for `.grid`.
/// A saved row always wins over either — dragging a card pins it for good.
enum CanvasDefaultPlacement: Equatable {
    /// A node's backend `positionX/Y/Z`, and the 3-column cascade for items.
    case backendPosition
    /// A spaced grid on the x/y plane, `columns` wide.
    case grid(columns: Int)
}

/// The deterministic 2D board layout for placeables with no saved row: pure
/// `index + column count → world position`, so the same folder opens to the
/// same arrangement every time and adding a document never reshuffles the ones
/// already on screen.
///
/// The overlap this replaces did not merely look wrong, it broke dragging:
/// `CanvasDropResolver` reads any release within `defaultThreshold` of another
/// placeable as a drop-ONTO, so moving a card that sat on top of its neighbours
/// became a link — or, over a folder, a move-INTO that took the card off the
/// canvas entirely. Cell pitch on both axes therefore has to clear that
/// threshold with room to spare, and `CanvasGridPlacementTests` pins it.
enum CanvasGridPlacement {
    /// The renderer's default card footprint in world units, mirroring
    /// `CanvasOrtho2DRenderer.defaultCardSize` (1.0 × 0.75). Kept here as plain
    /// numbers so this stays a pure, main-actor-free function.
    static let cardWidth = 1.0
    static let cardHeight = 0.75

    /// The gutter between cards. Card + gutter is the cell pitch, and both
    /// pitches must exceed `CanvasDropResolver.defaultThreshold` (0.6) so two
    /// neighbouring default slots can never read as a drop-onto each other.
    static let gutter = 0.5

    static var cellWidth: Double { cardWidth + gutter }      // 1.5
    static var cellHeight: Double { cardHeight + gutter }     // 1.25

    /// The world slot for the `index`-th row-less placeable in a `columns`-wide
    /// grid: left-to-right, then down. `y` decreases per line because canonical
    /// space is y-up and the 2D projection flips it, so lower `y` reads as
    /// further DOWN the board — the same convention as the item cascade.
    ///
    /// A non-positive `columns` degrades to a single column rather than
    /// dividing by zero: a narrow board, never a crash or a pile at the origin.
    static func position(index: Int, columns: Int) -> SIMD3<Double> {
        let columnCount = max(columns, 1)
        let slot = max(index, 0)
        let column = Double(slot % columnCount)
        let line = Double(slot / columnCount)
        return SIMD3<Double>(column * cellWidth, -line * cellHeight, 0)
    }

    /// How many columns fit across `worldWidth` world units. At least one, so a
    /// hairline-thin viewport still lays cards out in a column instead of
    /// stacking them.
    static func columnCount(worldWidth: Double) -> Int {
        guard worldWidth.isFinite, worldWidth > 0 else { return 1 }
        return max(Int(worldWidth / cellWidth), 1)
    }

    /// Columns for a viewport, given the renderer's world-units-per-screen-point.
    ///
    /// The host supplies `worldPerPoint` (from its own projection) so this layer
    /// carries no renderer dependency. Hosts pass their camera's *fit* scale, not
    /// its live one: the grid must not re-flow while the user zooms — cards
    /// sliding out from under the pointer mid-pinch is exactly the "nothing stays
    /// where I put it" complaint #4290 is about. Resizing the window does
    /// re-flow, and only for cards that have no saved row yet.
    static func columnCount(viewportSize: CGSize, worldPerPoint: Float) -> Int {
        columnCount(worldWidth: Double(worldPerPoint) * Double(viewportSize.width))
    }
}
