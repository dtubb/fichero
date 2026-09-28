import CoreGraphics
import Foundation

/// What a PDF page needs from its host to reshape segments (`source.editor.reshape` on PDF pages): Edit
/// Segments, the ONE selected box with its index among the shown pass's boxes (its segment's
/// `boxIndex`), how to select one, and how to commit a reshape -- the image overlay's own
/// `onReshapeCommit` shape, so both surfaces send `SegmentShapes.reshape` the same way.
struct PDFSegmentEditing {
    var isEditing = false
    var selected: (index: Int, box: OCRGeometryBox)?
    var select: ((OCRGeometryBox?) -> Void)?
    var commit: ((Int, SegmentShapes.Target, [[Double]]) -> Void)?

    /// A PDF page's pick as the ONE selection (#5155's ruling): written into the page's `RegionSelection`
    /// in the shown pass's scope and box indices, exactly as an image page writes it, so the Inspector
    /// and the Reader follow it. Nil (blank page, or boxes with no pass behind them) clears it.
    @MainActor
    static func select(
        _ box: OCRGeometryBox?, among boxes: [OCRGeometryBox], scope: String?, documentId: String,
        into selection: RegionSelection
    ) {
        guard let box, let scope, let index = boxes.firstIndex(where: { $0.id == box.id }) else {
            selection.clear()
            return
        }
        selection.select(index, artifactId: scope, documentId: documentId, in: boxes)
    }

    /// The other way: whatever made the selection -- this page, the Inspector, the Reader's caret line --
    /// the ONE box it names on this page is the one that gets handles. Nil for none, several, or another
    /// pass's selection.
    @MainActor
    static func selected(
        from selection: RegionSelection, among boxes: [OCRGeometryBox], scope: String?, documentId: String
    ) -> (index: Int, box: OCRGeometryBox)? {
        guard let scope, selection.artifactId == scope, selection.documentId == documentId else { return nil }
        let picked = selection.resolvedIndices(in: boxes)
        guard picked.count == 1, let index = picked.first, boxes.indices.contains(index) else { return nil }
        return (index, boxes[index])
    }
}

#if os(macOS)
import AppKit
import PDFKit

/// A Reshape on a PDF page, in PDFKit PAGE points: a press, its drag and its release, read into the
/// display-space normalized points the shapes are stored in (`PDFRegionGeometry.normalizedPoint`) and
/// decided by the image overlay's rule (`ReshapeDrag.press`). Pure, so the joint test drives the same
/// calls the page's gestures make.
struct PDFReshapeSession {
    let rotation: Int
    let crop: CGRect
    private(set) var drag: ReshapeDrag?

    init(rotation: Int, crop: CGRect) {
        self.rotation = rotation
        self.crop = crop
    }

    func normalized(_ pagePoint: CGPoint) -> [Double]? {
        PDFRegionGeometry.normalizedPoint(fromPagePoint: pagePoint, rotation: rotation, crop: crop)
    }

    /// A handle's reach -- its side on screen at `scale` (view points per page point) -- normalized to
    /// the displayed page, whose width is the crop's height on a page turned a quarter.
    func reach(scale: CGFloat) -> [Double] {
        let side = Double(SelectionStyle.handleSide) / Double(max(scale, 0.01))
        let turned = ((rotation % 180) + 180) % 180 == 90
        let width = Double(turned ? crop.height : crop.width), height = Double(turned ? crop.width : crop.height)
        return [side / max(width, 1), side / max(height, 1)]
    }

    /// The box a click in Edit Segments picks: the smallest one around the point, so a line wins over
    /// the region holding it. Nil on blank page.
    static func pick(_ point: [Double], in boxes: [OCRGeometryBox]) -> OCRGeometryBox? {
        boxes.filter { box in
            box.bbox.count >= 4 && point.count >= 2
                && (box.bbox[0]...(box.bbox[0] + box.bbox[2])).contains(point[0])
                && (box.bbox[1]...(box.bbox[1] + box.bbox[3])).contains(point[1])
        }
        .min { $0.bbox[2] * $0.bbox[3] < $1.bbox[2] * $1.bbox[3] }
    }

