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
