@testable import Fichero
import Foundation
import Testing

// Daniel, 2026-08-31: "drawing selection in library is super slow, and if you
// draw marquee selection rubber band so that it should scroll, it should
// scroll." Both throttles and the autoscroll ramp are pure functions so they
// pin here without a running grid.
@Suite("LibraryMarquee — sweep throttles and edge autoscroll")
struct LibraryMarqueeSweepThrottleTests {
    // MARK: - Throttle 1: the band must actually have moved

    @Test("the first tick of a sweep always recomputes")
    func firstTickRecomputes() {
        #expect(LibraryMarquee.shouldRecomputeHits(from: nil, to: CGRect(x: 0, y: 0, width: 10, height: 10)))
    }

    @Test("sub-tolerance wobble does not re-test every tile")
    func wobbleIsIgnored() {
        let previous = CGRect(x: 10, y: 10, width: 100, height: 100)
        #expect(!LibraryMarquee.shouldRecomputeHits(from: previous, to: previous))
        // Every edge inside the 2pt tolerance.
        #expect(!LibraryMarquee.shouldRecomputeHits(
            from: previous,
            to: CGRect(x: 11.5, y: 8.5, width: 99, height: 101)
        ))
    }

    @Test("a real move on any single edge recomputes")
    func realMoveRecomputes() {
        let previous = CGRect(x: 10, y: 10, width: 100, height: 100)
        // Growing height only — the common case, dragging straight down.
        #expect(LibraryMarquee.shouldRecomputeHits(
            from: previous,
            to: CGRect(x: 10, y: 10, width: 100, height: 103)
        ))
        // Growing width only.
        #expect(LibraryMarquee.shouldRecomputeHits(
            from: previous,
            to: CGRect(x: 10, y: 10, width: 103, height: 100)
        ))
        // Sliding the origin without changing the size.
        #expect(LibraryMarquee.shouldRecomputeHits(
            from: previous,
            to: CGRect(x: 14, y: 10, width: 100, height: 100)
        ))
    }

    // MARK: - Throttle 2: selection is written only when MEMBERSHIP changes

    /// The grid's expensive re-render is gated on the HIT SET changing, not on
    /// the band moving — a band can sweep many pixels across the same tiles.
    /// `hitIds` is the membership function that gate compares, so equal sets
    /// across a moved band must compare equal.
    @Test("a band that grows without crossing a tile keeps the same membership")
    func membershipIsStableWithinATile() {
        let frames: [String: CGRect] = [
            "a": CGRect(x: 0, y: 0, width: 100, height: 100),
            "b": CGRect(x: 0, y: 200, width: 100, height: 100)
        ]
        let small = LibraryMarquee.hitIds(in: frames, rect: CGRect(x: 10, y: 10, width: 20, height: 20))
        let grown = LibraryMarquee.hitIds(in: frames, rect: CGRect(x: 10, y: 10, width: 60, height: 60))
        #expect(small == ["a"])
        #expect(grown == small)
        // Reaching the second tile IS a membership change — the one tick that
        // is allowed to re-render the grid.
        let reaching = LibraryMarquee.hitIds(in: frames, rect: CGRect(x: 10, y: 10, width: 60, height: 210))
        #expect(reaching == ["a", "b"])
        #expect(reaching != grown)
    }

    // MARK: - Autoscroll

    @Test("the middle of the viewport does not scroll")
    func middleIsIdle() {
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: 300, viewportHeight: 600) == 0)
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: 24, viewportHeight: 600) == 0)
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: 576, viewportHeight: 600) == 0)
    }

    @Test("the top edge zone scrolls up, the bottom edge zone scrolls down")
    func edgesScroll() {
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: 12, viewportHeight: 600) < 0)
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: 590, viewportHeight: 600) > 0)
    }

    @Test("speed ramps with depth and caps at the edge")
    func speedRamps() {
        let shallow = LibraryMarquee.autoScrollVelocity(pointerY: 590, viewportHeight: 600)
        let deep = LibraryMarquee.autoScrollVelocity(pointerY: 599, viewportHeight: 600)
        #expect(deep > shallow)
        // Dragged past the edge (out of the window) keeps scrolling, capped.
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: 900, viewportHeight: 600)
            == LibraryMarquee.autoScrollMaxSpeed)
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: -50, viewportHeight: 600)
            == -LibraryMarquee.autoScrollMaxSpeed)
    }

    @Test("a viewport too short for two zones never autoscrolls")
    func shortViewportIsInert() {
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: 2, viewportHeight: 40) == 0)
        // No AppKit seam (iOS, or the probe not yet attached) reports 0 height.
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: 2, viewportHeight: 0) == 0)
    }

    // MARK: - The edge zone in the space the pointer is actually reported in
    //
    // Daniel's re-test 2026-09-01: "it doesn't scroll at edges". The library
    // pane lays a floating head over the top of this scroll view and the
    // bottom action bar over its foot (`safeAreaInset`), which SwiftUI applies
    // as NSScrollView content insets. The pointer is reported in the scroll
    // view's own space, so the FIRST reachable pixel is `topInset` and the
    // last is `viewportHeight - bottomInset`. Measuring a 24pt zone from 0 and
    // from `viewportHeight` puts both zones under chrome the pointer can never
    // enter — the velocity is 0 everywhere the user can actually drag.

    /// The pane head and bottom bar as they are laid out on the Mac.
    private static let headInset: CGFloat = 44
    private static let barInset: CGFloat = 34

    @Test("the visible top edge scrolls up even though it is below the head")
    func insetTopEdgeScrolls() {
        // The topmost pixel the pointer can reach sits AT the inset.
        let atVisibleTop = LibraryMarquee.autoScrollVelocity(
            pointerY: Self.headInset,
            viewportHeight: 600,
            topInset: Self.headInset,
            bottomInset: Self.barInset
        )
        #expect(atVisibleTop == -LibraryMarquee.autoScrollMaxSpeed)
        // The same point WITHOUT the insets is dead — the shipped bug.
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: Self.headInset, viewportHeight: 600) == 0)
    }

    @Test("the visible bottom edge scrolls down even though the bar covers the foot")
    func insetBottomEdgeScrolls() {
        let atVisibleBottom = LibraryMarquee.autoScrollVelocity(
            pointerY: 600 - Self.barInset,
            viewportHeight: 600,
            topInset: Self.headInset,
            bottomInset: Self.barInset
        )
        #expect(atVisibleBottom == LibraryMarquee.autoScrollMaxSpeed)
        #expect(LibraryMarquee.autoScrollVelocity(pointerY: 600 - Self.barInset, viewportHeight: 600) == 0)
    }

    @Test("the inset middle is still idle, and the ramp still ramps")
    func insetMiddleIdleAndRamps() {
        #expect(LibraryMarquee.autoScrollVelocity(
            pointerY: 300, viewportHeight: 600,
            topInset: Self.headInset, bottomInset: Self.barInset
        ) == 0)
        // Just inside the visible band, past the zone: idle.
        #expect(LibraryMarquee.autoScrollVelocity(
            pointerY: Self.headInset + LibraryMarquee.autoScrollEdge, viewportHeight: 600,
            topInset: Self.headInset, bottomInset: Self.barInset
        ) == 0)
        // Within the zone: ramps, deeper is faster, and it is signed upward.
        let shallow = LibraryMarquee.autoScrollVelocity(
            pointerY: Self.headInset + 20, viewportHeight: 600,
            topInset: Self.headInset, bottomInset: Self.barInset
        )
        let deep = LibraryMarquee.autoScrollVelocity(
            pointerY: Self.headInset + 4, viewportHeight: 600,
            topInset: Self.headInset, bottomInset: Self.barInset
        )
        #expect(shallow < 0)
        #expect(deep < shallow)
    }

    @Test("dragging under the chrome keeps scrolling, capped — Finder")
    func pastTheInsetEdgeIsCapped() {
        // Pointer beneath the bottom bar, or above the head: still scrolling.
        #expect(LibraryMarquee.autoScrollVelocity(
            pointerY: 598, viewportHeight: 600,
            topInset: Self.headInset, bottomInset: Self.barInset
        ) == LibraryMarquee.autoScrollMaxSpeed)
        #expect(LibraryMarquee.autoScrollVelocity(
            pointerY: 2, viewportHeight: 600,
            topInset: Self.headInset, bottomInset: Self.barInset
        ) == -LibraryMarquee.autoScrollMaxSpeed)
    }

    @Test("insets that swallow the viewport disable autoscroll rather than invert it")
    func insetsLargerThanViewportAreInert() {
        #expect(LibraryMarquee.autoScrollVelocity(
            pointerY: 30, viewportHeight: 60, topInset: 44, bottomInset: 34
        ) == 0)
        // Negative insets cannot widen the band.
        #expect(LibraryMarquee.autoScrollVelocity(
            pointerY: 300, viewportHeight: 600, topInset: -100, bottomInset: -100
        ) == 0)
    }
}
