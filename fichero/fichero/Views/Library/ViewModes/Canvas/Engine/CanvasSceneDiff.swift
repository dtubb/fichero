import CoreGraphics
import Foundation
import simd

// MARK: - Granular reconcile model (#3103)

/// One minimal change a renderer applies to its live scene. Generalizes the 3D
/// `reconcileCanvasItems` (find-or-create, remove-missing, reposition-in-place)
/// to ALL placeables. Renderers apply ONLY these ops — never rebuild the scene
/// (no-wholesale-re-render rule; also retires the 3D `layoutRevision`
/// bump-everything idiom).
enum CanvasSceneOp: Equatable {
    case insert(CanvasPlaceable)
    case move(id: String, position: SIMD3<Double>)
    case resize(id: String, size: CGSize)
    case updateContent(id: String)
    case remove(id: String)
    /// Edges are rebuilt wholesale — cheap and few, matching both current impls.
    case setEdges([CanvasEdge])
    case setSelection(Set<String>)
    /// WHICH cards matter now. Like `.setSelection`, it touches no card's
    /// geometry — and it must never turn into a rebuild, or a live search would
    /// destroy and re-create 2,228 textured cards per keystroke (#4409).
    case setEmphasis(CanvasEmphasis)
    /// WHAT each card is, in colour. Re-encodes in place like `.setEmphasis`,
    /// and moves nothing (§13.2).
    case setTint(CanvasTint)
}

enum CanvasSceneDiff {
    /// The minimal op list taking a renderer from `old` to `new`. Equal states
    /// yield `[]`. Untouched placeables produce no op (identity stable).
    static func compute(from old: CanvasSceneState, to new: CanvasSceneState) -> [CanvasSceneOp] {
        var ops: [CanvasSceneOp] = []

        let oldById = Dictionary(old.placeables.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let newById = Dictionary(new.placeables.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })

        // Removals first so a renderer frees entities before inserts reuse slots.
        for placeable in old.placeables where newById[placeable.id] == nil {
            ops.append(.remove(id: placeable.id))
        }

        // Inserts + in-place changes, in new-state order (stable insert order).
        for placeable in new.placeables {
            guard let previous = oldById[placeable.id] else {
                ops.append(.insert(placeable))
                continue
            }
            if previous.position != placeable.position {
                ops.append(.move(id: placeable.id, position: placeable.position))
            }
            if previous.size != placeable.size, let size = placeable.size {
                ops.append(.resize(id: placeable.id, size: size))
            }
            if previous.content.contentSignature != placeable.content.contentSignature {
                ops.append(.updateContent(id: placeable.id))
            }
        }

        if old.edges != new.edges {
            ops.append(.setEdges(new.edges))
        }
        if old.selection != new.selection {
            ops.append(.setSelection(new.selection))
        }
        if old.emphasis != new.emphasis {
            ops.append(.setEmphasis(new.emphasis))
        }
        if old.tint != new.tint {
            ops.append(.setTint(new.tint))
        }

        return ops
    }
}
