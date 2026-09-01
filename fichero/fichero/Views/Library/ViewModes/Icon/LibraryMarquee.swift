#if os(macOS)
import AppKit
#endif
import SwiftUI

// MARK: - Rubber-band selection for the icon grid (Daniel, 2026-08-09:
// Finder's grammar — nothing on hover, RUBBER BAND, the system highlight,
// cursor-borne drag feedback).
//
// Mechanism: each tile reports its frame in the grid's named coordinate
// space; a drag that STARTS in the gutter sweeps a rect, the intersecting
// tile ids feed `SelectionGrammar.marquee` live (⇧/⌘ ADD, plain replaces,
// an empty plain sweep clears — the same rules the 2D canvas marquee
// already follows), and the accent rectangle draws in an overlay. Tiles'
// own `.draggable` wins on the tiles themselves, so a marquee can only
// begin on empty space — exactly Finder.

extension View {
    /// Report this tile's frame under `id` for marquee hit-testing.
    ///
    /// Writes STRAIGHT into the marquee box, per tile (2026-09-01). This used
    /// to be a `PreferenceKey` whose `reduce` merged a `[String: CGRect]`
    /// dictionary pairwise up the whole grid, and that is what "there's a
    /// pause on first click" was: a click in the gutter clears the selection,
    /// every tile re-evaluates `isSelected`, the LazyVGrid re-lays out — and
    /// the preference machinery then rebuilt an N-entry dictionary by N merges
    /// (each copying the accumulated result) and diffed it for equality
    /// against the previous N-entry dictionary, on the main thread, before the
    /// drag's first `onChanged` could run. Over a 600-tile diary folder that
    /// is the visible stall, and it repeated on every layout pass of the sweep.
    ///
    /// One tile writing one key into an `@ObservationIgnored` box is O(1),
    /// allocates nothing, and — because the box is observation-ignored —
    /// re-renders nothing (HARD rule: no wholesale list re-render).
    ///
    /// Mid-sweep the tile also seeds its CONTENT-space frame if the sweep has
    /// not seen it yet: that is how a tile materialised by an autoscroll
    /// becomes selectable, without the sweep ever re-reading the live index.
    func iconTileFrame(id: String, in space: String, model: MarqueeModel) -> some View {
        onGeometryChange(for: CGRect.self) { proxy in
            proxy.frame(in: .named(space))
        } action: { frame in
            model.tileFrames[id] = frame
            if model.anchorContent != nil, model.contentFrames[id] == nil {
                model.contentFrames[id] = frame.offsetBy(dx: 0, dy: model.scrollOffsetY)
            }
        }
        // A tile the lazy grid recycled must not leave a stale frame behind:
        // `startsInGutter` would read it as "a tile is here" and refuse to
        // begin a sweep over empty space.
        .onDisappear { model.tileFrames.removeValue(forKey: id) }
    }
}

/// Live sweep state in an @Observable BOX (2026-08-09 perf fix: as
/// LibraryView @State, every mouse tick re-rendered the whole grid — 'the
/// rubber band doesn't keep up with the mouse'). Only the small overlay
/// view reads `rect`, so per-tick mutation re-renders ONE rectangle; the
/// grid re-renders only when the HIT SET changes and selection is applied.
@MainActor
@Observable
final class MarqueeModel {
    /// The band, in VIEWPORT space — what the overlay draws. The only
    /// observed property on the box.
    var rect: CGRect?
    @ObservationIgnored var lastHits: Set<String> = []
    @ObservationIgnored var baseSelection: Set<String>?
    /// Per-tile frames for hit-testing. In the BOX, not LibraryView @State
    /// (log audit 2026-08-19: the preference fired per scroll frame — frames
    /// are named-space relative to the outer container — and each write
    /// re-rendered the whole grid). Only gesture handlers read this; nothing
    /// renders from it, so it's observation-ignored.
    @ObservationIgnored var tileFrames: [String: CGRect] = [:]

