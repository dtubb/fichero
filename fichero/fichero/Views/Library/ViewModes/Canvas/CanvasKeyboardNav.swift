import SwiftUI

// MARK: - Canvas keyboard grammar (user, 2026-08-19)

/// Arrow keys pan the camera; ⌘A selects every node — the ONE keyboard
/// grammar for all three canvas surfaces (2D ortho, 3D space, legacy 3D),
/// so the three views cannot drift apart the way their click grammars once
/// did (#4436). The host supplies its own camera-pan primitive; selection
/// goes through `SelectionGrammar.selectAll` like every other select-all.
struct CanvasKeyboardNav: ViewModifier {
    /// World ids in the scene, in layout order.
    let nodeIds: [String]
    @Binding var selectedNodeIds: Set<String>
    /// The host's camera pan, in view points (same delta shape as scroll).
    let pan: (CGSize) -> Void

    /// Points per arrow press — held keys repeat via the `.repeat` phase.
    private static let step: CGFloat = 48

    func body(content: Content) -> some View {
        content
            .focusable()
            .focusEffectDisabled()
            .onKeyPress(
                keys: [.upArrow, .downArrow, .leftArrow, .rightArrow],
                phases: [.down, .repeat]
            ) { press in
                switch press.key {
                case .upArrow: pan(CGSize(width: 0, height: Self.step))
                case .downArrow: pan(CGSize(width: 0, height: -Self.step))
                case .leftArrow: pan(CGSize(width: Self.step, height: 0))
                case .rightArrow: pan(CGSize(width: -Self.step, height: 0))
                default: return .ignored
                }
                return .handled
            }
            .onKeyPress(.init("a"), phases: .down) { press in
                guard press.modifiers.contains(.command) else { return .ignored }
                selectedNodeIds = SelectionGrammar.selectAll(in: nodeIds).selection
                return .handled
            }
    }
}
