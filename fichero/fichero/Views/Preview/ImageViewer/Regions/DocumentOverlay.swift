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
        /// The segment's own shapes (polygon, path, point, baseline), drawn instead of the box when
        /// present (`SegmentShapes`).
        var shapes: [SegmentShapes.Drawn] = []
        /// No reading: drawn dashed and hollow, so what has no text yet can be seen and picked.
        var noReading = false
        /// The segment drawn, and its kind: what the box is called as an accessibility element (#5192).
        var segmentId: String?
        var kind = ""
        /// The segment it sits in: how a selection lights its children and shows its parent (#5426).
        var parentSegmentId: String?
        /// Its region's hue and its shade along the reading order (`RegionColours.Tone`); nil draws plain.
        var tone: RegionColours.Tone?
        /// The segment's resolved direction (`SegmentStore`, from the page text), so its inline reading is
        /// set the way the line is written (#5411). Nil: not resolved.
        var direction: String?
    }

    var boxes: [Box] = []

    /// The finest level drawn: read once per draw, not once per box. Only it sets its reading inline.
    var finestLevel: SegmentHierarchy.Level { SegmentHierarchy.finestLevel(boxes.map(\.kind)) }

    /// Whether a box of `kind` sets its reading inline (#5411, `source.editor.inline-text-fits-its-box`):
    /// only the finest level drawn does. A region under lines does not -- its words are its lines', and its
    /// reading is every line joined, which drawn at the region's size ran off the page -- and with every level
    /// drawn at once (#5426) a line under its words does not set its reading over them.
    static func setsTextInline(kind: String, finest: SegmentHierarchy.Level) -> Bool {
        SegmentHierarchy.Level(kind: kind) >= finest
    }

    /// Each box's emphasis under the selection (`SegmentHierarchy.emphasis`), by segment id: selecting a parent
    /// lights its children and dims the rest; selecting a child shows its parent. Empty with no selection.
    var emphasis: [String: SegmentHierarchy.Emphasis] {
        guard !selectedSegmentIds.isEmpty else { return [:] }
        var parents: [String: String] = [:]
        for box in boxes {
            if let id = box.segmentId, let parent = box.parentSegmentId { parents[id] = parent }
        }
        return SegmentHierarchy.emphasis(
            of: boxes.compactMap(\.segmentId), parents: parents, selected: selectedSegmentIds
        )
    }

    /// The index of the smallest rect containing `point`, or nil (#5411, `source.editor.hover-picks-the-line`):
    /// the hover's rule, the same "smallest wins" a click uses, so a line inside a region is the line.
    static func smallestContaining(_ point: CGPoint, in rects: [CGRect]) -> Int? {
        rects.indices
            .filter { rects[$0].contains(point) }
            .min { rects[$0].width * rects[$0].height < rects[$1].width * rects[$1].height }
    }

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
    /// The selected boxes' segments: what lights their children and shows their parents (#5426).
    var selectedSegmentIds: Set<String> = []
    /// Each selected box's shapes, parallel to `selected`: outlined as themselves, and in Edit
    /// Segments given a handle per point and one per side to add a point (Reshape).
    var selectedShapes: [[SegmentShapes.Drawn]] = []
    /// The shape point the arrow keys nudge, normalized: its handle is drawn filled.
    var selectedPoint: [Double]?
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
    /// The page these boxes are drawn on: the overlay view is named `SegmentPage-<id>` to accessibility,
    /// so `describe window` groups the drawn boxes by page (#5193).
    var documentId: String?

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
