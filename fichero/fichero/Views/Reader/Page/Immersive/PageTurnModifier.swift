import SwiftUI

// MARK: - Page-turn transition (#2485)

/// A book-style page-turn: the page rotates in 3D around its spine edge with a
/// little perspective, so paging reads like turning a page rather than a hard
/// cut. Reusable across the reading surfaces (the folder-image reader here; the
/// PDF/Page-tab reader can adopt it once the 4-tab restructure lands and owns a
/// single page renderer). Pure SwiftUI — no Metal / CATransition / parallel
/// renderer — so it survives the restructure and needs no platform fork.
struct PageTurnModifier: ViewModifier {
    /// Rotation at the "away" end of the turn, in degrees. 0 is flat/on-screen.
    let angle: Double
    /// The hinge the page rotates around — the spine edge.
    let anchor: UnitPoint

    func body(content: Content) -> some View {
        content
            .rotation3DEffect(
                .degrees(angle),
                axis: (x: 0, y: 1, z: 0),
                anchor: anchor,
                perspective: 0.5
            )
            // Fade the swinging page so the incoming/outgoing pages cross
            // cleanly instead of both rendering opaque mid-turn.
            .opacity(angle == 0 ? 1 : 0)
    }
}

extension AnyTransition {
    /// A page-turn keyed to direction: forward hinges on the leading (spine)
    /// edge with the incoming page swinging in from the right and the outgoing
    /// page flipping left; backward mirrors it on the trailing edge. (#2485)
    static func pageTurn(forward: Bool) -> AnyTransition {
        let hinge: UnitPoint = forward ? .leading : .trailing
        let insertion = AnyTransition.modifier(
            active: PageTurnModifier(angle: forward ? -90 : 90, anchor: hinge),
            identity: PageTurnModifier(angle: 0, anchor: hinge)
        )
        let removal = AnyTransition.modifier(
            active: PageTurnModifier(angle: forward ? 90 : -90, anchor: hinge),
            identity: PageTurnModifier(angle: 0, anchor: hinge)
        )
        return .asymmetric(insertion: insertion, removal: removal)
    }
}
