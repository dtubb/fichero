import CoreGraphics
import Foundation
import Observation

/// The selection of PERSISTED regions — boxes inside one artifact's `ocr_geometry` — in ONE
/// Source-view pane (Daniel, 2026-08-29; per pane since 2026-09-27, #5020).
///
/// **Each pane owns one** (ruled 2026-09-27, applying two standing rulings: panes are not linked
/// unless a person connects them, 2026-09-19; and "visible surface, always", 2026-08-23 — a verb
/// acts on the selection of the surface you can see, and focus decides which). It used to be ONE
/// app-wide instance, so a click in one Preview lit a box in every other Preview of the page, and
/// by an index that could name a different box there (#5020). The Inspector and the markup row
/// follow the FOCUSED pane's selection through `WindowState.focusedRegionSelection`. Boxes carry no server
/// ids, so a region is addressed the way the engine addresses it: by its
/// position in the artifact's full `boxes` list. Indices are ordered by
/// selection time; the palette color is keyed to the BOX index (stable while
/// the selection around it changes).
@MainActor
@Observable
final class RegionSelection {
    /// The artifact whose boxes are selected. A selection never spans
    /// artifacts — regions from two geometries share no coordinate frame.
    private(set) var artifactId: String?
    private(set) var documentId: String?

    /// FULL-list indices into the artifact's `ocr_geometry.boxes`, in
    /// selection order (combine order falls to READING order server-side,
    /// so click order is free to mean "what I picked, when").
    private(set) var indices: [Int] = []
    /// WHAT each selected box is, beside WHERE it was (#5020, commit 2): its bbox, text and level,
    /// parallel to `indices`, nil when the writer passed no box list. Two panes can hold one
    /// artifact's boxes in different orders (the artifact's and the segment seam's), or one list
    /// from before an edit and one from after; an index means a different box in each. A key does
    /// not. Read the selection through `resolvedIndices(in:)`.
    private(set) var keys: [BoxKey?] = []

    init() {}

    /// The selected boxes' positions in THIS list: found by identity where the writer recorded it,
    /// by the raw index only where it did not. A box the list no longer holds is dropped -- never
    /// replaced by whatever now sits at its old index, which is the "below and right" of #5020.
    func resolvedIndices(in boxes: [OCRGeometryBox]) -> [Int] {
        var out: [Int] = []
        for (position, index) in indices.enumerated() {
            let key = position < keys.count ? keys[position] : nil
            let found: Int?
            if let key {
                found = boxes.firstIndex { BoxKey($0) == key }
            } else {
                found = boxes.indices.contains(index) ? index : nil
            }
            if let found, !out.contains(found) { out.append(found) }
        }
        return out
    }

    var count: Int { indices.count }
    var isEmpty: Bool { indices.isEmpty }

    func isSelected(_ index: Int, in artifactId: String) -> Bool {
        self.artifactId == artifactId && indices.contains(index)
    }

    /// Replace the selection with one region (plain click). `boxes` is the writer's own full list,
    /// so the box's identity is kept with its index.
    func select(_ index: Int, artifactId: String, documentId: String?, in boxes: [OCRGeometryBox]? = nil) {
        retarget(artifactId: artifactId, documentId: documentId)
        indices = [index]
        keys = [Self.key(index, in: boxes)]
    }

    /// Add/remove one region (⇧-click, inspector row toggle).
    func toggle(_ index: Int, artifactId: String, documentId: String?, in boxes: [OCRGeometryBox]? = nil) {
        retarget(artifactId: artifactId, documentId: documentId)
        if let position = indices.firstIndex(of: index) {
            indices.remove(at: position)
            if position < keys.count { keys.remove(at: position) }
        } else {
            indices.append(index)
            keys.append(Self.key(index, in: boxes))
        }
    }

    private static func key(_ index: Int, in boxes: [OCRGeometryBox]?) -> BoxKey? {
        guard let boxes, boxes.indices.contains(index) else { return nil }
        return BoxKey(boxes[index])
    }

    /// Replace the selection with a whole set at once (⌘A over the preview,
    /// Daniel 2026-08-31: all text with the text tool, all boxes with the
    /// select tool). Order is the caller's — reading order for a geometry.
    func selectAll(_ indices: [Int], artifactId: String, documentId: String?, in boxes: [OCRGeometryBox]? = nil) {
        retarget(artifactId: artifactId, documentId: documentId)
        self.indices = indices
        keys = indices.map { Self.key($0, in: boxes) }
    }

