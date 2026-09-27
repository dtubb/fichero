import CoreGraphics

/// What the one-transform overlay draws (#5020, #5142): the page's boxes and the selection, as
/// plain values, so the view only draws and this decides.
struct DocumentOverlay: Equatable {
    struct Box: Equatable {
        /// `[x, y, w, h]`, normalized, top-left origin.
        let bbox: [Double]
        let confidence: Double?
    }

    var boxes: [Box] = []
    /// The selected boxes' rects, normalized. Drawn in the SAME view and pass as the boxes, so a
    /// highlight can never sit a transform away from the box it marks.
    var selected: [[Double]] = []
    /// The entry-source highlight: a soft wash BEHIND the words (the passage a claim or a search
    /// hit came from). Drawn first.
    var entryWashes: [[Double]] = []
    /// Words lit by the Reader's text selection, sharper than the entry wash.
    var linkedWashes: [[Double]] = []
    /// Edit Segments is on: a selection shows its resize handles (never while reading).
    var isEditing = false
    /// This pane's selection is the window's focused one (`WindowState.focusedRegionSelection`):
    /// with a key window, the selection is emphasized; otherwise it dims, as Finder's does.
    var isFocusedPane = false

    static let empty = DocumentOverlay()

    /// The boxes a redraw of `dirty` (document coordinates) must paint, each with its document rect.
    /// AppKit asks for only the newly exposed strip when the page scrolls, and a box outside it is
    /// already on screen or not visible at all -- so a scroll of a 4,525-box page paints a handful.
    func boxes(in dirty: CGRect, imageRect: CGRect) -> [(box: Box, rect: CGRect)] {
        boxes.compactMap { box in
            guard let rect = DocumentBoxMapping.rect(normalized: box.bbox, imageRect: imageRect),
                  rect.intersects(dirty) else { return nil }
            return (box, rect)
        }
    }

    /// The selected rects a redraw of `dirty` must paint.
    func selected(in dirty: CGRect, imageRect: CGRect) -> [CGRect] {
        Self.rects(selected, in: dirty, imageRect: imageRect)
    }

    /// Any list of normalized rects, reduced to those a redraw of `dirty` must paint.
    static func rects(_ list: [[Double]], in dirty: CGRect, imageRect: CGRect) -> [CGRect] {
        list.compactMap { bbox in
            guard let rect = DocumentBoxMapping.rect(normalized: bbox, imageRect: imageRect),
                  rect.intersects(dirty) else { return nil }
            return rect
        }
    }
}
