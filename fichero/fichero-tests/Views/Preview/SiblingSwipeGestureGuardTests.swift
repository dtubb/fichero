import Foundation
import Testing

/// Source-surface guards for the preview's two-finger swipe grammar
/// (left/right = sibling document, up/down = rendition flip). A real NSEvent
/// scroll sequence cannot be synthesized in-process, so these pin the two
/// timing properties whose loss made swipes flaky (Daniel, 2026-08-21:
/// "doesn't always let you swipe up or down"):
///
///   * MOMENTUM accumulation — a quick flick delivers most of its distance as
///     momentum events; dropping them made fast natural swipes under-count
///     the threshold while slow drags worked.
///   * LATE axis classification — the first event of a gesture often carries
///     (0, 0) deltas, so reading the axis at `.began` was a coin flip. The
///     axis must be read from the accumulated totals at evaluation time.
struct SiblingSwipeGestureGuardTests {
    private func swipeSource() throws -> String {
        let url = try AppSource.root().appendingPathComponent(
            "Views/Preview/ImageViewer/CursorTracking/SiblingSwipeScrollView.swift"
        )
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("momentum events keep accumulating, so flicks count")
    func momentumAccumulates() throws {
        let source = try swipeSource()
        #expect(source.contains("event.phase == .changed || event.momentumPhase == .changed"))
        #expect(source.contains("event.phase == .ended || event.momentumPhase == .ended"))
    }

    @Test("the axis is read from the totals, never from the first event")
    func axisReadLate() throws {
        let source = try swipeSource()
        #expect(source.contains("let horizontalIntent = abs(accumulatedX) > abs(accumulatedY)"))
        #expect(
            !source.contains("horizontalIntent = abs(event.scrollingDeltaX)"),
            "classifying at .began reads the first event's often-zero deltas"
        )
    }

    @Test("a gesture fires at most one navigation")
    func firesOnce() throws {
        let source = try swipeSource()
        // Threshold can be crossed at the gesture end AND again when momentum
        // ends — without the flag one flick stepped two pages.
        #expect(source.contains("!firedThisGesture"))
        #expect(source.contains("firedThisGesture = false"))
    }
}
