import CoreGraphics
import Foundation
import simd

// MARK: - What selection LOOKS like on a spatial surface (#4409)

/// The geometry and the policy behind the canvas selection frame, resize
/// handles and multi-selection set frame — pure, renderer-free and testable.
///
/// ## Why this is a type rather than code inside a renderer
///
/// Before this, "selected" was a solid accent plane the renderer built inline
/// inside `makeCard`, which is what forced a card REBUILD on every selection
/// change (#4409's blue flash — see `CanvasOrtho2DRenderer.setSelection`).
/// Pulling the decoration out of the card is what makes the flash impossible
/// rather than merely absent, and once it is out it has to live somewhere both
/// RealityKit renderers can reach. That is here.
///
/// Everything below works in the renderer's own PLANE coordinates (x right,
/// y up), already projected. The 2D ortho renderer passes `(x, −y)` scene
/// points and the 3D renderer passes `(x, y)` at the card's z, so neither
/// projection leaks in and both get the same frame model — which is what #4409
/// asks for when it says the affordances differ but the model is identical.
enum CanvasSelectionFrame {

    // MARK: - Entity naming
    //
    // Decoration entities live in the scene alongside cards, so the HOST's
    // `.targetedToAnyEntity()` gestures will happily target them. A name
    // prefix is how a host tells "a card" from "the frame around a card"
    // without a second entity registry to keep in step.

    /// Every decoration entity's name starts with this. A host that reads
    /// `value.entity.name` as a placeable id MUST skip these — otherwise a tap
    /// on the frame selects a placeable called "canvas.selection.frame:…",
    /// which exists nowhere.
    static let decorationNamePrefix = "canvas.selection."

    /// Resize handles are the one decoration that IS interactive.
    static let handleNamePrefix = decorationNamePrefix + "handle:"

    static func isDecoration(_ entityName: String) -> Bool {
        entityName.hasPrefix(decorationNamePrefix)
    }

    static func handleName(corner: Corner, itemId: String) -> String {
        "\(handleNamePrefix)\(corner.rawValue):\(itemId)"
    }

    /// Decode a handle entity name back into what it acts on.
    ///
    /// Split on the FIRST colon after the corner only: placeable ids are
    /// namespaced (`doc:…`, `entity:…`) and contain colons of their own, so a
    /// naive `split(separator: ":")` would truncate every id in the app.
    static func handle(fromEntityName name: String) -> (corner: Corner, itemId: String)? {
        guard name.hasPrefix(handleNamePrefix) else { return nil }
        let body = name.dropFirst(handleNamePrefix.count)
        guard let separator = body.firstIndex(of: ":") else { return nil }
        guard let corner = Corner(rawValue: String(body[body.startIndex..<separator])) else { return nil }
        let itemId = String(body[body.index(after: separator)...])
        guard !itemId.isEmpty else { return nil }
        return (corner, itemId)
    }

    // MARK: - Model

    /// One selected thing, already projected onto the renderer's plane.
    struct Item: Equatable {
        let id: String
        let centerX: Float
        let centerY: Float
        let width: Float
        let height: Float
        let isResizable: Bool
    }

    /// An axis-aligned rectangle in the renderer's plane.
    struct Box: Equatable {
        var centerX: Float
        var centerY: Float
        var width: Float
        var height: Float

        var minX: Float { centerX - width / 2 }
        var maxX: Float { centerX + width / 2 }
        var minY: Float { centerY - height / 2 }
        var maxY: Float { centerY + height / 2 }
    }

    enum Corner: String, CaseIterable, Equatable {
        case bottomLeading, bottomTrailing, topLeading, topTrailing

        /// −1 on the leading side, +1 on the trailing side.
        var xSign: Float { self == .bottomLeading || self == .topLeading ? -1 : 1 }
        /// −1 at the bottom, +1 at the top — plane coordinates are y-UP, which
        /// is what `Canvas2DProjection.sceneDelta` already converts a screen
        /// translation into, so a drag delta needs no second flip here.
        var ySign: Float { self == .bottomLeading || self == .bottomTrailing ? -1 : 1 }
    }

    struct Handle: Equatable {
        let itemId: String
        let corner: Corner
        let positionX: Float
        let positionY: Float
    }

    /// Everything the renderer must draw for the current selection.
    struct Plan: Equatable {
        /// One frame per selected item, so a multi-selection reads as N things
        /// that are each selected …
        var itemBoxes: [Box]
        /// … and this reads as ONE set containing them, which is the
        /// difference between "a sequence of individual highlights" and a
        /// selection (#4409). Nil for a single selection, where the item frame
        /// already is the set.
        var setBox: Box?
        /// Corner handles. Empty unless exactly one resizable item is
        /// selected — see `plan(for:)`.
        var handles: [Handle]
    }

    // MARK: - Sizing constants (plane units; a default 2D card is 1.0 × 0.75)

    /// Gap between a card's edge and its frame, so the frame reads as a frame
    /// around the card rather than a border drawn on it.
    static let itemInset: Float = 0.06
    /// A further gap between the outermost item frame and the set frame.
    static let setInset: Float = 0.12
    /// Smallest and largest a card may be resized to. Clamped in PLANE units
    /// because that is where the user is dragging; the persisted `w`/`h` are
    /// the same units.
    static let minimumSide: Float = 0.2
    static let maximumSide: Float = 8

    // MARK: - Plan

