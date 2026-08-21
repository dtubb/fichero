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

        var isRenditionFlip: Bool {
            if case .renditionFlip = self { return true }
            return false
        }
    }

    private static var pending: Kind?

    static func park(_ kind: Kind) { pending = kind }

    /// User-facing style (Settings ▸ General ▸ Display). "curl" rides the
    /// undocumented-but-long-lived "pageCurl"/"pageUnCurl" CATransition
    /// strings — Daniel's ruling (2026-08-21, Bookends precedent): an
    /// OPTION, slide the default. If an OS update ever kills the strings,
    /// Core Animation ignores unknown types and the swap is simply instant —
    /// degraded, never broken.
    static let styleKey = "preview.pageTurnStyle"

    private static var curlEnabled: Bool {
        UserDefaults.standard.string(forKey: styleKey) == "curl"
    }

    /// Run-and-clear on the view whose content is about to swap.
    static func runPending(on view: NSView) {
        guard let kind = pending else { return }
        pending = nil
        let transition = CATransition()
        transition.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        let forward: Bool
        switch kind {
        case .pageStep(let f): forward = f
        case .renditionFlip(let f): forward = f
        }
        if curlEnabled {
            transition.duration = 0.35
            transition.type = CATransitionType(rawValue: forward ? "pageCurl" : "pageUnCurl")
            // Un-curl peels from the SAME corner the curl lifted toward —
            // mirroring the corner made "back" read as another forward curl
            // (Daniel, 2026-08-21: "when one goes backwards, curl should be
            // reversed").
            transition.subtype = (kind.isRenditionFlip) ? .fromTop : .fromRight
        } else {
            transition.duration = 0.22
            transition.type = .push
            switch kind {
            case .pageStep(let forward):
                transition.subtype = forward ? .fromRight : .fromLeft
            case .renditionFlip(let forward):
                // AppKit layers are y-up: .fromTop pushes content in from the
                // BOTTOM of the screen. Forward (next rendition, fingers up)
                // reads as the new image rising from below.
                transition.subtype = forward ? .fromTop : .fromBottom
            }
        }
        view.wantsLayer = true
        view.layer?.add(transition, forKey: "previewSwap")
    }
}
#endif
