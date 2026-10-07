import RealityKit
import SwiftUI

// MARK: - A group's frame (#5570, `library.canvas.a-group-is-a-container-card`)

/// How the 2D canvas draws a group: a quiet translucent frame BEHIND the pages laid out inside it
/// (`CanvasGroupNesting`), with no picture of its own. Split out of the main renderer file, which
/// is at its file_length ceiling.
extension CanvasOrtho2DRenderer {
    /// The frame's colour: a light wash, so the pages inside read and the group still reads as one
    /// thing from far out.
    static var containerColor: PlatformColor { .systemGray }
    static let containerOpacity: Float = 0.3

    /// How far behind the board a card is drawn. A group's frame sits behind its pages, which sit
    /// on the board's plane with every other card, so the frame never covers a page.
    static func cardDepth(for placeable: CanvasPlaceable) -> Float {
        placeable.isContainer ? -0.02 : 0
    }

    /// The material a card is built with: the kind/tint colour, or a group's translucent frame.
    func cardMaterial(for placeable: CanvasPlaceable) -> any RealityKit.Material {
        guard placeable.isContainer else { return UnlitMaterial(color: cardColor(for: placeable)) }
        var material = UnlitMaterial(color: Self.containerColor)
        material.blending = .transparent(opacity: .init(floatLiteral: Self.containerOpacity))
        return material
    }

    /// A scene position for a card that keeps the card's own depth (a frame stays behind its
    /// pages through every move).
    func scenePosition(_ world: SIMD3<Double>, keepingDepthOf entity: Entity) -> SIMD3<Float> {
        var point = Canvas2DProjection.scenePosition(world)
        point.z = entity.position.z
        return point
    }
}
