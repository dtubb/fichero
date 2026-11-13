import CoreGraphics

/// A horizontal swipe on a fitted page turns to the previous or next one, as in Photos (#6559). A swipe on a zoomed-in
/// page pans it instead; so does a mostly vertical or a short drag.
enum PageSwipe {
    /// How far a finger must travel sideways, or be flung, before the swipe turns the page.
    static let minimumTravel: CGFloat = 60

    /// -1 for the previous page (a swipe to the right), +1 for the next (a swipe to the left), nil for no turn.
    /// `predictedEnd` is the gesture's predicted end translation, so a short, fast flick still turns the page.
    static func step(translation: CGSize, predictedEnd: CGSize, isZoomedIn: Bool) -> Int? {
        guard !isZoomedIn else { return nil }
        let travel = abs(predictedEnd.width) > abs(translation.width) ? predictedEnd.width : translation.width
        guard abs(travel) >= minimumTravel, abs(translation.width) > abs(translation.height) * 1.5 else { return nil }
        return travel < 0 ? 1 : -1
    }

    /// Whether the page is zoomed in past its fitted size (with a small allowance for rounding).
    static func isZoomedIn(scale: CGFloat, fitScale: CGFloat?) -> Bool {
        guard let fitScale, fitScale > 0 else { return false }
        return scale > fitScale * 1.05
    }

    /// Where a drag released at `velocity` (points per second) would come to rest, for `step`'s `predictedEnd`: UIKit's
    /// pan recognizer gives a velocity, not SwiftUI's predicted end.
    static func predictedEnd(translation: CGSize, velocity: CGPoint) -> CGSize {
        CGSize(width: translation.width + velocity.x * 0.2, height: translation.height + velocity.y * 0.2)
    }

    /// Whether a drag starting at `velocity` is the page swipe's to take: sideways, on a fitted page. A vertical drag
    /// is left to whatever else wants it (the full-screen view's swipe down to close).
    static func claimsDrag(velocity: CGPoint, isZoomedIn: Bool) -> Bool {
        !isZoomedIn && abs(velocity.x) > abs(velocity.y)
    }

    /// Where a page that isn't zoomed in rests: centred in the view along both axes. One formula for both cases: a
    /// page smaller than the view sits inside its centring inset (a negative offset), and one up to the zoomed-in
    /// threshold larger is split evenly. A new page must start here, not at the last page's scroll position.
    static func restingOffset(scaledContent: CGSize, viewSize: CGSize) -> CGPoint {
        CGPoint(x: (scaledContent.width - viewSize.width) / 2, y: (scaledContent.height - viewSize.height) / 2)
    }

    /// Whether the page asked for (by a swipe, the pane's arrows or a key) is not the one drawn yet, so the spinner
    /// shows over the old one until it arrives.
    static func isLoadingPage(requested: String?, shown: String?) -> Bool {
        guard let requested, let shown else { return false }
        return requested != shown
    }

    /// The smallest zoom a pinch or Zoom Out may reach: the fitted size, so a pinch out springs back to the whole page
    /// instead of shrinking it to a speck. `minScale` until the page can be measured.
    static func minimumZoom(fitScale: CGFloat?, minScale: CGFloat) -> CGFloat {
        guard let fitScale, fitScale > 0 else { return minScale }
        return max(minScale, fitScale)
    }
}
