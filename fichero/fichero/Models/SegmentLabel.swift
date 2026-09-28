import FicheroAPIClient
import Foundation

/// How a segment's text is laid out in a label ON the image -- the hover label and the fitted words (#5199,
/// Daniel on the chinese-vertical page: '登庸九' drawn across a vertical column). By the line's RESOLVED
/// direction, the engine's cascade as the page text serves it per block (`GET .../text`), never guessed from
/// the characters: a column of Han is vertical, a Syriac line right to left, and every label is a Unicode
/// isolate so a mixed line resolves on its own and never reorders what is around it.
nonisolated enum SegmentLabel {
    /// Each segment's resolved direction, from the page text's blocks: every span in a block is written in
    /// the block's direction.
    static func directions(from text: Components.Schemas.DerivedText) -> [String: String] {
        var out: [String: String] = [:]
        for block in text.blocks ?? [] {
            guard let direction = block.direction else { continue }
            for span in block.spans { out[span.segmentId] = direction }
        }
        return out
    }

    struct Layout: Equatable {
        /// The text to draw: isolated, and for a vertical line one grapheme per row.
        let text: String
        let vertical: Bool
        let rightToLeft: Bool
    }

    /// `text` laid out in `direction` (nil: not resolved -- the first strong character decides, isolated).
    static func layout(_ text: String, direction: String?) -> Layout {
        switch direction {
        case "ttb", "btt":
            // A column: one grapheme per row, upright, read down (up for btt).
            let rows = text.filter { !$0.isWhitespace }.map(String.init)
            return Layout(text: (direction == "btt" ? rows.reversed() : rows).joined(separator: "\n"),
                          vertical: true, rightToLeft: false)
        case "rtl":
            return Layout(text: "\u{2067}" + text + "\u{2069}", vertical: false, rightToLeft: true)
        case "ltr":
            return Layout(text: "\u{2066}" + text + "\u{2069}", vertical: false, rightToLeft: false)
        default:
            return Layout(text: "\u{2068}" + text + "\u{2069}", vertical: false, rightToLeft: false)
        }
    }
}