    // MARK: - Live sweep (2026-08-31: "drawing selection in library is super
    // slow, and if you draw a marquee so that it should scroll, it should
    // scroll"). A sweep now runs in CONTENT space so autoscrolling under the
    // pointer doesn't drag the anchor with it, and the hit set is recomputed
    // only when the band actually moved.

    /// The sweep's fixed origin in CONTENT space (viewport point + scroll
    /// offset). Non-nil exactly while a sweep is live — the flag every other
    /// handler tests, since `rect` is the drawn shape and may lag.
    @ObservationIgnored var anchorContent: CGPoint?
    /// Tile frames in CONTENT space: seeded from `tileFrames` at drag start
    /// and merged (not replaced) as the lazy grid materialises new tiles
    /// under an autoscroll. Hit-testing reads THIS, never the live index.
    @ObservationIgnored var contentFrames: [String: CGRect] = [:]
    /// The band the hit set was last computed for — the >2pt throttle.
    @ObservationIgnored var lastHitRect: CGRect?
    /// The pointer's last VIEWPORT position; the autoscroll tick re-derives
    /// the content point from it as the offset moves under a still mouse.
    @ObservationIgnored var pointerViewport: CGPoint = .zero
    /// Points per tick, signed: negative scrolls up, positive down, 0 idle.
    @ObservationIgnored var autoScrollVelocity: CGFloat = 0
    @ObservationIgnored var autoScrollTask: Task<Void, Never>?

    #if os(macOS)
    /// The AppKit scroll view SwiftUI's `ScrollView` is built on, handed over
    /// by `MarqueeScrollProbe`. Read for the live offset and driven for
    /// autoscroll — both without touching observable state, so neither
    /// re-renders the grid (HARD rule: no wholesale list re-render).
    @ObservationIgnored weak var scrollView: NSScrollView?
    #endif

    /// Content-space Y of the viewport's top edge.
    var scrollOffsetY: CGFloat {
        #if os(macOS)
        scrollView?.contentView.bounds.origin.y ?? 0
        #else
        0
        #endif
    }

    /// Visible height of the scroll viewport; 0 where there's no AppKit seam,
    /// which simply disables autoscroll rather than guessing.
    var viewportHeight: CGFloat {
        #if os(macOS)
        scrollView?.contentView.bounds.height ?? 0
        #else
        0
        #endif
    }

    /// How much of the viewport's TOP edge is covered by chrome the user
    /// cannot drag into, in the SAME space the pointer is reported in
    /// (2026-09-01 — "it doesn't scroll at edges").
    ///
    /// The library pane stacks two `safeAreaInset`s on this scroll view: the
    /// floating pane head above the rows and the bottom action bar below
    /// them. SwiftUI expresses those as `contentInsets` on the NSScrollView —
    /// the clip view keeps its FULL height, and the content is pushed inward.
    /// So the topmost pixel the user can actually reach with the pointer is
    /// `contentInsets.top`, not 0, and the bottom-most is
    /// `viewportHeight - contentInsets.bottom`, not `viewportHeight`.
    ///
    /// The old edge test compared the pointer against the raw 0…viewportHeight
    /// band with a 24pt zone. The head is taller than 24pt and so is the bottom
    /// bar, so the pointer could never enter EITHER zone: the sweep reached the
    /// visible edge and the velocity was still exactly 0. That is the whole bug
    /// — the ticker, the probe and the clip-view scroll were all working and
    /// simply never asked to move.
    var viewportTopInset: CGFloat {
        #if os(macOS)
        max(0, scrollView?.contentInsets.top ?? 0)
        #else
        0
        #endif
    }

    /// The bottom half of `viewportTopInset`'s story — the action bar.
    var viewportBottomInset: CGFloat {
        #if os(macOS)
        max(0, scrollView?.contentInsets.bottom ?? 0)
        #else
        0
        #endif
    }

