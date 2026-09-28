import CoreText
import FicheroAPIClient
import Observation
import SwiftUI

/// The fonts the engine bundles for scripts the system lacks (#5210, #5206): Junicode for MUFI's
/// private-use letters, Noto Sans for Syriac, Mongolian, Coptic and Cherokee. They are the SAME files the
/// Reader's `@font-face` names, fetched from the engine's `GET /view/fonts/{name}`, so the app vendors
/// nothing of its own and a remote engine serves them too.
///
/// Registering a font with the process does NOT put it in the system's fallback (U+F1AC stays a box), so
/// the faces are added as a CASCADE after the system font: a character the system font lacks is looked
/// up in the system's own cascade first, then in these, so the Chinese, Syriac and Latin the system
/// already draws keep their fonts. Text in the Inspector, the Segments rows and on the image reads its
/// font from here.
@MainActor
@Observable
final class BundledFonts {
    static let shared = BundledFonts()

    /// The engine's allowlist (`views.py` `BUNDLED_FONTS`), in cascade order.
    static let names = [
        "JunicodeVF-Roman.woff2", "NotoSansSyriac-VF.ttf", "NotoSansMongolian-Regular.ttf",
        "NotoSansCoptic-Regular.ttf", "NotoSansCherokee-VF.ttf"
    ]

    /// The faces fetched so far; empty until an engine has answered.
    private(set) var cascade: [CTFontDescriptor] = []

    /// Fetch the faces once, from the first engine that serves them. A face the engine does not serve is
    /// left out (an older engine has no route): the text still draws, with the system's fonts.
    func load(from client: FicheroClient) async {
        guard cascade.isEmpty else { return }
        var found: [CTFontDescriptor] = []
        for name in Self.names {
            guard let (status, data) = try? await client.requestData(path: "/view/fonts/\(name)"),
                  status == 200 else { continue }
            found += Self.descriptors(in: data)
        }
        cascade = found
    }

    /// A semantic style with the bundled faces after the system's own.
    func font(_ style: Font.TextStyle) -> Font {
        Self.font(style, cascade: cascade)
    }

    /// A fixed size (text fitted to a box on the image) with the bundled faces after the system's own.
    func font(size: CGFloat) -> Font {
        Self.font(size: size, cascade: cascade)
    }

    /// A font file's first face (a variable font's default instance).
    nonisolated static func descriptors(in data: Data) -> [CTFontDescriptor] {
        let all = CTFontManagerCreateFontDescriptorsFromData(data as CFData) as? [CTFontDescriptor] ?? []
        return Array(all.prefix(1))
    }

    nonisolated static func font(_ style: Font.TextStyle, cascade: [CTFontDescriptor]) -> Font {
        guard !cascade.isEmpty else { return .system(style) }
        return Font(ctFont(base: systemDescriptor(style), size: 0, cascade: cascade))
    }

    nonisolated static func font(size: CGFloat, cascade: [CTFontDescriptor]) -> Font {
        guard !cascade.isEmpty else { return .system(size: size) }
        let base = CTFontCopyFontDescriptor(CTFontCreateUIFontForLanguage(.system, size, nil)
            ?? CTFontCreateWithName("Helvetica" as CFString, size, nil))
        return Font(ctFont(base: base, size: size, cascade: cascade))
    }

    /// The system font for `style` with `cascade` as its fallbacks. Size 0 keeps the style's own size.
    nonisolated static func ctFont(base: CTFontDescriptor, size: CGFloat, cascade: [CTFontDescriptor]) -> CTFont {
        let descriptor = CTFontDescriptorCreateCopyWithAttributes(
            base, [kCTFontCascadeListAttribute: cascade] as CFDictionary
        )
        return CTFontCreateWithFontDescriptor(descriptor, size, nil)
    }

    /// The system's descriptor for a semantic style.
    nonisolated static func systemDescriptor(_ style: Font.TextStyle) -> CTFontDescriptor {
        #if os(macOS)
        NSFont.preferredFont(forTextStyle: platformStyles[style] ?? .body).fontDescriptor as CTFontDescriptor
        #else
        UIFont.preferredFont(forTextStyle: platformStyles[style] ?? .body).fontDescriptor as CTFontDescriptor
        #endif
    }

    #if os(macOS)
    private nonisolated static let platformStyles: [Font.TextStyle: NSFont.TextStyle] = [
        .largeTitle: .largeTitle, .title: .title1, .title2: .title2, .title3: .title3, .headline: .headline,
        .subheadline: .subheadline, .callout: .callout, .footnote: .footnote, .caption: .caption1, .caption2: .caption2
    ]
    #else
    private nonisolated static let platformStyles: [Font.TextStyle: UIFont.TextStyle] = [
        .largeTitle: .largeTitle, .title: .title1, .title2: .title2, .title3: .title3, .headline: .headline,
        .subheadline: .subheadline, .callout: .callout, .footnote: .footnote, .caption: .caption1, .caption2: .caption2
    ]
    #endif
}
