import Foundation
import SwiftUI
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
    /// silently lose on save (user feedback 2026-04-26).
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

    // MARK: - WebKit boundary (#2454)

    /// Convert stored content to an HTML string safe for `WKWebView.loadHTMLString`.
    /// RTF source (detected by the `{\rtf` prefix) is parsed via `NSAttributedString`
    /// and re-serialised as HTML so WebKit renders formatted text instead of raw RTF
    /// control words (#2454). Plain text and any content that fails RTF parsing pass
    /// through unchanged — the caller is responsible for HTML-escaping plain text
    /// before inserting it into a larger HTML document if needed.
    static func htmlForWebView(_ content: String) -> String {
        guard content.hasPrefix("{\\rtf"),
              let data = content.data(using: .utf8),
              let attr = try? NSAttributedString(
                  data: data,
                  options: [.documentType: NSAttributedString.DocumentType.rtf],
                  documentAttributes: nil
              ),
              let htmlData = try? attr.data(
                  from: NSRange(location: 0, length: attr.length),
                  documentAttributes: [.documentType: NSAttributedString.DocumentType.html]
              ),
              let html = String(data: htmlData, encoding: .utf8)
        else { return content }
        return html
    }

    // MARK: - Plain-text boundary (#2317)

    /// Plain-text projection of stored content for native readers that render
    /// selectable plain text (`PageContentPane`, `DocumentTextReader`) and must
    /// not leak raw RTF. RTF source (`{\rtf` prefix) is decoded so control words
    /// and `\'xx` escapes resolve to real characters (`\'e1` → á); plain text
    /// short-circuits unchanged so the common case pays no decode cost (#2317).
    static func plainText(_ content: String) -> String {
        guard content.hasPrefix("{\\rtf") else { return content }
        return decode(content).string
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
        encode(normalizedNSAttributedString(from: attr))
    }

    /// Bridge a SwiftUI `AttributedString` to an `NSAttributedString` with all
    /// formatting expressed as **concrete AppKit attributes** so it survives RTF
    /// serialization (#2494).
    ///
    /// The macOS 26 `TextEditor(text:)` format ribbon (Bold / Italic / underline
    /// / strikethrough / colour) records formatting as SwiftUI *semantic*
    /// attributes — `inlinePresentationIntent` and the `SwiftUI.UnderlineStyle` /
    /// `StrikethroughStyle` / `ForegroundColor` scope keys. A plain
    /// `NSAttributedString(attr)` bridge keeps those as opaque `SwiftUI.*` keys
    /// that RTF can't encode, so `attr.data(...rtf...)` silently drops them —
    /// bold typed in the inspector round-tripped back as plain text (#2494). We
    /// fold each run's semantic attributes onto a real `NSFont` trait /
    /// `.underlineStyle` / `.strikethroughStyle` / `.foregroundColor`, preserving
    /// any concrete font already present (e.g. from decoded RTF). Runs with no
    /// formatting stay attribute-free, so unformatted text still encodes as the
    /// bare plain string and storage stays human-readable.
    private static func normalizedNSAttributedString(from attr: AttributedString) -> NSAttributedString {
        let result = NSMutableAttributedString(attr)
        #if canImport(AppKit)
        let fontManager = NSFontManager.shared
        for run in attr.runs {
            let nsRange = NSRange(run.range, in: attr)
            guard nsRange.location != NSNotFound, nsRange.length > 0 else { continue }

            if let intent = run.inlinePresentationIntent {
                var font = (result.attribute(.font, at: nsRange.location, effectiveRange: nil) as? NSFont)
                    ?? NSFont.preferredFont(forTextStyle: .body)
                if intent.contains(.stronglyEmphasized) {
                    font = fontManager.convert(font, toHaveTrait: .boldFontMask)
                }
                if intent.contains(.emphasized) {
                    font = fontManager.convert(font, toHaveTrait: .italicFontMask)
                }
                result.addAttribute(.font, value: font, range: nsRange)
                if intent.contains(.strikethrough) {
                    result.addAttribute(.strikethroughStyle, value: NSUnderlineStyle.single.rawValue, range: nsRange)
                }
            }
            if run.underlineStyle != nil {
                result.addAttribute(.underlineStyle, value: NSUnderlineStyle.single.rawValue, range: nsRange)
            }
            if run.strikethroughStyle != nil {
                result.addAttribute(.strikethroughStyle, value: NSUnderlineStyle.single.rawValue, range: nsRange)
            }
            if let color = run.foregroundColor {
                result.addAttribute(.foregroundColor, value: NSColor(color), range: nsRange)
            }
        }
        #endif
        return result
    }
}
