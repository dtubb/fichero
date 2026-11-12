import Foundation

/// ⌘-scroll zoom on the boards (#4601; owner: with ⌘ and a Magic Mouse the zoom "goes too fast, then stops, and you
/// can't zoom out"). It multiplied the scale by `1 + delta × 0.005` per event: a Magic Mouse flick sends deltas past
/// ±200 with momentum, so the factor reached zero or below and the scale snapped to its limit. The factor is now
/// exponential -- always positive, the same speed in as out -- with each event's delta capped, and the momentum after
/// the fingers lift does not zoom (the zoom follows the fingers, as the pan's glide does not need to).
enum CanvasScrollZoom {
    /// How much one point of scroll zooms.
    static let rate = 0.005
    /// The most one event may zoom by, in scroll points: a flick's single event never jumps the board.
    static let deltaCap = 40.0

    /// The scale factor for one scroll event's vertical delta; positive delta grows the factor.
    static func factor(delta: Double) -> Double {
        exp(min(max(delta, -deltaCap), deltaCap) * rate)
    }

    /// Momentum events (the glide after the fingers lift) do not zoom.
    static func zooms(isMomentum: Bool) -> Bool { !isMomentum }
}
