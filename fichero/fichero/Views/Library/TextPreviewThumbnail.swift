import SwiftUI

// MARK: - TextPreviewThumbnail

/// Monospaced text thumbnail for JSON/text documents when no image thumbnail exists (#625).
struct TextPreviewThumbnail: View {
    let text: String

    private static let previewLimit = 600

    private var displayText: String {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        if trimmed.hasPrefix("{") || trimmed.hasPrefix("["),
           let data = trimmed.data(using: .utf8),
           let obj = try? JSONSerialization.jsonObject(with: data),
           let pretty = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted]),
           let str = String(data: pretty, encoding: .utf8) {
            return String(str.prefix(Self.previewLimit))
        }
        return String(trimmed.prefix(Self.previewLimit))
    }

    var body: some View {
        Text(displayText)
            .font(.system(size: 6, design: .monospaced))
            .foregroundStyle(.primary)
            .lineSpacing(1)
            .padding(4)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .clipped()
            // Reads as a PAGE (Finder's text-file icon): white sheet with a
            // hairline edge, so the tiny text isn't floating on the canvas.
            .background(Color(.textBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .strokeBorder(Color.primary.opacity(0.15), lineWidth: 0.5)
            )
            .allowsHitTesting(false)
    }
}

// MARK: - PDFStackSheets

/// How many sheets peek behind a container's cover for `childCount` items —
/// the stack's DEPTH says roughly how big the document/folder is (Daniel,
/// 2026-08-09: "we know that a 500 page pdf is larger than a 2 page pdf").
/// File scope so Swift Testing can call it off-main.
func stackSheetCount(forChildCount childCount: Int) -> Int {
    switch childCount {
    case ..<2: 0
    case 2..<10: 1
    case 10..<50: 2
    default: 3
    }
}

/// Sheets peeking behind a PDF's cover thumbnail (or a folder's glyph) so a
/// multi-item container reads as a STACK, not one loose page (Daniel,
/// 2026-08-09: "make it so the PDF icons are stacked"). Depth follows the
/// child count. Pure backdrop — no hit-testing, at most three rounded rects.
struct PDFStackSheets: View {
    var scale: CGFloat = 1.0
    var count: Int = 2

    var body: some View {
        ZStack {
            ForEach((1...max(1, min(count, 3))).reversed(), id: \.self) { depth in
                sheet.offset(x: CGFloat(depth) * 3 * scale, y: CGFloat(depth) * -3 * scale)
            }
        }
        .allowsHitTesting(false)
    }

    private var sheet: some View {
        RoundedRectangle(cornerRadius: 2)
            .fill(Color(.textBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .strokeBorder(Color.primary.opacity(0.15), lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.12), radius: 1, y: 0.5)
    }
}
