import Foundation
import RealityKit

// MARK: - Painting emphasis onto live cards (§25.4 step 2)

/// Turns a `CanvasEmphasis` into what you actually see, for BOTH renderers.
///
/// Shared for the same reason `CanvasSelectionDecorator` is: two near-identical
/// copies is how 2D and 3D drift on what a word MEANS, and "highlighted" is a
/// word the two canvases must not disagree about.
///
/// It works by opacity, deliberately. The alternative — swapping in a tinted
/// material — cannot be done without the card's `TextureResource` in hand,
/// which would mean rebuilding the card; and rebuilding a card drops its loaded
/// page texture and flashes the flat base colour. That is #4409, and a live
/// search would fire it on every keystroke across the whole board. An
/// `OpacityComponent` is set on the entity and touches neither mesh nor
/// material, so a card is never rebuilt and the flash stays impossible rather
/// than suppressed.
@MainActor
enum CanvasEmphasisPainter {
    /// Paint one card. Full strength REMOVES the component rather than setting
    /// opacity 1, so a neutral board carries no per-entity state at all.
    static func apply(_ emphasis: CanvasEmphasis, to entity: Entity, id: String) {
        let strength = emphasis.strength(for: id)
        if strength >= 1 {
            entity.components.remove(OpacityComponent.self)
        } else {
            entity.components.set(OpacityComponent(opacity: Float(strength)))
        }
    }

    /// Paint every card under `root`. Entities are named by placeable id (both
    /// renderers do this already — it is how `findEntity(named:)` moves a card),
    /// so the id comes off the entity rather than needing the scene state.
    static func apply(_ emphasis: CanvasEmphasis, to root: Entity) {
        for child in root.children {
            apply(emphasis, to: child, id: child.name)
        }
    }
}
