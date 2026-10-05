import SwiftUI

#if os(macOS)

/// The double-click popover on a segment box (`preview.segment.double-click-popover`, #5414): the box
/// is selected by the double-click's first verb, then a line, word or region box opens the Reader's Lines
/// row for its segment -- the same view -- instead of the old open/zoom.
extension RegionInteractionLayer {
    /// Open the popover for `box` when it names a stored segment; false leaves the double-click its old verb.
    func openSegmentPopover(for box: OCRGeometryBox) -> Bool {
        guard let target = SegmentPopoverTarget.target(for: box) else { return false }
        segmentPopover = target
        return true
    }

    /// Where the popover points: a clear frame over the box, always in the tree so the popover presents
    /// when its target is set.
    func segmentPopoverAnchor(in size: CGSize) -> some View {
        let rect = segmentPopover.flatMap { BoundingBoxGeometry.viewRect(normalized: $0.bbox, in: size, visible: visible) }
            ?? .zero
        return Color.clear
            .frame(width: max(rect.width, 1), height: max(rect.height, 1))
            .offset(x: rect.minX, y: rect.minY)
            .allowsHitTesting(false)
            .popover(item: $segmentPopover, arrowEdge: .bottom) { target in
                ReaderLinePopover(segmentId: target.id, documentId: documentId)
            }
    }
}

#endif
