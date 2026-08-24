#if os(macOS)
import AppKit

// MARK: - Brief transition on preview image swaps (Daniel, 2026-08-21:
// "an animation would be good. right now it just changes")

/// A ONE-SHOT hint describing how the next image swap should animate,
/// parked by whoever initiates the change (sibling step, rendition flip)
/// and consumed by the AppKit swap site. A swap with no hint (first load,
/// high-res upgrade, live edit echo) stays instant — animating those would
/// make every reload look like navigation.
///
/// Public CATransition types only (push/fade). The undocumented "pageCurl"
/// string works on macOS but is unsupported API — not worth the App Store
/// gamble for one effect (Daniel: "maybe just a brief animation is better").
@MainActor
enum PreviewSwapAnimation {
    enum Kind {
        /// Page step: horizontal push, matching the swipe's direction.
        case pageStep(forward: Bool)
        /// Rendition flip: vertical push — the up/down axis made visible.
        case renditionFlip(forward: Bool)
    }

    private static var pending: Kind?

    static func park(_ kind: Kind) { pending = kind }

    /// Run-and-clear on the view whose content is about to swap. Slide only
    /// (Daniel, 2026-08-21: "get rid of the curl stuff. the slide is fine") —
    /// the private pageCurl filter curled the whole surface against a black
    /// backing and was retired the same afternoon it landed.
    static func runPending(on view: NSView) {
        guard let kind = pending else { return }
        pending = nil
        let transition = CATransition()
        transition.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        transition.duration = 0.22
        transition.type = .push
        switch kind {
        case .pageStep(let forward):
            transition.subtype = forward ? .fromRight : .fromLeft
        case .renditionFlip(let forward):
            // Empirical (Daniel, 2026-08-22: "the animation is the wrong
            // direction for flipping up and down") — the y-up reasoning was
            // backwards on this layer: forward = next rendition comes from
            // the TOP of the screen sense below.
            transition.subtype = forward ? .fromBottom : .fromTop
        }
        view.wantsLayer = true
        view.layer?.add(transition, forKey: "previewSwap")
    }
}
#endif
