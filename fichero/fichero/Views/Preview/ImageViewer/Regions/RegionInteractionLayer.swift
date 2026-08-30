import SwiftUI

/// Stable palette for multi-selected regions (Daniel, 2026-08-29: N selected
/// rows highlight in DISTINCT colors). Keyed by the BOX index so a region
/// keeps its color while the selection around it changes. Outside the macOS
/// gate: the inspector's region rows use the same colors on every platform.
enum RegionPalette {
    static let colors: [Color] = [
        .blue, .orange, .green, .purple, .pink, .teal, .red, .indigo
    ]

    static func color(forBoxIndex index: Int) -> Color {
        colors[((index % colors.count) + colors.count) % colors.count]
    }
}

#if os(macOS)

/// The INTERACTIVE region layer over the Preview image: click-to-select,
/// ⇧-click to add, drag-a-selected-region to move, and the ephemeral
/// rubber-band marquees (add mode). Sits ABOVE `OCRGeometryOverlay`, which
/// deliberately stays a single inert Canvas — this layer builds views only
/// for the handful of SELECTED boxes and marquees, so the hundreds-of-boxes
/// perf fix is not regressed.
///
/// Event posture: pan is the NSScrollView's two-finger scroll (scrollWheel),
/// which a SwiftUI tap layer does not consume — so a full-frame TAP target is
/// safe here where a full-frame drag target would not be. Drags exist only
/// (a) inside a selected region (move) and (b) in add mode (rubber band).
struct RegionInteractionLayer: View {
    /// Displayed boxes with their FULL-list indices into the owning
    /// artifact's `ocr_geometry.boxes` — the index the engine addresses.
    let boxes: [(index: Int, box: OCRGeometryBox)]
    /// The FULL box list. Selection highlight reads through this, not the
    /// display set: the inspector's rows are LINE-level while the overlay may
    /// be displaying words, and a selected line must still light up.
    let allBoxes: [OCRGeometryBox]
    let visible: CGRect
    /// The artifact owning `boxes`; nil when only marquees are in play.
    let artifactId: String?
    let documentId: String
    /// Per-window ephemeral marquee seam (nil in hosts without WindowState).
    let marquees: PreviewMarqueeSelection?
    /// True while rubber-band add mode is armed.
    let isAddingRegion: Bool
    /// Commit a moved region: (full-list index, new normalized bbox).
    let onMoveCommit: (Int, [Double]) -> Void

