#if os(macOS)
import AppKit

/// A recognised word drawn IN its box, the size of the word it stands for (2026-09-01): the largest
/// size that fits the box in BOTH axes, never truncated. In DOCUMENT space, so it is page ink and
/// scales with the page like the pixels under it. Set in the line's resolved direction (#5411): a
/// vertical line is a column inside its box, laid out by `SegmentLabel`, the hover label's own rule.
/// Drawn by `DocumentOverlayView`.
enum InlineWords {
    static let plateAlpha: CGFloat = 0.6
    /// The share of the box's cross-axis the glyphs take: a row's height, a column's width. Leaves a
    /// hairline of plate either side.
    static let heightFill: CGFloat = 0.82

    /// Where and how big a reading is set in its box.
    struct Layout: Equatable {
        /// The text as drawn: isolated, and for a vertical line one grapheme per row (`SegmentLabel`).
        let text: String
        let vertical: Bool
        let rightToLeft: Bool
        let fontSize: CGFloat
        /// The measured text, inside the box: centred across a column, from the leading edge of a row
        /// (the right edge for `rtl`), centred in the box's other axis.
        let frame: CGRect
    }

    /// `text` set in `rect` in `direction`. `measure` is the drawn size of a string at a point size.
    static func layout(
        _ text: String, direction: String?, in rect: CGRect, measure: (String, CGFloat) -> CGSize
    ) -> Layout {
        let label = SegmentLabel.layout(text, direction: direction)
        let size = fittedSize(label.text, vertical: label.vertical, in: rect, measure: measure)
        let measured = measure(label.text, size)
        let originX: CGFloat
        if label.vertical {
            originX = rect.midX - measured.width / 2
        } else {
            originX = label.rightToLeft ? rect.maxX - measured.width : rect.minX
        }
        let frame = CGRect(x: originX, y: rect.midY - measured.height / 2,
                           width: measured.width, height: measured.height)
        return Layout(text: label.text, vertical: label.vertical, rightToLeft: label.rightToLeft,
                      fontSize: size, frame: frame)
    }

    /// The font size `text` is drawn at in `rect`: from the box's cross-axis (a row's height, a column's
    /// width), then shrunk (up to three passes, biased under the box) while it overflows the box in
    /// EITHER axis -- a column too short for its graphemes, a row too narrow for its word, a many-row
    /// reading taller than its box (#5411).
    static func fittedSize(
        _ text: String, vertical: Bool = false, in rect: CGRect, measure: (String, CGFloat) -> CGSize
    ) -> CGFloat {
        var size = max((vertical ? rect.width : rect.height) * heightFill, 0.5)
        var measured = measure(text, size)
        var passes = 0
        while measured.width > rect.width || measured.height > rect.height,
              measured.width > 0, measured.height > 0, passes < 3 {
            size *= min(rect.width / measured.width, rect.height / measured.height) * 0.98
            measured = measure(text, size)
            passes += 1
        }
        return size
    }

    /// The attributes a reading is drawn with at `size`. The size is COMPUTED from the box (it has to
    /// match the word it stands in for, at any zoom), so this is the one place a point size is given
    /// rather than a semantic text style: no text style describes "as tall as this box".
    private static func attributes(_ size: CGFloat, alignment: NSTextAlignment) -> [NSAttributedString.Key: Any] {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = alignment
        return [.font: NSFont.systemFont(ofSize: size), .paragraphStyle: paragraph]
    }

    static func draw(_ text: String, direction: String?, in rect: CGRect) {
        let alignment: NSTextAlignment
        if SegmentLabel.layout(text, direction: direction).vertical {
            alignment = .center
        } else {
            alignment = direction == "rtl" ? .right : .left
        }
        let placed = layout(text, direction: direction, in: rect) { string, points in
            (string as NSString).size(withAttributes: attributes(points, alignment: alignment))
        }
        var drawn = attributes(placed.fontSize, alignment: alignment)
        drawn[.foregroundColor] = NSColor.labelColor
        // Drawn across the box's full width with the alignment placing it, so a rounding hair in the
        // measure can never wrap a row. Text is set from the frame's top (high y in this unflipped
        // space), so the slack goes below, where it can never clip the last row.
        let slack = placed.fontSize * 0.2
        let frame = CGRect(x: rect.minX, y: placed.frame.minY - slack,
                           width: rect.width, height: placed.frame.height + slack)
        (placed.text as NSString).draw(in: frame, withAttributes: drawn)
    }
}
#endif
