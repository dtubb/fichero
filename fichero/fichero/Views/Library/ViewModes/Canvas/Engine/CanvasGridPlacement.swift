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
    /// The renderer's NOMINAL card footprint in world units, mirroring
    /// `CanvasOrtho2DRenderer.defaultCardSize` (1.0 × 0.75). Kept here as plain
    /// numbers so this stays a pure, main-actor-free function.
    ///
    /// Nominal, not actual: `CanvasCardGeometry` normalises every card on AREA,
    /// so a double-spread at aspect 2.0 renders 1.22 wide and 0.61 tall while
    /// covering this same area. Cell pitch therefore derives from the board's
    /// ACTUAL extents (`cell(forAspects:)`), never from these two numbers alone
    /// — the §18.1 defect 4 fix.
    static let cardWidth = 1.0
    static let cardHeight = 0.75
    static var cardArea: Double { cardWidth * cardHeight }

    /// The gutter, as a fraction of the widest card on the board (§6.3: ≈0.15
    /// at the `.thumbnail` tier). It was a flat 0.5 against a 1.0-wide card —
    /// 50% of card width, so the board read as scattered specks rather than a
    /// field you can scan.
    static let gutterFraction = 0.15

    /// Cell pitch may never fall to the drop threshold: `CanvasDropResolver`
    /// reads any release within `defaultThreshold` of another placeable as a
    /// drop-ONTO, so two neighbouring default slots would resolve as a link (or
    /// a move-into-folder) instead of a move. 5% of headroom over the threshold,
    /// because equality is already the bug.
    static var minimumPitch: Double { CanvasDropResolver.defaultThreshold * 1.05 }

    /// The extents of the widest and the tallest card the board can show, given
    /// the page aspects known so far (`CanvasCardGeometry` memoizes one per
    /// source as its texture loads).
    ///
    /// Area-normalised, matching `CanvasCardGeometry.dimensions`: for aspect
    /// `a`, `width = sqrt(area · a)` and `height = sqrt(area / a)`. The nominal
    /// aspect is always in the running because a card whose texture has not
    /// loaded still renders at the fallback shape.
    static func cardExtents(forAspects aspects: [Double]) -> CGSize {
        let nominalAspect = cardWidth / cardHeight
        let usable = aspects.filter { $0.isFinite && $0 > 0 }
        let widest = max(usable.max() ?? nominalAspect, nominalAspect)
        let tallest = min(usable.min() ?? nominalAspect, nominalAspect)
        return CGSize(
            width: (cardArea * widest).squareRoot(),
            height: (cardArea / tallest).squareRoot()
        )
    }

    /// The cell pitch for a board showing cards of these aspects: the actual max
    /// extents plus one gutter, floored above the drop threshold.
    ///
    /// Aspects arrive as textures load, so a board of row-less cards can re-flow
    /// ONCE as they land — the same class of re-flow as resizing the window, and
    /// bounded the same way: a saved row always wins, so nothing the user has
    /// placed ever moves.
    static func cell(forAspects aspects: [Double]) -> CGSize {
        let extents = cardExtents(forAspects: aspects)
        let width = Double(extents.width), height = Double(extents.height)
        let gutter = gutterFraction * width
        return CGSize(
            width: max(width + gutter, minimumPitch),
            height: max(height + gutter, minimumPitch)
        )
    }

    /// The cell for a board whose page aspects are not known yet — what every
    /// caller that has no aspects to offer gets.
    static var nominalCell: CGSize { cell(forAspects: []) }

    static var cellWidth: Double { Double(nominalCell.width) }       // 1.15
    static var cellHeight: Double { Double(nominalCell.height) }     // 0.90

    /// The world slot for the `index`-th row-less placeable in a `columns`-wide
    /// grid: left-to-right, then down. `y` INCREASES per line: the projection
    /// renders scene y as −world.y, so growing world y is what reads as
    /// further DOWN the board. The old `−line` double-negated with the
    /// projection and the grid marched UP from the bottom-left (user,
    /// 2026-08-20: "laid out from bottom left, not top left").
    ///
    /// A non-positive `columns` degrades to a single column rather than
    /// dividing by zero: a narrow board, never a crash or a pile at the origin.
    static func position(index: Int, columns: Int, cell: CGSize) -> SIMD3<Double> {
        let columnCount = max(columns, 1)
        let slot = max(index, 0)
        let column = Double(slot % columnCount)
        let line = Double(slot / columnCount)
        return SIMD3<Double>(column * Double(cell.width), line * Double(cell.height), 0)
    }

    /// The nominal-cell slot — for callers with no page aspects to offer.
    static func position(index: Int, columns: Int) -> SIMD3<Double> {
        position(index: index, columns: columns, cell: nominalCell)
    }

    /// How many columns fit across `worldWidth` world units. At least one, so a
    /// hairline-thin viewport still lays cards out in a column instead of
    /// stacking them.
    static func columnCount(worldWidth: Double, cell: CGSize? = nil) -> Int {
        guard worldWidth.isFinite, worldWidth > 0 else { return 1 }
        return max(Int(worldWidth / Double((cell ?? nominalCell).width)), 1)
    }

    /// Columns for a viewport, given the renderer's world-units-per-screen-point.
    ///
    /// The host supplies `worldPerPoint` (from its own projection) so this layer
    /// carries no renderer dependency. Hosts pass their camera's *fit* scale, not
    /// its live one: the grid must not re-flow while the user zooms — cards
    /// sliding out from under the pointer mid-pinch is exactly the "nothing stays
    /// where I put it" complaint #4290 is about. Resizing the window does
    /// re-flow, and only for cards that have no saved row yet.
    static func columnCount(viewportSize: CGSize, worldPerPoint: Float, cell: CGSize? = nil) -> Int {
        columnCount(worldWidth: Double(worldPerPoint) * Double(viewportSize.width), cell: cell)
    }
}
