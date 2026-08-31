import SwiftUI

// MARK: - Per-kind annotation rendering (Daniel, 2026-08-30, reading-markup
// rulings: "saved markup should LOOK like what it is")
//
// Every saved annotation used to render as the same accent box wash. This
// layer renders BY KIND: a highlight is a wash in its saved color, an
// underline a bar under the words, a strikethrough a bar through them, a
// line a diagonal stroke, a check a ✓ glyph in the margin beside its line,
// a note small text in the margin (ruling 3) or a glyph at its anchor, a
// star a star. The pure math lives in `AnnotationMarkGeometry` for tests.

/// What the mark layer needs from a `DocumentAnnotation` — kind, region,
/// color, rating, text. One value type so the image layer and the PDF
/// renderer read the same shape.
struct AnnotationMark: Identifiable {
    let id: String
    let kind: AnnotationKind
    /// Normalized `[x, y, w, h]`; nil = whole-page mark (bookmark).
    let rect: [Double]?
    /// Engine-persisted `#RRGGBB[AA]`, when the kind carries one.
    let color: String?
    let rating: Int?
    let text: String

    init(annotation: DocumentAnnotation) {
        id = annotation.id
        kind = annotation.kind
        rect = annotation.regionRect
        color = annotation.color
        rating = annotation.rating
        text = annotation.text ?? ""
    }

    /// Test/local construction.
    init(
        id: String, kind: AnnotationKind, rect: [Double]?,
        color: String? = nil, rating: Int? = nil, text: String = ""
    ) {
        self.id = id
        self.kind = kind
        self.rect = rect
        self.color = color
        self.rating = rating
        self.text = text
    }
}

/// 0–1 color components parsed from an engine `#RRGGBB[AA]` string.
struct AnnotationRGBA: Equatable {
    let red: Double
    let green: Double
    let blue: Double
    let alpha: Double
}

/// Pure geometry + parsing behind the per-kind rendering. No SwiftUI types
/// beyond CoreGraphics, so every rule is unit-testable.
enum AnnotationMarkGeometry {
    /// Parse `#RRGGBB` / `#RRGGBBAA` into 0–1 components. nil on anything
    /// else — a bad color renders as the default, never crashes a layer.
    static func rgba(hex: String?) -> AnnotationRGBA? {
        guard let hex, hex.hasPrefix("#"), hex.count == 7 || hex.count == 9,
              hex.dropFirst().allSatisfy(\.isHexDigit) else { return nil }
        var value: UInt64 = 0
        guard Scanner(string: String(hex.dropFirst())).scanHexInt64(&value) else { return nil }
        if hex.count == 7 { value = value << 8 | 0xFF }
        return AnnotationRGBA(
            red: Double((value >> 24) & 0xFF) / 255,
            green: Double((value >> 16) & 0xFF) / 255,
            blue: Double((value >> 8) & 0xFF) / 255,
            alpha: Double(value & 0xFF) / 255
        )
    }

    /// A 2pt bar along the box's BOTTOM edge (top-left-origin view space).
    static func underlineBar(in rect: CGRect, thickness: CGFloat = 2) -> CGRect {
        CGRect(x: rect.minX, y: rect.maxY - thickness, width: rect.width, height: thickness)
    }

    /// A 2pt bar through the box's vertical MIDDLE.
    static func strikethroughBar(in rect: CGRect, thickness: CGFloat = 2) -> CGRect {
        CGRect(x: rect.minX, y: rect.midY - thickness / 2, width: rect.width, height: thickness)
    }

    /// ✓ / ✓✓ / ✓✓✓ for the saved rating (clamped 1–3).
    static func checkGlyph(rating: Int?) -> String {
        String(repeating: "✓", count: min(max(rating ?? 1, 1), 3))
    }

    /// Ruling 3: a note whose box sits in the OUTER 12% of the page width is
    /// a margin note — its text renders small in the margin, not as a box.
    /// The box's horizontal CENTER decides, so a note straddling the edge of
    /// the margin still counts.
    static func isMarginNote(rect: [Double], marginFraction: Double = 0.12) -> Bool {
        guard rect.count >= 4 else { return false }
        let centerX = rect[0] + rect[2] / 2
        return centerX <= marginFraction || centerX >= 1 - marginFraction
    }
}

/// Comma-separated tag entry → clean tag list (coding v1, ruling 4).
/// Trimmed, empties dropped, order kept, duplicates dropped case-insensitively.
enum AnnotationTagParsing {
    static func parse(_ input: String) -> [String] {
        var seen = Set<String>()
        return input.split(separator: ",").compactMap { piece in
            let tag = piece.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !tag.isEmpty, seen.insert(tag.lowercased()).inserted else { return nil }
            return tag
        }
    }
}

/// Word-boundary marquee (ruling 2): which FULL-LIST indices of a geometry's
/// boxes a normalized drag band selects — word-level boxes only, so the
/// selection means words, and the region-delete path can address them.
enum AnnotationWordSelection {
    static func wordIndices(inBand band: [Double], boxes: [OCRGeometryBox]) -> [Int] {
        guard band.count >= 4 else { return [] }
        return boxes.enumerated()
            .filter { $0.element.level == "word" && AnnotationWordSnap.intersects(band, $0.element.bbox) }
            .map(\.offset)
    }
}

