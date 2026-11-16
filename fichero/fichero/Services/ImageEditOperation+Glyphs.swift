import Foundation

// The one icon table (`preview.edit.tool.one-icon-table`, #1420). Every place a tool or its step is shown draws its glyph from here, so
// no two operations share one and no surface keeps a table of its own. Every symbol is one the app already draws or a long-standing
// system symbol (an unknown name logs in AppKit on every editor open, as `person.crop.rectangle.badge.xmark` did on 2026-08-29).
extension ImageEditOperation {
    /// Op name (the engine's chain vocabulary, plus the two rotate directions the toolbar offers) -> SF Symbol.
    static let glyphs: [String: String] = [
        "crop": "crop",
        "rotate": "rotate.right",
        "rotate_left": "rotate.left",
        "straighten": "crop.rotate",
        "enhance": "wand.and.stars",
        "fuzzy_clean": "sparkles",
        "remove_background": "scissors",
        "segment": "square.split.bottomrightquarter",
        "flip_horizontal": "arrow.left.and.right.righttriangle.left.righttriangle.right",
        "flip_vertical": "arrow.up.and.down.righttriangle.up.righttriangle.down",
        "grayscale": "circle.lefthalf.filled",
        "contrast": "circle.righthalf.filled",
        "brightness": "sun.max",
        "auto_levels": "slider.horizontal.below.rectangle",
        "sharpen": "triangle",
        "denoise": "circle.dotted",
        "binarise": "square.lefthalf.filled",
        "adaptive_binarize": "square.righthalf.filled",
        "stain_flatten": "drop",
        "ruled_lines": "line.3.horizontal",
        "bleed_through": "square.on.square",
        "auto_crop_border": "rectangle.dashed",
        "square": "viewfinder",
        "mark_blank": "doc"
    ]

    /// The glyph for `kind`; an op the table does not know draws the generic adjustment glyph.
    static func glyph(for kind: String) -> String { glyphs[kind] ?? "slider.horizontal.3" }
}
