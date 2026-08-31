import OSLog
import SwiftUI

extension Notification.Name {
    /// Posted by the image preview when a horizontal two-finger swipe should
    /// step to a sibling document. `object` is `+1` (next) or `-1` (previous).
    static let previewSiblingSwipe = Notification.Name("previewSiblingSwipe")
    /// The vertical twin (Daniel, 2026-08-21: "the way we want to change
    /// between renditions is swiping up and down"). `object` is `+1`/`-1`.
    static let previewRenditionSwipe = Notification.Name("previewRenditionSwipe")
}

#if canImport(AppKit)

// MARK: - Swipe left/right = previous/next library item (Daniel, 2026-08-10)

/// The image preview's scroll view, with Preview.app swipe grammar:
/// left/right two-finger swipes step between library siblings; up/down (and
/// every gesture while the image overflows horizontally) keeps its native
/// meaning on the CURRENT image. Native panning is untouched — super always
/// runs; navigation only engages when the scaled image cannot pan
/// horizontally, so a zoomed-in pan can never mis-trigger a page change.
final class SiblingSwipeScrollView: NSScrollView {
    private var accumulatedX: CGFloat = 0
    private var accumulatedY: CGFloat = 0
    private var firedThisGesture = false
    private static let threshold: CGFloat = 60
    /// Entry ladder (2026-08-23): at the REGION rung the crop is fully
    /// visible but the page around it still pans, so pan-first would swallow
    /// the zoom-out swipe. When set, vertical swipes NAVIGATE regardless of
    /// pannability (and vertical panning yields); horizontal keeps the
    /// pan-first sibling grammar.
    var verticalSwipeAlwaysNavigates = false

    override func scrollWheel(with event: NSEvent) {
        guard let doc = documentView else {
            super.scrollWheel(with: event)
            return
        }
        let scaledWidth = doc.frame.width * magnification
        let scaledHeight = doc.frame.height * magnification
        let canPanHorizontally = scaledWidth > contentSize.width + 0.5
        let canPanVertically = scaledHeight > contentSize.height + 0.5
        // Gesture triage (Daniel, 2026-08-31: swipes still dead in the wild).
        // One line per gesture START in Console: filter `swipe-triage`.
        logSwipeTriage(phase: event.phase, doc: doc)
        // A fitted image has nowhere to scroll: swallowing the event kills
        // the elastic bounce that made two-finger navigation feel like the
        // page was jumping around (Daniel, 2026-08-21: "why does 2 fingers
        // move anything if the entire image is visible?"). The gesture is
        // pure navigation in that state; native panning returns the moment
        // either axis actually overflows.
        // A vertical-leaning event in ladder mode belongs to the ladder, not
        // the pan — passing it to super would scroll the page out from under
        // the step.
        let verticalLeaning = abs(event.scrollingDeltaY) >= abs(event.scrollingDeltaX)
        let ladderOwnsThisEvent = verticalSwipeAlwaysNavigates && verticalLeaning
        if (canPanHorizontally || canPanVertically) && !ladderOwnsThisEvent {
            super.scrollWheel(with: event)
        }
        // Flaky-swipe fix (Daniel, 2026-08-21: "doesn't always let you swipe
        // up or down"). Two causes, both timing:
        //   * intent was classified at .began from the FIRST event's deltas,
        //     which are often (0, 0) — a coin-flip start misrouted the axis;
        //   * a quick FLICK delivers most of its distance as MOMENTUM events,
        //     which were never accumulated — so slow deliberate drags worked
        //     and fast natural ones under-counted the 60pt threshold.
        // Now the axis is read from the totals at evaluation time, momentum
        // keeps accumulating, and the swipe fires at whichever end (gesture
        // or momentum) first crosses the threshold — once per gesture.
        if event.phase == .began {
            accumulatedX = 0
            accumulatedY = 0
            firedThisGesture = false
        }
        if event.phase == .changed || event.momentumPhase == .changed {
            accumulatedX += event.scrollingDeltaX
            accumulatedY += event.scrollingDeltaY
        }
        if event.phase == .ended || event.momentumPhase == .ended, !firedThisGesture {
            let horizontalIntent = abs(accumulatedX) > abs(accumulatedY)
            if horizontalIntent, !canPanHorizontally, abs(accumulatedX) > Self.threshold {
                // Natural scrolling: fingers left → negative deltaX → NEXT,
                // matching Preview.app's page grammar.
                firedThisGesture = true
                NotificationCenter.default.post(
                    name: .previewSiblingSwipe,
                    object: accumulatedX < 0 ? 1 : -1
                )
            } else if !horizontalIntent,
                      !canPanVertically || verticalSwipeAlwaysNavigates,
                      abs(accumulatedY) > Self.threshold {
                // Vertical = the RENDITION axis (Daniel, 2026-08-21). Same
                // pan-first rule: a vertically-overflowing zoom keeps native
                // scrolling; the flip engages only when there is nothing to
                // pan. Fingers up → negative deltaY → NEXT rendition.
                firedThisGesture = true
                NotificationCenter.default.post(
                    name: .previewRenditionSwipe,
                    object: accumulatedY < 0 ? 1 : -1
                )
            }
        }
        if event.momentumPhase == .ended {
            accumulatedX = 0
            accumulatedY = 0
        }
    }

    private static var lastTriageLog = Date.distantPast

    private func logSwipeTriage(phase: NSEvent.Phase, doc: NSView) {
        // Gesture starts always log; PHASE-LESS scrolls (a real mouse wheel,
        // or synthesized CGEvents in headless triage) log at most 1/s.
        if phase != .began {
            guard phase.isEmpty, Date().timeIntervalSince(Self.lastTriageLog) > 1 else { return }
        }
        Self.lastTriageLog = Date()
        // Recomputed here (cheap) so the call site stays one line.
        let scaledWidth = doc.frame.width * magnification
        let scaledHeight = doc.frame.height * magnification
        let canPanHorizontally = scaledWidth > contentSize.width + 0.5
        let canPanVertically = scaledHeight > contentSize.height + 0.5
        Logger(subsystem: "app.fichero.fichero", category: "swipe-triage").info(
            """
            swipe-triage began: doc=\(doc.frame.width, format: .fixed(precision: 1))x\
            \(doc.frame.height, format: .fixed(precision: 1)) mag=\(self.magnification, format: .fixed(precision: 3)) \
            scaled=\(scaledWidth, format: .fixed(precision: 1))x\(scaledHeight, format: .fixed(precision: 1)) \
            content=\(self.contentSize.width, format: .fixed(precision: 1))x\(self.contentSize.height, format: .fixed(precision: 1)) \
            canPanH=\(canPanHorizontally) canPanV=\(canPanVertically) ladder=\(self.verticalSwipeAlwaysNavigates)
            """
        )
    }
}

#endif
