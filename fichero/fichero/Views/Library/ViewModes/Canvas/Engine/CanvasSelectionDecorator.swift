import CoreGraphics
import Foundation
import RealityKit
import simd

// MARK: - The entities that draw a selection (#4409)

/// Owns the RealityKit entities that show WHICH placeables are selected, for
/// both canvas renderers.
///
/// A separate object rather than code inside each renderer, for two reasons.
///
/// The first is the bug. Selection used to be drawn by `makeCard`, which meant
/// a selection change had to REBUILD the card — `reskinCard` destroyed the
/// `ModelEntity` and made a new one whose material is the flat base colour
/// until an async thumbnail reload restored the page texture. A source node's
/// base colour is `.systemBlue`; that is #4409's blue flash, and it fired on
/// the card gained AND the card lost. With the decoration owned here the cards
/// are never touched by a selection change, so the flash is impossible rather
/// than suppressed by an overlay.
///
/// The second is that there were two near-identical copies of the drawing
/// code, one per renderer — which is how the 2D and 3D canvases would drift
/// apart on what "selected" looks like, the same way the six selection
/// implementations of #4436 drifted on what "selected" MEANS.
@MainActor
final class CanvasSelectionDecorator {

    /// Add this to the scene once; its contents are managed here.
    let root = Entity()

    /// Whether corner resize handles are drawn. The 2D canvas says yes; the 3D
    /// scene says no, because an axis-handle gizmo in a perspective scene is
    /// its own design problem and a handle that cannot resize is worse than no
    /// handle — the affordance-that-does-nothing #4409 opens with.
    private let showsHandles: Bool
    private let accentColor: PlatformColor

    private let frameThickness: Float
    private let setFrameThickness: Float
    /// How far in front of a card its frame sits. A frame drawn behind the
    /// thing it frames is not a frame — which is what the old solid accent
    /// plane was.
    private let frameLift: Float
    private let handleLift: Float
    private let handleSide: Float

    init(
        showsHandles: Bool,
        accentColor: PlatformColor,
        frameThickness: Float = 0.022,
        setFrameThickness: Float = 0.014,
        frameLift: Float = 0.02,
        handleLift: Float = 0.03,
        handleSide: Float = 0.09
    ) {
        self.showsHandles = showsHandles
        self.accentColor = accentColor
        self.frameThickness = frameThickness
        self.setFrameThickness = setFrameThickness
        self.frameLift = frameLift
        self.handleLift = handleLift
        self.handleSide = handleSide
    }

    /// Redraw everything from the current selection geometry.
    ///
    /// Rebuilding this root wholesale is NOT the pattern the
    /// no-wholesale-re-render rule forbids. That rule protects CONTENT —
    /// entities carrying textures, collision and load state, whose rebuild
    /// costs a fetch and shows a flash. Decoration carries none of that: it is
    /// a pure function of the selection and where the cards are, so there is no
    /// in-place state to preserve, and keeping frames alive across a change
    /// would mean a second registry that can disagree with the cards about
    /// where they are — which is the class of bug this issue is.
    ///
    /// `depth` supplies each item's plane offset (the 3D renderer's cards sit
    /// at different z; the 2D renderer's are all on one plane).
    func update(items: [CanvasSelectionFrame.Item], depth: (String) -> Float = { _ in 0 }) {
        root.children.forEach { $0.removeFromParent() }
        // Sorted to match `plan`'s own ordering, so `itemBoxes[i]` and
        // `ordered[i]` are the same placeable and each frame gets ITS card's
        // depth rather than a neighbour's.
        let ordered = items.sorted { $0.id < $1.id }
        let plan = CanvasSelectionFrame.plan(for: ordered)

        for (index, box) in plan.itemBoxes.enumerated() {
            let itemDepth = index < ordered.count ? depth(ordered[index].id) : 0
            root.addChild(makeFrame(box, depth: itemDepth, thickness: frameThickness, alpha: 1))
        }

        if let setBox = plan.setBox {
            // Thinner and dimmer than the item frames: it says "these belong
            // together" without competing with the frames that say which
            // things are selected.
            let depths = ordered.map { depth($0.id) }
            let meanDepth = depths.isEmpty ? 0 : depths.reduce(0, +) / Float(depths.count)
            root.addChild(makeFrame(setBox, depth: meanDepth, thickness: setFrameThickness, alpha: 0.55))
        }

        guard showsHandles else { return }
        for handle in plan.handles {
            root.addChild(makeHandle(handle, depth: depth(handle.itemId)))
        }
    }

    // MARK: - Entities

    /// A STROKED rectangle — four thin bars.
    ///
    /// The decoration this replaces was a solid accent plane drawn behind the
    /// card, which reads as a coloured halo rather than a selection frame and
    /// which, at the accent default, is literally blue. Finder draws a frame;
    /// so does this.
    private func makeFrame(
        _ box: CanvasSelectionFrame.Box, depth: Float, thickness: Float, alpha: CGFloat
    ) -> Entity {
        let container = Entity()
        container.name = CanvasSelectionFrame.decorationNamePrefix + "frame"
        let color = accentColor.withAlphaComponent(alpha)
        let horizontal = MeshResource.generatePlane(width: box.width, height: thickness)
        let vertical = MeshResource.generatePlane(width: thickness, height: box.height)
        func addBar(_ mesh: MeshResource, offsetX: Float, offsetY: Float) {
            let entity = ModelEntity(mesh: mesh, materials: [UnlitMaterial(color: color)])
            entity.position = SIMD3<Float>(box.centerX + offsetX, box.centerY + offsetY, depth + frameLift)
            container.addChild(entity)
        }
        addBar(horizontal, offsetX: 0, offsetY: box.height / 2)
        addBar(horizontal, offsetX: 0, offsetY: -box.height / 2)
        addBar(vertical, offsetX: -box.width / 2, offsetY: 0)
        addBar(vertical, offsetX: box.width / 2, offsetY: 0)
        return container
    }

    /// A corner grab handle — the ONE decoration that is an input target. The
    /// host's resize drag finds it by name.
    private func makeHandle(_ handle: CanvasSelectionFrame.Handle, depth: Float) -> ModelEntity {
        let mesh = MeshResource.generatePlane(
            width: handleSide, height: handleSide, cornerRadius: handleSide * 0.25
        )
        let entity = ModelEntity(mesh: mesh, materials: [UnlitMaterial(color: accentColor)])
        entity.name = CanvasSelectionFrame.handleName(corner: handle.corner, itemId: handle.itemId)
        entity.position = SIMD3<Float>(handle.positionX, handle.positionY, depth + handleLift)
        entity.components.set(InputTargetComponent())
        entity.components.set(CollisionComponent(
            shapes: [.generateBox(size: SIMD3<Float>(handleSide, handleSide, 0.02))]
        ))
        return entity
    }
}
