#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import Foundation
import SwiftUI

extension DocumentKGPaneRoute {
    /// The resolved reader palette + base text size for the current appearance,
    /// bridged from the platform's SEMANTIC colors/fonts so the WebKit reader
    /// matches the native app in light AND dark. Colors, fonts, AND base size are
    /// all injected, on macOS AND iOS — closing the previously-unthemed-reader-
    /// on-iOS gap (#3683).
    struct ReaderTheme {
        let background, panel, text, muted, line, accent, accentSoft: String
        let selectionBg, selectionText: String
        /// Semantic body point size (Dynamic Type on iOS). The Reader font-scale
        /// override (#3681) multiplies this before injection.
        let baseSizePx: Int
    }

    /// A platform SEMANTIC color as an sRGB `rgba(...)` CSS string.
    #if canImport(AppKit)
    private static func cssColor(_ color: NSColor) -> String {
        let resolved = color.usingColorSpace(.sRGB) ?? NSColor.black
        let red = Int((resolved.redComponent * 255).rounded())
        let green = Int((resolved.greenComponent * 255).rounded())
        let blue = Int((resolved.blueComponent * 255).rounded())
        return String(format: "rgba(%d, %d, %d, %.3f)", red, green, blue, resolved.alphaComponent)
    }
    #elseif canImport(UIKit)
    private static func cssColor(_ color: UIColor) -> String {
        let resolved = color.resolvedColor(with: UITraitCollection.current)
        var red: CGFloat = 0, green: CGFloat = 0, blue: CGFloat = 0, alpha: CGFloat = 0
        guard resolved.getRed(&red, green: &green, blue: &blue, alpha: &alpha) else {
            return "rgba(0, 0, 0, 1.000)"
        }
        return String(
            format: "rgba(%d, %d, %d, %.3f)",
            Int((red * 255).rounded()), Int((green * 255).rounded()),
            Int((blue * 255).rounded()), alpha
        )
    }
    #endif

    /// The reader typography font stacks — the single Swift-side source that
    /// keeps the WebKit reader's fonts identical to the app (matches the template
    /// defaults, and now overrides them so both stay in lockstep).
    private static let readerFontSystem =
        "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", system-ui, sans-serif"
    private static let readerFontMono =
        "ui-monospace, \"SF Mono\", SFMono-Regular, Menlo, monospace"

    /// Neutral fallback matching the template's light default, used when no
    /// platform appearance is resolvable.
    private static let fallbackReaderTheme = ReaderTheme(
        background: "rgba(247, 244, 238, 1.000)", panel: "rgba(255, 255, 255, 0.850)",
        text: "rgba(31, 29, 26, 1.000)", muted: "rgba(106, 98, 88, 1.000)",
        line: "rgba(64, 53, 39, 0.140)", accent: "rgba(13, 107, 111, 1.000)",
        accentSoft: "rgba(13, 107, 111, 0.140)",
        selectionBg: "rgba(13, 107, 111, 0.300)", selectionText: "rgba(31, 29, 26, 1.000)",
        baseSizePx: 14
    )

    /// Semantic `.body` point size (Dynamic Type on iOS) the reader body text
    /// derives from — so Dynamic Type is folded into the base before the #3681
    /// user scale multiplies it.
    @MainActor
    static func readerBaseSize() -> Int {
        #if canImport(AppKit)
        return Int(NSFont.preferredFont(forTextStyle: .body).pointSize.rounded())
        #elseif canImport(UIKit)
        return Int(UIFont.preferredFont(forTextStyle: .body).pointSize.rounded())
        #else
        return 14
        #endif
    }

    /// Resolve the semantic palette for the current appearance, per platform.
    @MainActor
    private static func resolveReaderTheme() -> ReaderTheme {
        #if canImport(AppKit)
        var theme: ReaderTheme?
        NSApp.effectiveAppearance.performAsCurrentDrawingAppearance {
            theme = ReaderTheme(
                background: cssColor(.textBackgroundColor),
                panel: cssColor(.controlBackgroundColor),
                text: cssColor(.textColor),
                muted: cssColor(.secondaryLabelColor),
                line: cssColor(.separatorColor),
                accent: cssColor(.controlAccentColor),
                accentSoft: cssColor(.controlAccentColor.withAlphaComponent(0.14)),
                // Bridge the macOS system selection color so ::selection matches
                // the user's accent / appearance, not the browser default (#1481).
                selectionBg: cssColor(.selectedTextBackgroundColor),
                selectionText: cssColor(.selectedTextColor),
                baseSizePx: readerBaseSize()
            )
        }
        return theme ?? fallbackReaderTheme
        #elseif canImport(UIKit)
        // iOS has no `selectedTextBackgroundColor`; approximate with the app tint.
        let accent = UIColor.tintColor
        return ReaderTheme(
            background: cssColor(.systemBackground),
            panel: cssColor(.secondarySystemBackground),
            text: cssColor(.label),
            muted: cssColor(.secondaryLabel),
            line: cssColor(.separator),
            accent: cssColor(accent),
            accentSoft: cssColor(accent.withAlphaComponent(0.14)),
            selectionBg: cssColor(accent.withAlphaComponent(0.30)),
            selectionText: cssColor(.label),
            baseSizePx: readerBaseSize()
        )
        #else
        return fallbackReaderTheme
        #endif
    }

    /// CSS that overrides the template's `:root` palette + typography with the
    /// live SEMANTIC system colors/fonts for the current appearance, so the
    /// WebKit reader matches the native app exactly — colors, accent, dark mode,
    /// font stack, and base text size. Theming lives here (Swift) by design: the
    /// backend never sniffs the OS. Cross-platform (macOS + iOS) — #3683.
    @MainActor
    static func systemThemeCSS() -> String {
        let theme = resolveReaderTheme()
        // The reader body size = semantic base × the user's Reader font scale
        // (#3681). Dynamic Type is already in `baseSizePx`; the scale composes.
        let scaledSize = Int((Double(theme.baseSizePx) * ViewSettings.FontScale.readerScale()).rounded())
        return """
        :root{\
        --bg: \(theme.background);--panel: \(theme.panel);--text: \(theme.text);\
        --muted: \(theme.muted);--line: \(theme.line);--accent: \(theme.accent);\
        --accent-soft: \(theme.accentSoft);\
        --font-system: \(readerFontSystem);--font-mono: \(readerFontMono);\
        --reader-base-size: \(scaledSize)px;--reader-text-wrap: \(ReaderTextWrap.currentCSS());\
        }html,body{background:transparent!important;}
        ::selection{background-color:\(theme.selectionBg);color:\(theme.selectionText);}
        """
    }
}