    @State private var selection = RegionSelection.shared
    /// Live move drag: which box, and how far (view points).
    @State private var moveDrag: (index: Int, translation: CGSize)?
    /// Live rubber-band corners (view points).
    @State private var bandStart: CGPoint?
    @State private var bandCurrent: CGPoint?
    /// ⇧ held? Tracked via `onModifierKeysChanged` (pure SwiftUI — the §6b
    /// no-AppKit rule) because a tap gesture's value carries no modifiers.
    @State private var shiftHeld = false

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                marqueeRects(in: geo.size)
                selectedRegionRects(in: geo.size)
                if let rect = liveBandRect {
                    RoundedRectangle(cornerRadius: 2)
                        .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.5, dash: [4]))
                        .background(Color.accentColor.opacity(0.12))
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX, y: rect.minY)
                        .allowsHitTesting(false)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .contentShape(Rectangle())
            .gesture(isAddingRegion ? bandGesture(in: geo.size) : nil)
            .gesture(tapGesture(in: geo.size))
            .onModifierKeysChanged(mask: .shift) { _, new in
                shiftHeld = new.contains(.shift)
            }
        }
    }

    // MARK: - Drawing

    /// Selected regions, palette-colored, following a live move drag.
    /// Renders from the FULL list so a selection made in the inspector
    /// (line rows) lights up even while the overlay displays words.
    @ViewBuilder
    private func selectedRegionRects(in size: CGSize) -> some View {
        if artifactId != nil, selection.artifactId == artifactId {
            ForEach(selection.indices.filter { allBoxes.indices.contains($0) }, id: \.self) { index in
                let box = allBoxes[index]
                if let rect = BoundingBoxGeometry.viewRect(
                    normalized: box.bbox, in: size, visible: visible
                ) {
                    let offset = moveDrag?.index == index
                        ? (moveDrag?.translation ?? .zero) : .zero
                    let color = RegionPalette.color(forBoxIndex: index)
                    RoundedRectangle(cornerRadius: 2)
                        .stroke(color, lineWidth: 2)
                        .background(color.opacity(0.14))
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX + offset.width, y: rect.minY + offset.height)
                        .gesture(moveGesture(for: (index: index, box: box), in: size))
                }
            }
        }
    }

    /// Ephemeral marquees: dashed, visually distinct from persisted regions;
    /// the marquee picked for deletion carries a solid accent stroke.
    @ViewBuilder
    private func marqueeRects(in size: CGSize) -> some View {
        if let marquees, marquees.documentId == documentId {
            ForEach(Array(marquees.rects.enumerated()), id: \.offset) { index, box in
                if let rect = BoundingBoxGeometry.viewRect(
                    normalized: box, in: size, visible: visible
                ) {
                    let isPicked = marquees.selectedIndex == index
                    RoundedRectangle(cornerRadius: 2)
                        .stroke(
                            Color.accentColor,
                            style: StrokeStyle(lineWidth: isPicked ? 2.5 : 1.5, dash: isPicked ? [] : [5])
                        )
                        .background(Color.accentColor.opacity(isPicked ? 0.18 : 0.08))
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX, y: rect.minY)
                        .allowsHitTesting(false)
                }
            }
        }
    }

    private var liveBandRect: CGRect? {
        guard let start = bandStart, let current = bandCurrent else { return nil }
        return CGRect(
            x: min(start.x, current.x),
            y: min(start.y, current.y),
            width: abs(current.x - start.x),
            height: abs(current.y - start.y)
        )
    }

    // MARK: - Gestures

    /// Click = select; ⇧-click = add/toggle; click-away = deselect (regions
    /// AND marquees — the honest reading of "click-away clears").
    private func tapGesture(in size: CGSize) -> some Gesture {
        SpatialTapGesture().onEnded { value in
            let additive = shiftHeld
            // Marquees first: they are drawn on top and are what the user
            // most recently made.
            if let marquees, marquees.documentId == documentId,
               let picked = RegionHitTesting.pick(
                   at: value.location, boxes: marquees.rects, in: size, visible: visible
               ) {
                marquees.selectedIndex = picked
                return
            }
            if let artifactId,
               let picked = RegionHitTesting.pick(
                   at: value.location, boxes: boxes.map { $0.box.bbox }, in: size, visible: visible
               ) {
                let fullIndex = boxes[picked].index
                if additive {
                    selection.toggle(fullIndex, artifactId: artifactId, documentId: documentId)
                } else {
                    selection.select(fullIndex, artifactId: artifactId, documentId: documentId)
                }
                marquees?.selectedIndex = nil
                return
            }
            // Empty ground: clear everything ephemeral.
            selection.clear()
            marquees?.clear()
        }
    }

    /// Rubber-band a new marquee (add mode only — a full-frame drag target
    /// outside an armed mode would fight the platform).
    private func bandGesture(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                if bandStart == nil { bandStart = value.startLocation }
                bandCurrent = value.location
            }
            .onEnded { value in
                defer { bandStart = nil; bandCurrent = nil }
                let start = bandStart ?? value.startLocation
                if let box = BoundingBoxGeometry.normalizedBox(
                    from: start, to: value.location, in: size, visible: visible
                ) {
                    marquees?.add(box, documentId: documentId)
                }
            }
    }

    /// Drag a SELECTED region to move it; the bbox commits on mouse-up.
    private func moveGesture(
        for item: (index: Int, box: OCRGeometryBox), in size: CGSize
    ) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                moveDrag = (item.index, value.translation)
            }
            .onEnded { value in
                moveDrag = nil
                if let moved = RegionHitTesting.moved(
                    bbox: item.box.bbox, byViewDelta: value.translation,
                    in: size, visible: visible
                ) {
                    onMoveCommit(item.index, moved)
                }
            }
    }
}

#endif
