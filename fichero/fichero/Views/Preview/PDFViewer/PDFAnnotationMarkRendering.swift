#if os(macOS)
import AppKit
import PDFKit

// MARK: - Per-kind PDF annotation rendering (Daniel, 2026-08-30, reading-
// markup rulings) — the PDF half of `AnnotationMarkLayer`: the same marks,
// drawn as native PDFKit annotations so they position correctly at any zoom.

enum PDFAnnotationMarkRendering {
    /// Build the PDFKit annotations for one saved mark, in PDF page space
    /// (origin bottom-left; `PDFRegionGeometry.pageRect` does the flip).
    /// The caller stamps `userName` and adds them to the page.
    static func annotations(for mark: AnnotationMark, pageSize: CGSize) -> [PDFAnnotation] {
        let rect = mark.rect.flatMap { PDFRegionGeometry.pageRect(normalized: $0, pageSize: pageSize) }
        if mark.kind == .bookmark { return [bookmarkStar(rect: rect, pageSize: pageSize)] }
        guard let rect else { return [] }
        switch mark.kind {
        case .highlight:
            return [highlightWash(rect, mark: mark)]
        case .underline:
            // Visual bottom edge = minY in PDF's bottom-up page space.
            return [bar(CGRect(x: rect.minX, y: rect.minY, width: rect.width, height: 2), mark: mark)]
        case .strikethrough:
            return [bar(CGRect(x: rect.minX, y: rect.midY - 1, width: rect.width, height: 2), mark: mark)]
        case .line:
            return [diagonal(rect, mark: mark)]
        case .rating:
            // ✓ in the right margin BESIDE its line (ruling 1's glyphs).
            return [glyph(AnnotationMarkGeometry.checkGlyph(rating: mark.rating),
                          in: CGRect(x: pageSize.width - 34, y: rect.midY - 8, width: 32, height: 16),
                          color: .controlAccentColor, fontSize: 11)]
        case .note:
            return [note(rect, mark: mark)]
        default:
            return [legacyBox(rect)]
        }
    }

    private static func highlightWash(_ rect: CGRect, mark: AnnotationMark) -> PDFAnnotation {
        let tint = color(for: mark, defaultColor: .systemYellow)
        let wash = PDFAnnotation(bounds: rect, forType: .square, withProperties: nil)
        wash.color = tint.withAlphaComponent(0)
        wash.interiorColor = tint.withAlphaComponent(0.3)
        return wash
    }

    private static func diagonal(_ rect: CGRect, mark: AnnotationMark) -> PDFAnnotation {
        let line = PDFAnnotation(bounds: rect, forType: .line, withProperties: nil)
        // Visual top-left → bottom-right = (minX, maxY) → (maxX, minY).
        line.startPoint = CGPoint(x: rect.minX, y: rect.maxY)
        line.endPoint = CGPoint(x: rect.maxX, y: rect.minY)
        line.color = color(for: mark, defaultColor: .controlAccentColor)
        let border = PDFBorder()
        border.lineWidth = 2
        line.border = border
        return line
    }

    /// Margin writing (ruling 3): small text IN the margin; elsewhere a
    /// native note-icon annotation carrying the text.
    private static func note(_ rect: CGRect, mark: AnnotationMark) -> PDFAnnotation {
        if let box = mark.rect, AnnotationMarkGeometry.isMarginNote(rect: box), !mark.text.isEmpty {
            let noteRect = CGRect(
                x: rect.minX, y: rect.minY,
                width: max(rect.width, 60), height: max(rect.height, 28)
            )
            return glyph(mark.text, in: noteRect, color: .labelColor, fontSize: 7)
        }
        let anchor = PDFAnnotation(
            bounds: CGRect(x: rect.minX, y: rect.maxY - 16, width: 16, height: 16),
            forType: .text, withProperties: nil
        )
        anchor.iconType = .note
        anchor.color = .controlAccentColor
        anchor.contents = mark.text
        return anchor
    }

    /// Star at its rect's top-right, or the page's when whole-page.
    private static func bookmarkStar(rect: CGRect?, pageSize: CGSize) -> PDFAnnotation {
        let starRect = rect.map { CGRect(x: $0.maxX - 16, y: $0.maxY - 16, width: 16, height: 16) }
            ?? CGRect(x: pageSize.width - 26, y: pageSize.height - 26, width: 20, height: 20)
        return glyph("★", in: starRect, color: .systemYellow, fontSize: 12)
    }

    /// Unknown/legacy kinds keep the old honest accent box.
    private static func legacyBox(_ rect: CGRect) -> PDFAnnotation {
        let box = PDFAnnotation(bounds: rect, forType: .square, withProperties: nil)
        box.color = NSColor.controlAccentColor
        box.interiorColor = NSColor.controlAccentColor.withAlphaComponent(0.12)
        return box
    }

    private static func bar(_ rect: CGRect, mark: AnnotationMark) -> PDFAnnotation {
        let tint = color(for: mark, defaultColor: .controlAccentColor)
        let bar = PDFAnnotation(bounds: rect, forType: .square, withProperties: nil)
        bar.color = tint
        bar.interiorColor = tint
        return bar
    }

    private static func glyph(
        _ text: String, in rect: CGRect, color: NSColor, fontSize: CGFloat
    ) -> PDFAnnotation {
        let annotation = PDFAnnotation(bounds: rect, forType: .freeText, withProperties: nil)
        annotation.contents = text
        annotation.font = NSFont.systemFont(ofSize: fontSize)
        annotation.fontColor = color
        annotation.color = .clear
        annotation.backgroundColor = .clear
        return annotation
    }

    /// The mark's saved `#RRGGBB[AA]`, else the kind's default.
    private static func color(for mark: AnnotationMark, defaultColor: NSColor) -> NSColor {
        guard let rgba = AnnotationMarkGeometry.rgba(hex: mark.color) else { return defaultColor }
        return NSColor(red: rgba.red, green: rgba.green, blue: rgba.blue, alpha: rgba.alpha)
    }
}
#endif
