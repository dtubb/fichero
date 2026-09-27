import Observation
import SwiftUI
#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif

/// Observable settings for view configuration (app-wide preferences)
/// Note: sidebarMode is NOT here - it's per-window state stored in @SceneStorage
@MainActor
@Observable
class ViewSettings {
    var libraryLayout: LibraryLayout = .icons
    var previewMode: PreviewMode = .widescreen
    // NOTE: inspector visibility is intentionally NOT here. It is per-window
    // state (`ContentView.showInspectorSidebar`, @SceneStorage) exposed to the
    // View menu via `FocusedValues.showInspector` below, so toggling the
    // inspector in one window no longer flips it in every other window (#1451).
}

// MARK: - Typography (Reader / Editor font scale, #3681 / #3682)

extension ViewSettings {
    /// Reader- and Editor-text font-size overrides — a *scale* over the semantic
    /// base size (`preferredFont(forTextStyle:)`), never an absolute size, so the
    /// override composes with Dynamic Type and honors the semantic-fonts rule.
    ///
    /// Stored as `@AppStorage`-keyed UserDefaults doubles (not instance
    /// properties) so both the Settings scene — a SEPARATE scene — and the
    /// Reader/Editor consumers share one source without env-injection coupling.
    /// Reader and Editor are independent (the maintainer): separate keys, separate
    /// steppers, both clamped `0.8…2.0`.
    enum FontScale {
        static let readerKey = "fichero.reader.fontScale"
        static let editorKey = "fichero.editor.fontScale"
        static let defaultValue = 1.0
        static let range: ClosedRange<Double> = 0.8...2.0
        static let step = 0.1

        /// Clamp any stored/edited value into range — defends consumers against a
        /// corrupted default; the Settings stepper also enforces `range` on input.
        static func clamped(_ value: Double) -> Double {
            min(max(value, range.lowerBound), range.upperBound)
        }

        /// A "%" readout of a scale for the stepper label (e.g. `1.2 → "120%"`).
        static func percentLabel(_ value: Double) -> String {
            "\(Int((value * 100).rounded()))%"
        }

        /// The current, clamped Reader / Editor scale from UserDefaults. Consumers
        /// (the WebKit injection, AnnotatableTextView, the editor surfaces) read
        /// these so the stored key is the single source. Defaults to `1.0` when
        /// unset — NOT `UserDefaults.double`'s `0`, which would clamp to 0.8.
        static func readerScale() -> Double { storedScale(forKey: readerKey) }
        static func editorScale() -> Double { storedScale(forKey: editorKey) }

        private static func storedScale(forKey key: String) -> Double {
            clamped((UserDefaults.standard.object(forKey: key) as? Double) ?? defaultValue)
        }

        /// The semantic point size of a text style on this platform — Dynamic Type
        /// on iOS, the system size on macOS. The user scale multiplies this, so an
        /// editor keeps the *semantic* base it was designed with (a `.caption`
        /// editor stays smaller than a `.body` one at every scale).
        @MainActor
        static func semanticSize(_ style: Font.TextStyle) -> Double {
            #if canImport(AppKit)
            return Double(NSFont.preferredFont(forTextStyle: platformTextStyle(style)).pointSize)
            #elseif canImport(UIKit)
            return Double(UIFont.preferredFont(forTextStyle: platformTextStyle(style)).pointSize)
            #else
            return 13
            #endif
        }

        /// The semantic `.body` point size for the current platform.
        @MainActor
        static func semanticBodySize() -> Double { semanticSize(.body) }

        /// Editor point size = the style's semantic base × the clamped Editor scale (#3682).
        @MainActor
        static func editorSize(_ style: Font.TextStyle, scale: Double) -> Double {
            semanticSize(style) * clamped(scale)
        }

        /// Editor body point size = semantic base × the clamped Editor scale (#3682).
        @MainActor
        static func editorBodySize(scale: Double) -> Double { editorSize(.body, scale: scale) }
    }
}

#if canImport(AppKit)
private typealias PlatformTextStyle = NSFont.TextStyle
#elseif canImport(UIKit)
private typealias PlatformTextStyle = UIFont.TextStyle
#endif

#if canImport(AppKit) || canImport(UIKit)
/// SwiftUI `Font.TextStyle` → the AppKit/UIKit style whose preferred font carries
/// the semantic point size. (The two frameworks share these case names.) Anything
/// unmapped falls back to `.body`.
private func platformTextStyle(_ style: Font.TextStyle) -> PlatformTextStyle {
    let map: [Font.TextStyle: PlatformTextStyle] = [
        .largeTitle: .largeTitle, .title: .title1, .title2: .title2, .title3: .title3,
        .headline: .headline, .subheadline: .subheadline, .body: .body,
        .callout: .callout, .footnote: .footnote, .caption: .caption1, .caption2: .caption2
    ]
    return map[style] ?? .body
}
#endif

// MARK: - Editor font scaling modifier (#3682)

/// Applies the user's Editor font scale to an editable text surface — scales the
/// semantic base of the style the surface was designed with (which tracks Dynamic
/// Type) by the clamped Editor scale, so the override composes with Dynamic Type
/// and never hardcodes a size.
private struct EditorScaledFont: ViewModifier {
    let style: Font.TextStyle
    let design: Font.Design

    @AppStorage(ViewSettings.FontScale.editorKey)
    private var editorScale = ViewSettings.FontScale.defaultValue

    func body(content: Content) -> some View {
        content.font(.system(size: ViewSettings.FontScale.editorSize(style, scale: editorScale),
                             design: design))
    }
}

extension View {
    /// Scale an editable text surface by the user's Editor font size (#3682).
    /// Use on every editable `TextEditor` in place of `.font(<semantic style>)`,
    /// passing the style (and design) that surface would otherwise have used.
    func editorScaledFont(_ style: Font.TextStyle = .body,
                          design: Font.Design = .default) -> some View {
        modifier(EditorScaledFont(style: style, design: design))
    }
}

// MARK: - Reader paragraph wrapping (#3684)

/// How the Reader wraps prose paragraphs, mapped to the CSS `text-wrap` value
/// injected as `--reader-text-wrap`. Default `.tidy` (`pretty`) stops a single
/// word from stranding on the last line; a widont JS pass covers WebKit without
/// `text-wrap: pretty` (older than the Golden Gate target — a no-op there).
enum ReaderTextWrap: String, CaseIterable, Identifiable {
    case system
    case tidy
    case balanced

    var id: String { rawValue }

    /// The CSS `text-wrap` value this mode injects.
    var cssValue: String {
        switch self {
        case .system: "normal"
        case .tidy: "pretty"
        case .balanced: "balance"
        }
    }

    var label: String {
        switch self {
        case .system: "System"
        case .tidy: "Tidy (no orphans)"
        case .balanced: "Balanced"
        }
    }

    static let storageKey = "fichero.reader.textWrap"

    /// The current CSS `text-wrap` value from UserDefaults (default `.tidy`).
    static func currentCSS() -> String {
        (UserDefaults.standard.string(forKey: storageKey)
            .flatMap(ReaderTextWrap.init(rawValue:)) ?? .tidy).cssValue
    }
}
