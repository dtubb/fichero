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
}