    mutating func press(
        at pagePoint: CGPoint, on box: OCRGeometryBox, boxIndex: Int, scale: CGFloat, option: Bool
    ) -> ReshapeDrag.Press {
        guard let point = normalized(pagePoint) else { return .none }
        let pressed = ReshapeDrag.press(
            at: point, boxIndex: boxIndex, shapes: box.shapes, reach: reach(scale: scale), option: option
        )
        if case .drag(let started) = pressed { drag = started }
        return pressed
    }

    mutating func drag(to pagePoint: CGPoint) {
        guard var moving = drag, let point = normalized(pagePoint) else { return }
        moving.points = SegmentShapes.moving(moving.points, index: moving.pointIndex, to: point)
        drag = moving
    }

    /// The reshape to commit, or nil when the press moved nothing.
    mutating func release() -> ReshapeDrag? {
        defer { drag = nil }
        guard let done = drag, done.points != done.original else { return nil }
        return done
    }
}

extension PDFReshapeSession {
    init(page: PDFPage) {
        self.init(rotation: page.rotation, crop: page.bounds(for: .cropBox))
    }
}

extension PDFPageView {
    /// The click that selects a box in Edit Segments (and ⌥-click that removes a point).
    func wireSegmentEditing(_ coordinator: Coordinator, on view: PDFView) {
        let click = NSClickGestureRecognizer(target: coordinator, action: #selector(Coordinator.handleSegmentClick(_:)))
        click.delegate = coordinator
        view.addGestureRecognizer(click)
    }
}

extension PDFPageView.Coordinator {
    static let reshapeLiveName = "fichero.reshape-live"

    /// Edit Segments: a click picks the smallest box under it; ⌥-click on a point of the selected box
    /// removes the point (never below what its shape needs).
    @objc func handleSegmentClick(_ recognizer: NSClickGestureRecognizer) {
        let editing = owner.segmentEditing
        guard editing.isEditing, let view = pdfView, let page = view.currentPage else { return }
        let pagePoint = view.convert(recognizer.location(in: view), to: page)
        var session = PDFReshapeSession(page: page)
        if NSEvent.modifierFlags.contains(.option), let selected = editing.selected {
            let pressed = session.press(at: pagePoint, on: selected.box, boxIndex: selected.index, scale: view.scaleFactor, option: true)
            if case .remove(let target, let fewer) = pressed { editing.commit?(selected.index, target, fewer) }
            if pressed != .none { return }
        }
        guard let point = session.normalized(pagePoint) else { return }
        editing.select?(PDFReshapeSession.pick(point, in: owner.ocrBoxes))
    }

    /// A drag in Edit Segments that starts on a handle of the selected box reshapes it; true when it
    /// did, so the pan does not also turn the page or draw a region.
    func reshapePan(_ recognizer: NSPanGestureRecognizer, in view: PDFView) -> Bool {
        guard let page = view.currentPage else { return false }
        let location = recognizer.location(in: view)
        switch recognizer.state {
        case .began:
            guard let selected = owner.segmentEditing.selected else { return false }
            // The press is where the drag STARTED: a pan begins only after the pointer has moved.
            let moved = recognizer.translation(in: view)
            let start = view.convert(CGPoint(x: location.x - moved.x, y: location.y - moved.y), to: page)
            var session = PDFReshapeSession(page: page)
            guard case .drag = session.press(
                at: start, on: selected.box, boxIndex: selected.index, scale: view.scaleFactor, option: false
            ) else { return false }
            reshapeSession = session
            reshapeSession?.drag(to: view.convert(location, to: page))
            showLiveReshape(on: page)
            return true
        case .changed:
            guard reshapeSession != nil else { return false }
            reshapeSession?.drag(to: view.convert(location, to: page))
            showLiveReshape(on: page)
            return true
        default:
            guard var session = reshapeSession else { return false }
            reshapeSession = nil
            page.annotations.filter { $0.userName == Self.reshapeLiveName }.forEach(page.removeAnnotation)
            if let done = session.release() { owner.segmentEditing.commit?(done.boxIndex, done.target, done.points) }
            return true
        }
    }

    private func showLiveReshape(on page: PDFPage) {
        page.annotations.filter { $0.userName == Self.reshapeLiveName }.forEach(page.removeAnnotation)
        guard let drag = reshapeSession?.drag,
              let live = PDFShapeAnnotations.live(drag.points, closed: drag.target.isClosed, on: page, userName: Self.reshapeLiveName)
        else { return }
        page.addAnnotation(live)
    }
}
#endif
