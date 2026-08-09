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
    var rect: CGRect?
    @ObservationIgnored var lastHits: Set<String> = []
    @ObservationIgnored var baseSelection: Set<String>?
}

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
}
