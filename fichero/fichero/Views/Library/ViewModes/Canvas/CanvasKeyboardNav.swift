import SwiftUI

// MARK: - Canvas keyboard grammar (user, 2026-08-19/20)

/// Arrow keys move the SELECTION spatially — left/right/up/down to the
/// nearest node by board position (user, 2026-08-20: "left and right and up
/// and down would take us left right up and down in our selection") — and
/// ⌘A selects every node. One shared grammar for all three canvas surfaces,
/// so they cannot drift apart the way their click grammars once did (#4436).
/// Camera movement stays on two-finger scroll / Space-drag.
struct CanvasKeyboardNav: ViewModifier {
    /// World ids in the scene, in layout order.
    let nodeIds: [String]
    /// Board position per node id (world x/y) — the spatial neighbor metric.
    var nodePositions: [String: CGPoint] = [:]
    @Binding var selectedNodeIds: Set<String>

    func body(content: Content) -> some View {
        content
            .focusable()
            .focusEffectDisabled()
            .onKeyPress(
                keys: [.upArrow, .downArrow, .leftArrow, .rightArrow],
                phases: [.down, .repeat]
            ) { press in
                guard let target = Self.neighbor(
                    of: currentAnchor,
                    in: nodePositions.isEmpty ? [:] : nodePositions,
                    ids: nodeIds,
                    direction: press.key
                ) else { return .ignored }
                selectedNodeIds = SelectionGrammar.select(target).selection
                return .handled
            }
            .onKeyPress(.init("a"), phases: .down) { press in
                guard press.modifiers.contains(.command) else { return .ignored }
                selectedNodeIds = SelectionGrammar.selectAll(in: nodeIds).selection
                return .handled
            }
    }

    private var currentAnchor: String? {
        // A single selection is the anchor; a multi-selection steps from its
        // spatially-first member so repeated presses behave predictably.
        if selectedNodeIds.count == 1 { return selectedNodeIds.first }
        return selectedNodeIds
            .compactMap { id in nodePositions[id].map { (id, $0) } }
            .min {
                ($0.1.y, $0.1.x) < ($1.1.y, $1.1.x)
            }?.0
    }

    /// Nearest node in `direction` from `origin` — primary-axis progress
    /// required, ties broken by total distance. No origin/empty board →
    /// the first node (arrow into an unselected canvas lands somewhere).
    static func neighbor(
        of origin: String?,
        in positions: [String: CGPoint],
        ids: [String],
        direction: KeyEquivalent
    ) -> String? {
        guard let origin, let from = positions[origin] else { return ids.first }
        var best: (id: String, score: CGFloat)?
        for (id, p) in positions where id != origin {
            let dx = p.x - from.x, dy = p.y - from.y
            let (forward, lateral): (CGFloat, CGFloat)
            switch direction {
            case .leftArrow: (forward, lateral) = (-dx, abs(dy))
            case .rightArrow: (forward, lateral) = (dx, abs(dy))
            case .upArrow: (forward, lateral) = (-dy, abs(dx))
            case .downArrow: (forward, lateral) = (dy, abs(dx))
            default: return nil
            }
            guard forward > 0.001 else { continue }
            // Strongly prefer staying in line; forward distance breaks ties.
            let score = lateral * 4 + forward
            if best == nil || score < best!.score { best = (id, score) }
        }
        return best?.id
    }
}