// MARK: - The layer

/// Draws saved annotations BY KIND over the image canvas. Display-only
/// (`allowsHitTesting(false)` throughout); the host frames it to the drawn
/// image rect and clips, same as every box overlay.
struct AnnotationMarkLayer: View {
    let marks: [AnnotationMark]
    /// Normalized sub-rect of the image currently visible (zoom/pan window).
    let visible: CGRect

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                ForEach(marks) { mark in
                    // Display-only, EXCEPT notes: their `.help` tooltip
                    // (the full text) needs hover hit-testing to fire.
                    markView(mark, in: geo.size)
                        .allowsHitTesting(mark.kind == .note)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
    }

    @ViewBuilder
    private func markView(_ mark: AnnotationMark, in size: CGSize) -> some View {
        if let box = mark.rect,
           let rect = BoundingBoxGeometry.viewRect(normalized: box, in: size, visible: visible) {
            switch mark.kind {
            case .highlight:
                RoundedRectangle(cornerRadius: 2)
                    .fill(washColor(mark))
                    .frame(width: rect.width, height: rect.height)
                    .offset(x: rect.minX, y: rect.minY)
            case .underline:
                bar(AnnotationMarkGeometry.underlineBar(in: rect), mark: mark)
            case .strikethrough:
                bar(AnnotationMarkGeometry.strikethroughBar(in: rect), mark: mark)
            case .line:
                Path { path in
                    path.move(to: CGPoint(x: rect.minX, y: rect.minY))
                    path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
                }
                .stroke(strokeColor(mark), lineWidth: 2)
            case .rating:
                // ✓ in the right margin BESIDE its line — accent, constant
                // size (an adornment, not page ink).
                Text(AnnotationMarkGeometry.checkGlyph(rating: mark.rating))
                    .font(.caption.bold())
                    .foregroundStyle(Color.accentColor)
                    .position(x: size.width - 14, y: rect.midY)
            case .note:
                noteView(mark, box: box, rect: rect, in: size)
            case .bookmark:
                starGlyph
                    .position(x: rect.maxX - 8, y: rect.minY + 8)
            default:
                // Unknown/legacy kinds keep the old honest accent box.
                RoundedRectangle(cornerRadius: 2)
                    .stroke(Color.accentColor, lineWidth: 1.5)
                    .background(Color.accentColor.opacity(0.12))
                    .frame(width: rect.width, height: rect.height)
                    .offset(x: rect.minX, y: rect.minY)
            }
        } else if mark.kind == .bookmark {
            // Whole-page star: top-right of the page.
            starGlyph
                .position(x: size.width - 16, y: 16)
        }
    }

    /// Margin notes (ruling 3): small readable text IN the margin — "write
    /// directly in the margins, not with a square box". Elsewhere (or with no
    /// text yet) a small note glyph marks the anchor.
    @ViewBuilder
    private func noteView(_ mark: AnnotationMark, box: [Double], rect: CGRect, in size: CGSize) -> some View {
        if AnnotationMarkGeometry.isMarginNote(rect: box), !mark.text.isEmpty {
            Text(mark.text)
                .font(.caption2)
                .foregroundStyle(.primary)
                .lineLimit(3)
                .frame(width: max(rect.width, size.width * 0.11), alignment: .leading)
                .offset(x: rect.minX, y: rect.minY)
                .help(mark.text)
        } else {
            Image(systemName: "note.text")
                .font(.caption)
                .foregroundStyle(Color.accentColor)
                .position(x: rect.minX + 8, y: rect.minY + 8)
                .help(mark.text)
        }
    }

    private func bar(_ barRect: CGRect, mark: AnnotationMark) -> some View {
        Rectangle()
            .fill(strokeColor(mark))
            .frame(width: barRect.width, height: barRect.height)
            .offset(x: barRect.minX, y: barRect.minY)
    }

    /// Saved color as a translucent wash; hex alpha wins when present,
    /// otherwise a readable 0.3. Default: the classic yellow highlighter.
    private func washColor(_ mark: AnnotationMark) -> Color {
        guard let rgba = AnnotationMarkGeometry.rgba(hex: mark.color) else {
            return Color.yellow.opacity(0.3)
        }
        let alpha = rgba.alpha < 1 ? rgba.alpha : 0.3
        return Color(red: rgba.red, green: rgba.green, blue: rgba.blue).opacity(alpha)
    }

    /// Saved color at full strength for bars and strokes; accent by default.
    private func strokeColor(_ mark: AnnotationMark) -> Color {
        guard let rgba = AnnotationMarkGeometry.rgba(hex: mark.color) else {
            return Color.accentColor
        }
        return Color(red: rgba.red, green: rgba.green, blue: rgba.blue).opacity(rgba.alpha)
    }

    private var starGlyph: some View {
        Image(systemName: "star.fill")
            .font(.caption)
            .foregroundStyle(Color.yellow)
    }
}