    /// The frames and handles for a selection.
    ///
    /// **Handles appear only where resizing actually happens.** That is one
    /// resizable item: a handle drawn on a set would have to resize the whole
    /// set to be honest, which is a different operation (N persists under one
    /// undo group) and is not built. Drawing it anyway would be worse than
    /// omitting it — a direct-manipulation affordance that does nothing teaches
    /// the user the surface is broken, which is the complaint #4409 opens with.
    ///
    /// Ordered by id throughout so the same selection produces the same scene
    /// on every run: the caller's input comes from a `Set`, whose iteration
    /// order is hash order.
    static func plan(for items: [Item]) -> Plan {
        let ordered = items.sorted { $0.id < $1.id }
        guard !ordered.isEmpty else { return Plan(itemBoxes: [], setBox: nil, handles: []) }

        let boxes = ordered.map { item in
            Box(
                centerX: item.centerX,
                centerY: item.centerY,
                width: item.width + itemInset,
                height: item.height + itemInset
            )
        }

        let setBox: Box? = boxes.count > 1 ? union(boxes, expandedBy: setInset) : nil

        var handles: [Handle] = []
        if ordered.count == 1, let item = ordered.first, item.isResizable, let box = boxes.first {
            handles = Corner.allCases.map { corner in
                Handle(
                    itemId: item.id,
                    corner: corner,
                    positionX: box.centerX + corner.xSign * box.width / 2,
                    positionY: box.centerY + corner.ySign * box.height / 2
                )
            }
        }

        return Plan(itemBoxes: boxes, setBox: setBox, handles: handles)
    }

    /// The smallest box containing all of `boxes`, grown by `margin` on every side.
    static func union(_ boxes: [Box], expandedBy margin: Float) -> Box? {
        guard let first = boxes.first else { return nil }
        var minX = first.minX, maxX = first.maxX, minY = first.minY, maxY = first.maxY
        for box in boxes.dropFirst() {
            minX = min(minX, box.minX)
            maxX = max(maxX, box.maxX)
            minY = min(minY, box.minY)
            maxY = max(maxY, box.maxY)
        }
        return Box(
            centerX: (minX + maxX) / 2,
            centerY: (minY + maxY) / 2,
            width: (maxX - minX) + margin,
            height: (maxY - minY) + margin
        )
    }

    // MARK: - Resizability

    /// Which placeables offer a handle.
    ///
    /// A `.link` item is an EDGE between two cards, not a card — it has no
    /// size of its own and its endpoints decide where it is drawn, so a resize
    /// handle on one could not do anything. Everything else is resizable,
    /// including source nodes: `CanvasCardGeometry.dimensions` holds a page's
    /// true aspect and normalizes on AREA, so resizing a page card changes how
    /// much room it takes without distorting the page. That is exactly the
    /// "larger reads as more important" #4409 asks for.
    static func isResizable(_ content: CanvasContent) -> Bool {
        if case .item(let item) = content, item.kind == .link { return false }
        return true
    }

    // MARK: - Resize math

    /// The new card size for a corner drag, anchored at the OPPOSITE corner —
    /// the grabbed corner tracks the pointer and the other three stay put,
    /// which is what makes a corner drag feel like grabbing a corner.
    ///
    /// `proportional` is the DEFAULT (#4409: "proportional resize by default
    /// with a modifier to free the aspect ratio"). The freeing modifier is ⇧,
    /// chosen because ⌥ already means force-link on this surface's drags and a
    /// handle drag can never be a selection extend, so ⇧ is unambiguous here.
    ///
    /// Under `proportional` the DOMINANT axis drives: whichever of width or
    /// height the user changed proportionally more sets the scale, so a mostly
    /// vertical drag is not dead and a diagonal one does the obvious thing.
    /// The scale is clamped so BOTH sides stay inside `minimumSide ...
    /// maximumSide` — clamping each side independently would silently break the
    /// aspect the proportional mode exists to preserve.
    static func resizedSize(
        from origin: CGSize,
        corner: Corner,
        sceneDelta: SIMD2<Float>,
        proportional: Bool
    ) -> CGSize {
        let originWidth = Float(origin.width)
        let originHeight = Float(origin.height)
        guard originWidth > 0, originHeight > 0 else { return origin }

        let widthDelta = sceneDelta.x * corner.xSign
        let heightDelta = sceneDelta.y * corner.ySign

        guard proportional else {
            return CGSize(
                width: CGFloat(clampSide(originWidth + widthDelta)),
                height: CGFloat(clampSide(originHeight + heightDelta))
            )
        }

        let scaleX = (originWidth + widthDelta) / originWidth
        let scaleY = (originHeight + heightDelta) / originHeight
        let dominant = abs(scaleX - 1) >= abs(scaleY - 1) ? scaleX : scaleY
        let scale = clampScale(dominant, width: originWidth, height: originHeight)
        return CGSize(width: CGFloat(originWidth * scale), height: CGFloat(originHeight * scale))
    }

    private static func clampSide(_ side: Float) -> Float {
        min(max(side, minimumSide), maximumSide)
    }

    /// The scale range that keeps both sides in bounds. The lower bound wins
    /// over the upper when a card is already outside the range (a legacy row
    /// with a huge `w`), so the result is always a real number rather than an
    /// empty range's crash.
    private static func clampScale(_ scale: Float, width: Float, height: Float) -> Float {
        let lower = max(minimumSide / width, minimumSide / height)
        let upper = min(maximumSide / width, maximumSide / height)
        guard lower <= upper else { return lower }
        return min(max(scale, lower), upper)
    }
}
