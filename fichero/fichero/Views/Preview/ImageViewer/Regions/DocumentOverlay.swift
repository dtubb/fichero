import CoreGraphics

/// How a saved mark is drawn on the page: a wash, a bar under or through the words, a line, a box.
/// Top level for SwiftLint's nesting rule (it was `DocumentOverlay.Mark.Shape`).
enum DocumentOverlayMarkShape: Equatable { case wash, underline, strike, line, box }

/// What the one-transform overlay draws (#5020, #5142): the page's boxes and the selection, as
/// plain values, so the view only draws and this decides.
struct DocumentOverlay: Equatable {
    struct Box: Equatable {
        /// `[x, y, w, h]`, normalized, top-left origin.
        let bbox: [Double]
        let confidence: Double?
        /// The recognised words, drawn IN the box when `showsText` (the inline-text switch, and a
        /// machine sure enough of where the word is).
        var text: String = ""
        var showsText = false
    }

    var boxes: [Box] = []

    /// A saved annotation mark whose look is pure geometry -- a wash, a bar, a line, a box. The
    /// glyph and text marks (a check in the margin, a note, a star) and anything tappable stay in
    /// SwiftUI: there are few of them, and a note must stay tappable.
    struct Mark: Equatable {
        let shape: DocumentOverlayMarkShape
        let bbox: [Double]
        /// The person's chosen colour (data, not chrome), or nil for the default.
        let color: AnnotationRGBA?

        /// The shape an annotation draws as here, or nil when it is drawn elsewhere.
        static func shape(for kind: AnnotationKind) -> DocumentOverlayMarkShape? {
            switch kind {
            case .highlight: .wash
            case .underline: .underline
            case .strikethrough: .strike
            case .line: .line
            case .rating, .note, .bookmark: nil
            default: .box
            }
        }
    }

    /// The selected boxes' rects, normalized. Drawn in the SAME view and pass as the boxes, so a
    /// highlight can never sit a transform away from the box it marks.
    var selected: [[Double]] = []
    /// The entry-source highlight: a soft wash BEHIND the words (the passage a claim or a search
    /// hit came from). Drawn first.
    var entryWashes: [[Double]] = []
    /// Words lit by the Reader's text selection, sharper than the entry wash.
    var linkedWashes: [[Double]] = []
    /// Saved annotation marks drawn as geometry (`Mark`), frame-gated and switched by the host.
    var marks: [Mark] = []
    /// The annotation the Inspector has selected, drawn in the selection's own style.
    var selectedMark: [Double]?
    /// Ephemeral marquees (run scopes, not segments): dashed; the picked one solid. Their name
    /// badges are buttons and stay in SwiftUI.
    var marquees: [[Double]] = []
    var pickedMarquee: Int?
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