    func clear() {
        artifactId = nil
        documentId = nil
        indices = []
        keys = []
    }

    /// A server-side edit changed the artifact's box list, so every held
    /// index may now point at a different box. Honest answer: drop them.
    func invalidate(artifactId: String) {
        if self.artifactId == artifactId { clear() }
    }

    /// Selecting in a different artifact abandons the old selection — two
    /// geometries' indices must never mix.
    private func retarget(artifactId: String, documentId: String?) {
        if self.artifactId != artifactId {
            indices = []
            keys = []
            self.artifactId = artifactId
        }
        if let documentId { self.documentId = documentId }
    }
}

/// What a box IS, for finding it again in another list (#5020): its rect, words and level. Boxes
/// carry no server id; two boxes identical in all three are the same box as far as anyone can tell.
struct BoxKey: Hashable {
    let bbox: [Double]
    let text: String
    let level: String

    init(_ box: OCRGeometryBox) {
        bbox = box.bbox
        text = box.text
        level = box.level
    }
}

// MARK: - Hit testing (pure, unit-testable)

/// Point-in-box picking for the Preview overlay's click-to-select. Pure
/// coordinate math, no SwiftUI — the same testability rule as
/// `BoundingBoxGeometry`, which supplies the mapping it composes.
enum RegionHitTesting {
    /// The index (into `boxes`) of the SMALLEST box containing `point`, or
    /// nil. Smallest wins so an overlapping little region stays clickable
    /// inside a big one — otherwise the big box would shadow it forever.
    static func pick(
        at point: CGPoint,
        boxes: [[Double]],
        in size: CGSize,
        visible: CGRect
    ) -> Int? {
        var best: (index: Int, area: CGFloat)?
        for (index, box) in boxes.enumerated() {
            guard let rect = BoundingBoxGeometry.viewRect(
                normalized: box, in: size, visible: visible
            ), rect.insetBy(dx: -2, dy: -2).contains(point) else { continue }
            let area = rect.width * rect.height
            if best == nil || area < best!.area {
                best = (index, area)
            }
        }
        return best?.index
    }

    /// The CHECK tool's target at a click height (Daniel, 2026-09-04: "the
    /// check tool applies to the full line box — one gesture"). The line
    /// whose vertical extent contains the click wins, x ignored so a margin
    /// click counts. On a page (or height) with no recognised line, the
    /// honest "entire line" is a FULL-WIDTH band at the click's height, one
    /// typical line tall — never a private 16pt square that reads as a
    /// misplaced mark (the 2026-09-04 fallback squares at x≈0.96).
    ///
    /// - Parameters:
    ///   - normalizedY: the click's y in normalized image space (0…1).
    ///   - lines: the geometry's line-level boxes.
    /// - Returns: normalized `[x, y, w, h]`.
    static func checkTarget(atNormalizedY normalizedY: Double, lines: [[Double]]) -> [Double] {
        for line in lines where line.count >= 4
            && normalizedY >= line[1] && normalizedY <= line[1] + line[3] {
            return line
        }
        let heights = lines.compactMap { $0.count >= 4 && $0[3] > 0 ? $0[3] : nil }.sorted()
        let height = heights.isEmpty ? 0.03 : heights[heights.count / 2]
        let top = min(max(normalizedY - height / 2, 0), max(1 - height, 0))
        return [0, top, 1, height]
    }

    /// A drag's translation applied to a normalized box: the delta converts
    /// through the visible window (a 10pt drag while zoomed-in is a smaller
    /// normalized move), and the box is clamped to stay entirely on the page
    /// — a region half off the image is not a statement about the page.
    static func moved(
        bbox: [Double],
        byViewDelta delta: CGSize,
        in size: CGSize,
        visible: CGRect
    ) -> [Double]? {
        guard bbox.count >= 4, size.width > 0, size.height > 0 else { return nil }
        let deltaX = Double(delta.width / size.width) * visible.width
        let deltaY = Double(delta.height / size.height) * visible.height
        let width = bbox[2]
        let height = bbox[3]
        let movedX = min(max(bbox[0] + deltaX, 0), max(1 - width, 0))
        let movedY = min(max(bbox[1] + deltaY, 0), max(1 - height, 0))
        return [movedX, movedY, width, height]
    }
}
