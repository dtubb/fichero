import CoreGraphics

/// The window toolbar's own measurements, in ONE place, so the two bars that
/// hang beneath it (the workflow bar and the markup bar) are the same size as
/// the toolbar rather than merely near it.
///
/// The defect this exists for (Daniel, 2026-09-02): the model chip's family
/// mark was a 20pt circle sitting between 17pt glyphs, so the AI icon read as
/// a badge someone had dropped on the toolbar — "far too big, blows up the
/// UX". Two bars and a chip had each picked their own numbers; a glyph size
/// that is a literal at three call sites drifts by construction.
///
/// Semantic system fonts still carry TYPE (`.body`, `.caption`); these are
/// the frame metrics around them, which have no semantic equivalent.
enum ToolbarMetrics {
    /// A standard toolbar glyph's square. `.body` renders to about this, so a
    /// mark drawn at this edge sits on the same optical line as the SF Symbol
    /// beside it.
    static let glyphSide: CGFloat = 16

    /// The row a toolbar item occupies in Icon-and-Text mode, and in Icon Only.
    /// The markup bar has always used this pair; the workflow bar's verb row
    /// was pinned at the tall value in both modes, so hiding the labels shrank
    /// nothing (Daniel, 2026-09-02: "the whole workflow strip should match
    /// toolbar metrics").
    static let rowHeightWithLabels: CGFloat = 52
    static let rowHeightIconOnly: CGFloat = 38

    /// The height either bar takes for the given label mode.
    static func rowHeight(showsLabels: Bool) -> CGFloat {
        showsLabels ? rowHeightWithLabels : rowHeightIconOnly
    }
}
