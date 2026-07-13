import SwiftUI

/// ★ EVERY FRAME PERFECT (#3619): one place for transition timing so animations
/// feel intentional and consistent instead of ad-hoc per view. Great start + end
/// frames aren't enough — standardizing the curve keeps the frames BETWEEN smooth
/// and matched across surfaces.
///
/// Two tiers, both pure SwiftUI `Animation` values (no new framework),
/// cross-platform:
///
/// - ``snappy`` — chrome & selection movement (tab switch, pane/sidebar reveal,
///   inspector present). A quick, minimal-overshoot spring so a control feels
///   responsive without bouncing.
/// - ``crossfade`` — content opacity swaps (skeleton → image #3616, edit-mode
///   overtake of the Preview #3593, content replace). A calm, bounce-free curve
///   so pixels dissolve rather than jump-cut.
enum FrameAnimation {
    /// Shared base duration. Keep any manual `.transition`/`withAnimation` timing
    /// in step with this rather than inventing a per-view number.
    static let duration: Double = 0.25

    /// Chrome & selection movement — tabs, pane/sidebar reveal, present/dismiss.
    static let snappy: Animation = .snappy(duration: duration)

    /// Content opacity cross-fades — skeleton → image, mode overtake, replace.
    static let crossfade: Animation = .easeInOut(duration: duration)
}