    /// Scroll by `deltaY` points, clamped to the document. Returns the distance
    /// actually travelled (0 at either end, which parks the autoscroll).
    @discardableResult
    func autoScroll(by deltaY: CGFloat) -> CGFloat {
        #if os(macOS)
        guard deltaY != 0, let scrollView, let document = scrollView.documentView else { return 0 }
        let clip = scrollView.contentView
        let limit = max(0, document.bounds.height - clip.bounds.height)
        let current = clip.bounds.origin.y
        let target = min(max(0, current + deltaY), limit)
        guard target != current else { return 0 }
        clip.scroll(to: CGPoint(x: clip.bounds.origin.x, y: target))
        scrollView.reflectScrolledClipView(clip)
        return target - current
        #else
        _ = deltaY
        return 0
        #endif
    }

    /// Drop every trace of a sweep (drag ended, or never legally began).
    func endSweep() {
        autoScrollTask?.cancel()
        autoScrollTask = nil
        autoScrollVelocity = 0
        anchorContent = nil
        contentFrames = [:]
        lastHitRect = nil
        lastHits = []
        baseSelection = nil
        rect = nil
    }
}

#if os(macOS)
/// A zero-size AppKit probe that hands the enclosing `NSScrollView` to the
/// marquee model. SwiftUI has no pixel-level scroll command that doesn't
/// round-trip through observable state, and `.scrollPosition` would re-render
/// the whole grid on every scroll frame — the exact pathology the box exists
/// to avoid. Reading and driving the clip view directly costs nothing.
struct MarqueeScrollProbe: NSViewRepresentable {
    let model: MarqueeModel

    func makeNSView(context: Context) -> NSView { ProbeView(model: model) }

    /// Re-adopt on every SwiftUI update too. `viewDidMoveToWindow` fires once,
    /// and SwiftUI may host this view before the enclosing `NSScrollView`
    /// exists — a single missed adoption left `model.scrollView` nil for the
    /// whole session, which reads to the user as "autoscroll is not
    /// implemented" (`viewportHeight` is then 0 and every velocity is 0).
    func updateNSView(_ nsView: NSView, context: Context) {
        (nsView as? ProbeView)?.adoptScrollView()
    }

    private final class ProbeView: NSView {
        private let model: MarqueeModel

        init(model: MarqueeModel) {
            self.model = model
            super.init(frame: .zero)
        }

        @available(*, unavailable)
        required init?(coder: NSCoder) { fatalError("MarqueeScrollProbe is code-only") }

        override func viewDidMoveToSuperview() {
            super.viewDidMoveToSuperview()
            adopt()
        }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            adopt()
        }

        /// Keep the last scroll view we saw: SwiftUI detaches and re-attaches
        /// backgrounds during relayout, and dropping the reference mid-sweep
        /// would silently kill autoscroll.
        ///
        /// Internal (not private): `updateNSView` re-adopts from every SwiftUI
        /// update, so a scroll view that did not exist at insertion time is
        /// still found on the next pass rather than never.
        func adoptScrollView() {
            guard let found = enclosingScrollView else { return }
            model.scrollView = found
        }

        private func adopt() {
            adoptScrollView()
            // The probe can be inserted into its immediate superview BEFORE
            // that superview joins the scroll view's document view. One
            // deferred retry costs nothing and closes that window; without it
            // the miss is permanent and silent.
            guard model.scrollView == nil else { return }
            DispatchQueue.main.async { [weak self] in
                self?.adoptScrollView()
            }
        }
    }
}
#endif

/// The overlay host — the ONLY reader of the model's rect.
struct MarqueeOverlayHost: View {
    let model: MarqueeModel

    var body: some View {
        if let rect = model.rect {
            MarqueeRectangle(rect: rect)
        }
    }
}

/// The translucent accent sweep rectangle.
struct MarqueeRectangle: View {
    let rect: CGRect

    var body: some View {
        Rectangle()
            .fill(Color.accentColor.opacity(0.15))
            .overlay(Rectangle().stroke(Color.accentColor.opacity(0.6), lineWidth: 1))
            .frame(width: rect.width, height: rect.height)
            .offset(x: rect.minX, y: rect.minY)
            .allowsHitTesting(false)
    }
}

enum LibraryMarquee {
    /// How close to an edge the pointer must get before the view scrolls.
    static let autoScrollEdge: CGFloat = 24
    /// Points per tick at the very edge (ticks run at ~60Hz).
    static let autoScrollMaxSpeed: CGFloat = 18

