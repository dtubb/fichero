import Foundation
import SwiftUI

// MARK: - Drop-location inverse transform

/// Maps a drop location reported in the canvas's untransformed frame space
/// back into canvas (node-position) coordinates, undoing the rendered
/// `.scaleEffect(scale)` (anchored at the frame center) and `.offset(offset)`
/// pan — so a drop while zoomed/panned lands under the cursor (#4323).
enum WorkflowCanvasTransform {
    /// Forward mapping: canvasPoint → q = center + (p − center)·scale + offset.
    /// This is the inverse: p = (q − offset − center)/scale + center.
    static func canvasPoint(
        fromDropLocation location: CGPoint,
        canvasSize: CGSize,
        scale: CGFloat,
        offset: CGSize
    ) -> CGPoint {
        let center = CGPoint(x: canvasSize.width / 2, y: canvasSize.height / 2)
        let safeScale = max(scale, 0.0001)
        return CGPoint(
            x: (location.x - offset.width - center.x) / safeScale + center.x,
            y: (location.y - offset.height - center.y) / safeScale + center.y
        )
    }
}

// MARK: - Parallel edge separation

/// Perpendicular offsets so multiple edges sharing the SAME resolved
/// endpoints (e.g. a files + documents pair whose stored port ids collapse
/// to one geometry point) render as visually distinct curves instead of a
/// single line (#4322).
enum EdgeParallelOffset {
    struct Segment {
        let id: String
        let source: CGPoint
        let target: CGPoint

        init(id: String, source: CGPoint, target: CGPoint) {
            self.id = id
            self.source = source
            self.target = target
        }
    }

    /// Returns a vertical offset per edge id. Edges with unique geometry get
    /// no entry (0 offset); edges sharing both endpoints are fanned out
    /// symmetrically around the shared line, in input order.
    static func offsets(for segments: [Segment], spacing: CGFloat = 12) -> [String: CGFloat] {
        var groups: [String: [Segment]] = [:]
        var groupOrder: [String] = []
        for segment in segments {
            let key = "\(segment.source.x),\(segment.source.y)|\(segment.target.x),\(segment.target.y)"
            if groups[key] == nil { groupOrder.append(key) }
            groups[key, default: []].append(segment)
        }

        var result: [String: CGFloat] = [:]
        for key in groupOrder {
            guard let group = groups[key], group.count > 1 else { continue }
            let middle = CGFloat(group.count - 1) / 2
            for (index, segment) in group.enumerated() {
                result[segment.id] = (CGFloat(index) - middle) * spacing
            }
        }
        return result
    }
}
