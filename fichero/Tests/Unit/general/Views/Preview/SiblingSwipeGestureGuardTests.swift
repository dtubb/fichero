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

/// Every image-SWAP endpoint re-measures the overlay geometry
/// (entry-highlight fix, 2026-08-23): the async load completion runs after
/// updateNSView's trailing re-measure, and the auto-fit it applies does not
/// reliably fire boundsDidChange — so the highlight drew against the
/// PREVIOUS item's frame, scaled and displaced.
struct ImageSwapGeometryGuardTests {
    @Test("all three swap endpoints call updateVisibleRect")
    func swapEndpointsRemeasure() throws {
        let url = try AppSource.root().appendingPathComponent(
            "Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingMac.swift"
        )
        let source = try String(contentsOf: url, encoding: .utf8)
        // updateNSView's two trailing calls + the three swap endpoints
        // (async load completion, sync override fit, same-item pixel swap).
        // COUNTED, not just present: losing any one reintroduces one stale
        // path while the others keep looking fixed.
        let calls = source.components(separatedBy: "updateVisibleRect()").count - 1
        #expect(
            calls >= 5,
            "an image-swap endpoint lost its geometry re-measure (\(calls) calls)"
        )
    }
}

/// The entry containment ladder (Daniel, 2026-08-23: "only show the bounding
/// box, but be able to get back to full page by swiping…which will also
/// bring us up to the full spread"). Structural pins: the vertical axis is
/// the LADDER on an entry and the rendition flip everywhere else, and the
/// region rung opens zoomed to the band.
struct EntryContainmentLadderGuardTests {
    private func source(_ rel: String) throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(rel), encoding: .utf8
        )
    }

    @Test("vertical steps consult the ladder before the rendition flip")
    func ladderOutranksRenditionFlip() throws {
        let viewer = try source("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        #expect(viewer.contains("if let onContainmentStep, onContainmentStep(step) { return }"))
        // All three vertical inputs route through the ONE arbiter — swipe
        // notification plus both arrow keys. Counted so a fourth input can't
        // quietly go straight to the flip.
        #expect(viewer.components(separatedBy: "verticalStep(").count - 1 >= 4)
    }

    @Test("the region rung opens zoomed to the band and owns the vertical axis")
    func regionRungOpensOnTheBand() throws {
        let entry = try source("Views/Preview/EntrySourcePreview.swift")
        #expect(entry.contains("focusRegion: ladderLevel == .region ? region.first : nil"))
        let tracking = try source("Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingMac.swift")
        #expect(tracking.contains("coordinator.zoomToNormalizedRegion(region)"))
        #expect(tracking.contains("verticalSwipeAlwaysNavigates =\n            focusRegion != nil"))
    }

    @Test("an entry with no region starts at the page rung, never a dead crop")
    func regionlessEntryStartsAtPage() throws {
        let entry = try source("Views/Preview/EntrySourcePreview.swift")
        #expect(entry.contains("ladderLevel = entry.regionInParent == nil ? .page : .region"))
        // …and stepping IN from the page respects the same absence.
        #expect(entry.contains("if entry.regionInParent != nil { ladderLevel = .region }"))
    }

    @Test("a folder parent is not a rung — the ladder stops at the page")
    func folderParentIsNotARung() throws {
        let entry = try source("Views/Preview/EntrySourcePreview.swift")
        #expect(entry.contains("guard let parent, parent.docType != .folder else { return }"))
    }
}
