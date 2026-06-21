import Foundation
#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif

/// Encode/decode helpers for artifact rich-text content, extracted from
/// `ArtifactPanel` so they can be unit-tested directly (#710).
///
/// Storage contract: an artifact's `content` field is either
/// - plain text (no RTF wrapper) when the user added no formatting, or
/// - inline RTF source (`{\rtf...}`, not base64) when formatting is present,
///   so the field stays human-readable for plain text and round-trips
///   losslessly when the user added bold/italic/underline or ruler edits.
enum ArtifactRichTextCodec {
    /// Decode a stored content string into an `NSAttributedString`. RTF source
    /// (detected by the `{\rtf` prefix) is parsed as rich text; anything else
    /// is treated as plain text.
    static func decode(_ content: String) -> NSAttributedString {
        if content.hasPrefix("{\\rtf"),
           let data = content.data(using: .utf8),
           let attr = try? NSAttributedString(
            data: data,
            options: [.documentType: NSAttributedString.DocumentType.rtf],
            documentAttributes: nil
           ) {
            return attr
        }
        return NSAttributedString(string: content)
    }

    /// Encode an `NSAttributedString` back to a content string. Returns the
    /// plain string when no formatting is present; otherwise inline RTF source.
    ///
    /// Custom paragraph styles (ruler tab stops, indents, line spacing changes)
    /// MUST round-trip through RTF — an earlier version excluded
    /// `.paragraphStyle` from the formatting check, which made ruler edits
    /// silently lose on save (Daniel feedback 2026-04-26).
    static func encode(_ attr: NSAttributedString) -> String {
        let fullRange = NSRange(location: 0, length: attr.length)
        let plain = attr.string

        var hasFormatting = false
        let defaultPara = NSParagraphStyle.default
        attr.enumerateAttributes(in: fullRange) { attrs, _, stop in
            for (key, value) in attrs {
                if key == .paragraphStyle {
                    if let para = value as? NSParagraphStyle, para != defaultPara {
                        hasFormatting = true
                    }
                    continue
                }
                hasFormatting = true
            }
            if hasFormatting { stop.pointee = true }
        }

        if !hasFormatting { return plain }

        guard let data = try? attr.data(
            from: fullRange,
            documentAttributes: [.documentType: NSAttributedString.DocumentType.rtf]
        ), let rtfString = String(data: data, encoding: .utf8) else {
            return plain
        }
        return rtfString
    }

    // MARK: - AttributedString boundary (#2453)

    /// Decode stored content into a SwiftUI-native `AttributedString` for the
    /// unified `TextEditor(text:)`. Storage stays portable RTF/plain via the
    /// `NSAttributedString` path above — raw RTF never reaches a view (#2454).
    static func decodeAttributed(_ content: String) -> AttributedString {
        AttributedString(decode(content))
    }

    /// Encode the editor's `AttributedString` back to the stored content string
    /// (plain when unformatted, inline RTF otherwise).
    static func encodeAttributed(_ attr: AttributedString) -> String {
        encode(NSAttributedString(attr))
    }
}