    /// True when a drag's start point touches NO tile — the only place a
    /// rubber band may begin (Finder). Enforced at the gesture (#34: a
    /// ⌘-click on a tile that moved 4pt became a degenerate sweep that
    /// re-toggled the tile — the intermittent deselect).
    static func startsInGutter(_ point: CGPoint, frames: [String: CGRect]) -> Bool {
        !frames.values.contains { $0.contains(point) }
    }

    /// The rect between the drag's start and current points.
    static func rect(from start: CGPoint, to current: CGPoint) -> CGRect {
        CGRect(
            x: min(start.x, current.x),
            y: min(start.y, current.y),
            width: abs(current.x - start.x),
            height: abs(current.y - start.y)
        )
    }

    /// Ids of the tiles the sweep currently touches.
    static func hitIds(in frames: [String: CGRect], rect: CGRect) -> Set<String> {
        Set(frames.filter { $0.value.intersects(rect) }.keys)
    }

    /// Whether the band moved far enough to be worth re-testing every tile
    /// (2026-08-31 perf): a mouse drag delivers ticks far finer than a tile,
    /// so sub-pixel wobble used to re-run an O(tiles) intersection sweep on
    /// every one of them. Any edge moving more than `tolerance` counts.
    static func shouldRecomputeHits(
        from previous: CGRect?,
        to current: CGRect,
        tolerance: CGFloat = 2
    ) -> Bool {
        guard let previous else { return true }
        return abs(previous.minX - current.minX) > tolerance
            || abs(previous.minY - current.minY) > tolerance
            || abs(previous.maxX - current.maxX) > tolerance
            || abs(previous.maxY - current.maxY) > tolerance
    }

    /// Signed autoscroll speed for a pointer at `pointerY`, measured in the
    /// scroll view's own coordinate space: negative near the top, positive
    /// near the bottom, ramping linearly from 0 at the edge zone's inner
    /// boundary to `maxSpeed` at the edge itself (and staying at `maxSpeed`
    /// past it, so dragging out of the window keeps scrolling — Finder).
    ///
    /// `topInset` / `bottomInset` are the chrome the pane lays OVER this
    /// scroll view (`safeAreaInset`: the floating pane head, the bottom action
    /// bar), which SwiftUI applies as `contentInsets`. The zone is measured
    /// against the band the pointer can actually occupy — `topInset` to
    /// `viewportHeight - bottomInset` — not the raw viewport.
    ///
    /// This is the coordinate-space bug behind "it doesn't scroll at edges":
    /// with a ~44pt pane head and a ~34pt bottom bar, a pointer at the visible
    /// top edge reported `pointerY ≈ 44`, which is OUTSIDE a 24pt zone
    /// measured from 0 — so the velocity was 0 everywhere the user could
    /// actually put the pointer. Insets default to 0, so the pure math is the
    /// same one the existing table pins.
    static func autoScrollVelocity(
        pointerY: CGFloat,
        viewportHeight: CGFloat,
        topInset: CGFloat = 0,
        bottomInset: CGFloat = 0,
        edge: CGFloat = autoScrollEdge,
        maxSpeed: CGFloat = autoScrollMaxSpeed
    ) -> CGFloat {
        let top = max(0, topInset)
        let bottom = max(0, bottomInset)
        let visibleHeight = viewportHeight - top - bottom
        // Too short to have two distinct zones: no autoscroll at all.
        guard visibleHeight > edge * 2 else { return 0 }
        let fromTop = pointerY - top
        if fromTop < edge {
            let depth = min(1, (edge - fromTop) / edge)
            return -maxSpeed * depth
        }
        let fromBottom = (viewportHeight - bottom) - pointerY
        if fromBottom < edge {
            let depth = min(1, (edge - fromBottom) / edge)
            return maxSpeed * depth
        }
        return 0
    }
}

// The marquee has no standalone view — preview the icon grid it selects in
// (Daniel, 2026-08-09: every view-mode file previews in place).
#Preview("Icon mode") { LibraryPreviewFixtures.mode(.icon, .icons) }
