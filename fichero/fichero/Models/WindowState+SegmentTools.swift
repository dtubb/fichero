import Foundation

/// The segment editor's held keys and tool state transitions (#6582): Knife, Marker, Brush and Paint
/// held or armed, Order clicks, the Simplify slider's release and the order overlay's flash.
/// The segment editor's tools that are armed by a flag rather than by `activeMarkupTool`.
enum SegmentFlagTool: Equatable {
    case knife, marker, order, brush, paint
}

extension WindowState {
    /// The one flag tool chosen now, nil when none is. At most one flag is ever true: `chooseSegmentTool` is the only way
    /// the tool row, the keys and Esc change them.
    var activeSegmentTool: SegmentFlagTool? {
        if knifeArmed { return .knife }
        if markerArmed { return .marker }
        if orderArmed { return .order }
        if brushArmed { return .brush }
        if paintArmed { return .paint }
        return nil
    }

    /// Choose one segment tool, or none (Select): exactly one is active and shown (#6734). A flag tool leaves
    /// `activeMarkupTool` empty, so the row does not also show Select and Select does not take the drag; putting a tool
    /// down returns to Select.
    func chooseSegmentTool(_ tool: SegmentFlagTool?) {
        activeMarkupTool = tool == nil ? .select : nil  // its didSet puts every flag down; the flags are set after
        knifeArmed = tool == .knife
        markerArmed = tool == .marker
        orderArmed = tool == .order
        brushArmed = tool == .brush
        paintArmed = tool == .paint
    }

    /// K pressed in Edit Segments: the Knife held, for a stroke or for a tap.
    func pressKnifeKey() {
        knifeHeld = true
        knifeStrokedWhileHeld = false
    }

    /// K let go (`segment-editor.split-knife`): after a stroke the Knife goes back; a tap (no stroke while held) chooses it,
    /// as the tool row's Knife does, until another tool is chosen or Esc.
    func letGoOfKnifeKey() {
        if knifeHeld, !knifeStrokedWhileHeld {
            chooseSegmentTool(.knife)
        }
        knifeHeld = false
        knifeStrokedWhileHeld = false
    }

    /// M pressed in Edit Segments.
    func pressMarkerKey() {
        markerHeld = true
        markerStrokedWhileHeld = false
    }

    /// M let go: after a stroke the Marker goes back; a tap chooses it.
    func letGoOfMarkerKey() {
        if markerHeld, !markerStrokedWhileHeld {
            chooseSegmentTool(.marker)
        }
        markerHeld = false
        markerStrokedWhileHeld = false
    }

    /// B pressed in Edit Segments.
    func pressBrushKey() {
        brushHeld = true
        brushStrokedWhileHeld = false
    }

    /// B let go: after a stroke the Brush goes back; a tap chooses it.
    func letGoOfBrushKey() {
        if brushHeld, !brushStrokedWhileHeld {
            chooseSegmentTool(.brush)
        }
        brushHeld = false
        brushStrokedWhileHeld = false
    }

    /// `[` and `]`: the Brush smaller or larger, between 6 and 120 points.
    func resizeBrush(larger: Bool) {
        brushSize = min(max(brushSize * (larger ? 1.25 : 0.8), 6), 120)
    }

    /// `[` and `]` on the Paintbrush: narrower or wider, between 4 and 120 points.
    func resizePaint(larger: Bool) {
        paintWidth = min(max(paintWidth * (larger ? 1.25 : 0.8), 4), 120)
    }

    /// A click on a segment in Order: numbered next, or, clicked again, its number taken away.
    func clickInOrder(_ segmentId: String, after selected: String?) {
        if let index = orderClicks.firstIndex(of: segmentId) {
            orderClicks.remove(at: index)
            return
        }
        if orderClicks.isEmpty { orderAfter = selected == segmentId ? nil : selected }
        orderClicks.append(segmentId)
    }

    /// Once Order is left (`orderArmed` false): the clicks to send, taken so they are sent once; nil when there are none.
    func takeOrderClicks() -> (segmentIds: [String], after: String?)? {
        guard !orderArmed, !orderClicks.isEmpty else { return nil }
        defer { orderClicks = []; orderAfter = nil }
        return (orderClicks, orderAfter)
    }

    /// The slider let go at `tolerance`: the live preview goes and one Simplify is asked for.
    func letGoOfSimplifySlider(at tolerance: Double) {
        simplifyTolerance = nil
        simplifyPreview = []
        simplifyRelease = SimplifyRelease(tolerance: tolerance)
    }

    /// Show the order numbers for `seconds`; a second flash meanwhile restarts the clock.
    func flashOrderOverlay(for seconds: Double = 2) {
        let stamp = UUID()
        orderOverlayStamp = stamp
        orderOverlayFlash = true
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(seconds))
            if self?.orderOverlayStamp == stamp { self?.orderOverlayFlash = false }
        }
    }
}
/// One release of the Simplify slider (`WindowState.simplifyRelease`); each is new, so the same tolerance twice is two.
struct SimplifyRelease: Equatable {
    let tolerance: Double
    let id = UUID()

    /// The engine's answer as paths to draw: each outline closed on its first point, each baseline as it is.
    static func paths(polygons: [[[Double]]?], baselines: [[[Double]]?]) -> [[[Double]]] {
        let outlines = polygons.compactMap { polygon -> [[Double]]? in
            guard let polygon, let first = polygon.first else { return nil }
            return polygon + [first]
        }
        return outlines + baselines.compactMap { $0 }
    }
}

/// `reading_order.sequence`: the segments clicked in the Order tool, in click order, in one order.
struct ReadingOrderSequenceRequest: Encodable, Equatable {
    let orderId: String
    let segmentIds: [String]
    let afterSegmentId: String?

    enum CodingKeys: String, CodingKey {
        case orderId = "order_id", segmentIds = "segment_ids", afterSegmentId = "after_segment_id"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(orderId, forKey: .orderId)
        try container.encode(segmentIds, forKey: .segmentIds)
        try container.encodeIfPresent(afterSegmentId, forKey: .afterSegmentId)
    }
}
