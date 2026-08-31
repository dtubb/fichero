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

/// Per-tile frames in the icon grid's coordinate space.
struct IconTileFramesKey: PreferenceKey {
    static let defaultValue: [String: CGRect] = [:]
    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) {
        value.merge(nextValue(), uniquingKeysWith: { _, new in new })
    }
}

extension View {
    /// Report this tile's frame under `id` for marquee hit-testing.
    func iconTileFrame(id: String, in space: String) -> some View {
        background(
            GeometryReader { geo in
                Color.clear.preference(
                    key: IconTileFramesKey.self,
                    value: [id: geo.frame(in: .named(space))]
                )
            }
        )
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
    func updateNSView(_ nsView: NSView, context: Context) {}

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
        private func adopt() {
            guard let found = enclosingScrollView else { return }
            model.scrollView = found
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

    /// Signed autoscroll speed for a pointer at `pointerY` in a viewport
    /// `viewportHeight` tall: negative near the top, positive near the
    /// bottom, ramping linearly from 0 at the edge zone's inner boundary to
    /// `maxSpeed` at the edge itself (and staying at `maxSpeed` past it, so
    /// dragging out of the window keeps scrolling — Finder).
    static func autoScrollVelocity(
        pointerY: CGFloat,
        viewportHeight: CGFloat,
        edge: CGFloat = autoScrollEdge,
        maxSpeed: CGFloat = autoScrollMaxSpeed
    ) -> CGFloat {
        // Too short to have two distinct zones: no autoscroll at all.
        guard viewportHeight > edge * 2 else { return 0 }
        if pointerY < edge {
            let depth = min(1, (edge - pointerY) / edge)
            return -maxSpeed * depth
        }
        let fromBottom = viewportHeight - pointerY
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
