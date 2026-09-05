import CoreGraphics
import Foundation
import Observation

/// Shared selection of PERSISTED regions — boxes inside one artifact's
/// `ocr_geometry` — for the regions-as-first-class work (Daniel, 2026-08-29).
///
/// The `FocusedArtifact` idiom: one small shared focus holder that the
/// inspector's region rows WRITE and the Preview overlay OBSERVES (and vice
/// versa — clicking a box in Preview lights its row). Boxes carry no server
/// ids, so a region is addressed the way the engine addresses it: by its
/// position in the artifact's full `boxes` list. Indices are ordered by
/// selection time; the palette color is keyed to the BOX index (stable while
/// the selection around it changes).
@MainActor
@Observable
final class RegionSelection {
    static let shared = RegionSelection()

    /// The artifact whose boxes are selected. A selection never spans
    /// artifacts — regions from two geometries share no coordinate frame.
    private(set) var artifactId: String?
    private(set) var documentId: String?

    /// FULL-list indices into the artifact's `ocr_geometry.boxes`, in
    /// selection order (combine order falls to READING order server-side,
    /// so click order is free to mean "what I picked, when").
    private(set) var indices: [Int] = []

    init() {}

    var count: Int { indices.count }
    var isEmpty: Bool { indices.isEmpty }

    func isSelected(_ index: Int, in artifactId: String) -> Bool {
        self.artifactId == artifactId && indices.contains(index)
    }

    /// Replace the selection with one region (plain click).
    func select(_ index: Int, artifactId: String, documentId: String?) {
        retarget(artifactId: artifactId, documentId: documentId)
        indices = [index]
    }

    /// Add/remove one region (⇧-click, inspector row toggle).
    func toggle(_ index: Int, artifactId: String, documentId: String?) {
        retarget(artifactId: artifactId, documentId: documentId)
        if let position = indices.firstIndex(of: index) {
            indices.remove(at: position)
        } else {
            indices.append(index)
        }
    }

    /// Replace the selection with a whole set at once (⌘A over the preview,
    /// Daniel 2026-08-31: all text with the text tool, all boxes with the
    /// select tool). Order is the caller's — reading order for a geometry.
    func selectAll(_ indices: [Int], artifactId: String, documentId: String?) {
        retarget(artifactId: artifactId, documentId: documentId)
        self.indices = indices
    }

    func clear() {
        artifactId = nil
        documentId = nil
        indices = []
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
            self.artifactId = artifactId
        }
        if let documentId { self.documentId = documentId }
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
