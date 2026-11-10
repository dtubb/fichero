import Foundation

/// The Preview's three modes (`source.editor.preview-has-three-modes`, #6482), one three-way control in its head.
/// Each mode puts its own tools on the markup row (`source.editor.toolbar-follows-the-mode`): reading never offers a
/// box or pixel tool, editing segments offers no annotation, and the image mode offers the pixel operations only.
nonisolated enum PreviewMode: String, CaseIterable, Identifiable {
    /// Look, annotate, highlight, copy: what is drawn is shown, never edited. The default.
    case read
    /// Edit regions, lines and the order: draw, reshape, move, join, delete.
    case segments
    /// Change the pixels: Enhance, Clean up the folder, crop, straighten, rotate, split.
    case image

    var id: String { rawValue }

    var title: String {
        switch self {
        case .read: "Read"
        case .segments: "Segments"
        case .image: "Image"
        }
    }

    var icon: String {
        switch self {
        case .read: "text.cursor"
        case .segments: "rectangle.dashed"
        case .image: "wand.and.stars"
        }
    }

    /// The markup row's tool identifiers each mode shows. A tool absent here is absent from the row, never greyed.
    /// Image-mode operations (crop, straighten, rotate, split page, Enhance) are not on this row: they are the image
    /// controls, which sit in this mode (`SourcePaneImageControls`).
    var tools: Set<String> {
        switch self {
        case .read:
            ["previewMarkupTextSelect", "previewMarkupWordSelect", "previewMarkupHighlight", "previewMarkupLine",
             "previewMarkupNote", "previewMarkupStar", "previewMarkupCheck"]
        case .segments:
            ["previewMarkupSelect", "previewMarkupDrawRegion", "previewMarkupShapeKind", "previewMarkupDelete",
             "previewMarkupCombine"]
        case .image:
            []
        }
    }

    func offers(_ identifier: String) -> Bool { tools.contains(identifier) }
}
