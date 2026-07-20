import SwiftUI

extension ImmersiveReaderView {
    var siblingIndex: Int? {
        siblings.firstIndex { $0.id == document.id }
    }

    func navigate(by offset: Int) {
        guard let index = siblingIndex else { return }
        let target = index + offset
        guard siblings.indices.contains(target) else { return }
        // Capture the turn direction BEFORE the parent swaps `document` so the
        // transition on the next render curls the right way (#2485).
        turnForward = offset > 0
        onNavigate?(siblings[target])
        revealControls()
    }

    /// The page-turn transition for a prev/next swap. Off ⇒ no visual transition
    /// (fast mode); reduce-motion ⇒ a plain crossfade; otherwise a 3D page-turn
    /// hinged on the spine edge (leading when going forward). (#2485)
    var pageTurnTransition: AnyTransition {
        guard pageTurnAnimated else { return .identity }
        guard !reduceMotion else { return .opacity }
        return .pageTurn(forward: turnForward)
    }

    /// Animation timing paired with `pageTurnTransition`. Nil ⇒ instant swap
    /// (fast mode); shorter under reduce-motion.
    var pageTurnAnimation: Animation? {
        guard pageTurnAnimated else { return nil }
        return .easeInOut(duration: reduceMotion ? 0.2 : 0.45)
    }
}
