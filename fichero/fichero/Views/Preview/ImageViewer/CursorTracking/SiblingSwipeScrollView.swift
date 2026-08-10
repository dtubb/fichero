import SwiftUI

#if canImport(AppKit)

// MARK: - Swipe left/right = previous/next library item (Daniel, 2026-08-10)

extension Notification.Name {
    /// Posted by the image preview when a horizontal two-finger swipe should
    /// step to a sibling document. `object` is `+1` (next) or `-1` (previous).
    static let previewSiblingSwipe = Notification.Name("previewSiblingSwipe")
}

/// The image preview's scroll view, with Preview.app swipe grammar:
/// left/right two-finger swipes step between library siblings; up/down (and
/// every gesture while the image overflows horizontally) keeps its native
/// meaning on the CURRENT image. Native panning is untouched — super always
/// runs; navigation only engages when the scaled image cannot pan
/// horizontally, so a zoomed-in pan can never mis-trigger a page change.
final class SiblingSwipeScrollView: NSScrollView {
    private var accumulatedX: CGFloat = 0
    private var horizontalIntent = false
    private static let threshold: CGFloat = 60

    override func scrollWheel(with event: NSEvent) {
        super.scrollWheel(with: event)
        guard let doc = documentView else { return }
        let scaledWidth = doc.frame.width * magnification
        let canPanHorizontally = scaledWidth > contentSize.width + 0.5
        switch event.phase {
        case .began:
            accumulatedX = 0
            horizontalIntent = abs(event.scrollingDeltaX) > abs(event.scrollingDeltaY)
        case .changed:
            accumulatedX += event.scrollingDeltaX
        case .ended:
            if horizontalIntent, !canPanHorizontally, abs(accumulatedX) > Self.threshold {
                // Natural scrolling: fingers left → negative deltaX → NEXT,
                // matching Preview.app's page grammar.
                NotificationCenter.default.post(
                    name: .previewSiblingSwipe,
                    object: accumulatedX < 0 ? 1 : -1
                )
            }
            accumulatedX = 0
            horizontalIntent = false
        default:
            break
        }
    }
}

#endif
