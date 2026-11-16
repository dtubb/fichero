@testable import Fichero
import Foundation
import Testing

/// One icon table for every place a tool or its step is shown (`preview.edit.tool.one-icon-table`, #1420).
struct ImageEditToolSetTests {
    /// The engine's chain vocabulary (`_OPERATION_MODELS` and `_PARAMETERLESS_OPERATIONS`).
    private static let chainOperations = [
        "adaptive_binarize", "auto_crop_border", "auto_levels", "binarise", "bleed_through", "brightness", "contrast", "crop", "denoise",
        "enhance", "flip_horizontal", "flip_vertical", "fuzzy_clean", "grayscale", "mark_blank", "remove_background", "rotate",
        "ruled_lines", "segment", "sharpen", "square", "stain_flatten", "straighten"
    ]

    @Test("every chain operation has a glyph of its own")
    func everyOperationHasAGlyph() {
        for kind in Self.chainOperations {
            #expect(ImageEditOperation.glyphs[kind] != nil, "\(kind) has no glyph")
        }
    }

    @Test("no two operations share a glyph")
    func noTwoShareAGlyph() {
        let glyphs = ImageEditOperation.glyphs.values.sorted()
        #expect(Set(glyphs).count == glyphs.count)
    }

    @Test("an op the table does not know draws the generic adjustment glyph")
    func unknownIsGeneric() {
        #expect(ImageEditOperation.glyph(for: "no_such_op") == "slider.horizontal.3")
    }
}
