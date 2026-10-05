import SwiftUI

/// The double-click popover on a PDF page's segment box (`preview.segment.double-click-popover`, #5414):
/// the image Preview's popover -- `SegmentPopoverTarget` opening `ReaderLinePopover`, one row of the
/// Reader's Lines lens, saving through `InspectorReadingEdit.save` -- pointed at a box `PDFView` draws.
/// Only the anchor differs: AppKit's `PDFView` owns the page's space, so the box's rect is mapped out of
/// it by the reveal's own rule (`PDFZoomController.pageRect`) and handed to a SwiftUI anchor over the page.
struct PDFSegmentPopover: Identifiable, Equatable {
    let target: SegmentPopoverTarget
    /// The box in the page view's own space, top-left origin: where the popover points.
    let anchor: CGRect
    var id: String { target.id }
}

extension PDFPageWithToolbar {
    /// A clear frame over the double-clicked box, always in the tree so the popover presents when set.
    var pdfSegmentPopoverAnchor: some View {
        let rect = pdfSegmentPopover?.anchor ?? .zero
        return Color.clear
            .frame(width: max(rect.width, 1), height: max(rect.height, 1))
            .offset(x: rect.minX, y: rect.minY)
            .allowsHitTesting(false)
            .popover(item: $pdfSegmentPopover, arrowEdge: .bottom) { popover in
                ReaderLinePopover(segmentId: popover.target.id, documentId: effectiveGeometryDocumentId)
            }
    }
}

#if os(macOS)
import PDFKit

extension PDFSegmentPopover {
    /// What a double-click at `pagePoint` opens: the smallest drawn box under it (the Edit Segments
    /// click's pick) when it names a stored segment, else nil -- PDFKit keeps its own double-click.
    @MainActor
    static func pick(
        atPagePoint pagePoint: CGPoint, on page: PDFPage, in boxes: [OCRGeometryBox]
    ) -> (box: OCRGeometryBox, target: SegmentPopoverTarget)? {
        guard let point = PDFReshapeSession(page: page).normalized(pagePoint),
              let box = PDFReshapeSession.pick(point, in: boxes),
              let target = SegmentPopoverTarget.target(for: box) else { return nil }
        return (box, target)
    }

    /// The box's rect in the page view, top-left origin: the page rect the reveal zooms to
    /// (`PDFZoomController.pageRect` -- unrotated, flipped, crop-offset, as the box is drawn), carried
    /// into the view by `toView` (`PDFView.convert(_:from:)`), then flipped when the view is not.
    @MainActor
    static func anchor(
        for bbox: [Double], on page: PDFPage, viewHeight: CGFloat, viewIsFlipped: Bool,
        toView: (CGRect) -> CGRect
    ) -> CGRect? {
        guard let pageRect = PDFZoomController.pageRect(forNormalized: bbox, on: page) else { return nil }
        let inView = toView(pageRect)
        guard !viewIsFlipped else { return inView }
        return CGRect(x: inView.minX, y: viewHeight - inView.maxY, width: inView.width, height: inView.height)
    }
}

extension PDFPageView.Coordinator {
    /// A double-click on a segment box selects it (the one selection, as a click does in Edit Segments)
    /// and opens its popover. Anywhere else the double-click is PDFKit's own.
    @objc func handleSegmentDoubleClick(_ recognizer: NSClickGestureRecognizer) {
        guard recognizer.state == .ended, let view = pdfView, let page = view.currentPage,
              let open = owner.segmentEditing.openPopover else { return }
        let pagePoint = view.convert(recognizer.location(in: view), to: page)
        guard let picked = PDFSegmentPopover.pick(atPagePoint: pagePoint, on: page, in: owner.ocrBoxes),
              let anchor = PDFSegmentPopover.anchor(
                  for: picked.target.bbox, on: page, viewHeight: view.bounds.height, viewIsFlipped: view.isFlipped,
                  toView: { view.convert($0, from: page) }
              ) else { return }
        owner.segmentEditing.select?(picked.box)
        open(PDFSegmentPopover(target: picked.target, anchor: anchor))
    }
}
#endif
