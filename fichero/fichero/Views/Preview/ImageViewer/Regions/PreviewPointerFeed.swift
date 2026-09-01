import CoreGraphics
import Foundation

/// One pointer event over the preview image, in NORMALIZED image coordinates
/// (0…1, top-left origin — the same space the OCR boxes and marquees use).
enum PreviewPointerPhase: Sendable {
    case pressed
    case dragged
    case released
}

struct PreviewPointerEvent: Sendable {
    let phase: PreviewPointerPhase
    /// Normalized image point; may fall outside 0…1 when the press lands in
    /// the letterbox around the image.
    let point: CGPoint
    let shift: Bool
    let clickCount: Int
}

/// The seam through which AppKit hands the region layer its clicks and
/// drags (2026-09-01). The SwiftUI region layer used to own a full-frame
/// `contentShape` + gestures over the image; on macOS that made the hosting
/// view claim hit-testing over the NSScrollView beneath, and two-finger
/// pan, pinch, and the page/rendition swipes never reached it (the
/// swipe-triage log stayed empty through every gesture Daniel made). Now the
/// image view forwards its mouse events here, the SwiftUI layer stays out of
/// hit-testing entirely, and the scroll view keeps every trackpad gesture.
@MainActor
@Observable
final class PreviewPointerFeed {
    private(set) var latest: PreviewPointerEvent?
    /// Monotonic so an identical event (same point, same phase) still
    /// registers as a change.
    private(set) var sequence: Int = 0

    func publish(_ event: PreviewPointerEvent) {
        latest = event
        sequence &+= 1
    }
}
