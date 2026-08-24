import RealityKit
import simd
import SwiftUI

// MARK: - Op application (split from CanvasOrtho2DRenderer for file_length)

/// The granular reconcile path: every scene change arrives here as one op and
/// is applied IN PLACE. Never a rebuild of the scene, and — since #4409 — never
/// a rebuild of a card for anything that is only decoration.
extension CanvasOrtho2DRenderer {
    /// Apply ONE scene op. Internal, not private: `apply` lives in the main
    /// file and Swift's `private` is FILE-scoped.
    func applyOne(_ operation: CanvasSceneOp) {
        switch operation {
        case .insert(let placeable):
            placeablesById[placeable.id] = placeable
            let card = makeCard(placeable)
            CanvasEmphasisPainter.apply(emphasis, to: card, id: placeable.id)
            placeablesRoot.addChild(card)
        case .move(let id, let position):
            applyMove(id: id, to: position)
        case .resize(let id, let size):
            placeablesById[id]?.size = size
            // Mesh + collision IN PLACE, keeping the materials — a `reskinCard`
            // here would drop the loaded page texture and flash the base colour
            // for exactly the same reason selection used to (#4409).
            resizeCardInPlace(id)
        case .updateContent(let id):
            reskinCard(id)
        case .remove(let id):
            placeablesById[id] = nil
            texturedIds.remove(id)
            placeablesRoot.findEntity(named: id)?.removeFromParent()
        case .setEdges(let edges):
            rebuildEdges(edges)
        case .setSelection(let newSelection):
            // NOTHING happens to the cards. This used to `reskinCard` every id
            // in the symmetric difference — destroying and rebuilding a
            // textured card to add or remove a decoration — which is #4409's
            // blue flash and the no-wholesale-re-render rule broken at card
            // granularity. `refreshSelectionDecoration` (called once by
            // `apply`) redraws the frames instead.
            selection = newSelection
        case .setTint(let newTint):
            // Colour NEVER moves a card and never rebuilds one: the painter
            // swaps the material colour of cards that carry no page texture,
            // and skips the ones that do (§13.2 — re-encode, don't re-arrange).
            tint = newTint
            repaintTint()
        case .setEmphasis(let newEmphasis):
            // Also nothing to the cards themselves: an OpacityComponent, so a
            // live search never rebuilds a textured card (#4409, this channel).
            emphasis = newEmphasis
            CanvasEmphasisPainter.apply(newEmphasis, to: placeablesRoot)
        }
    }

    /// Repaint every card for the current colouring. Cards carrying a page
    /// image are skipped by the painter, so the page stays readable.
    private func repaintTint() {
        for child in placeablesRoot.children {
            guard let card = child as? ModelEntity, let placeable = placeablesById[card.name] else { continue }
            CanvasTintPainter.apply(
                tint, to: card, id: card.name,
                fallback: baseColor(for: placeable.content), isTextured: isTextured(card.name)
            )
        }
    }

    /// Slide ONE card to its new slot.
    ///
    /// Don't fight a local drag (#3084): a store echo for the id being dragged
    /// is skipped. Every other move ANIMATES, so a re-arrange, a cross-window
    /// move or an agent's edit glides rather than jumps (R10).
    private func applyMove(id: String, to position: SIMD3<Double>) {
        guard isDragSuppressed?(id) != true else { return }
        placeablesById[id]?.position = position
        guard let entity = placeablesRoot.findEntity(named: id) else { return }
        var transform = entity.transform
        transform.translation = Canvas2DProjection.scenePosition(position)
        entity.move(to: transform, relativeTo: entity.parent, duration: moveDuration)
    }
}
