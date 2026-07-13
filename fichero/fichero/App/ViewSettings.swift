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
    /// Reader and Editor are independent (Daniel): separate keys, separate
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

// MARK: - View Mode Enums

/// Sidebar mode selection - Xcode-style mode switching
/// Order: Content (1-4), Research (5), Automation (6), Monitoring (7), KG (9)
enum SidebarMode: String, CaseIterable {
    case library      // 1: Documents, folders
    case search       // 2: Saved searches + search bar
    case chat         // 3: Conversations
    case workflows    // 4: Workflow definitions
    case automation   // 5: Schedules + triggers
    case activity       // 6: All workflow runs (running + completed + failed) with logs/errors
    case research       // 8: Research projects + workspace
    case knowledgeGraph // 9: Entity / ontology browser (#498)

    /// SF Symbol icon name for this mode
    var icon: String {
        switch self {
        case .library: "folder"
        case .search: "magnifyingglass"
        case .chat: "bubble.left.and.bubble.right"
        case .workflows: "bolt"
        case .research: "flask"
        case .automation: "gearshape.2"
        case .activity: "clock"
        case .knowledgeGraph: "point.3.connected.trianglepath.dotted"
        }
    }

    /// Display label for menus
    var label: String {
        switch self {
        case .library: "Library"
        case .search: "Search"
        case .chat: "Chat"
        case .workflows: "Workflows"
        case .research: "Research"
        case .automation: "Automation"
        case .activity: "Activity"
        case .knowledgeGraph: "Knowledge Graph"
        }
    }

    /// Keyboard shortcut number (1-9)
    var shortcutNumber: String {
        switch self {
        case .library: "1"
        case .search: "2"
        case .chat: "3"
        case .workflows: "4"
        case .automation: "5"
        case .activity: "6"
        case .research: "8"
        case .knowledgeGraph: "9"
        }
    }

    /// Tooltip copy: what the mode shows and how to reach it. (#1371)
    var helpText: String {
        let body: String
        switch self {
        case .library:
            body = "Library — browse your documents and folders"
        case .search:
            body = "Search — saved searches and full-text search across the library"
        case .chat:
            body = "Chat — ask questions about your documents in a conversation"
        case .workflows:
            body = "Workflows — build and run AI processing pipelines"
        case .research:
            body = "Research — research projects and their workspace"
        case .automation:
            body = "Automation — schedules and triggers that run workflows automatically"
        case .activity:
            body = "Activity — monitor running and recent background jobs"
        case .knowledgeGraph:
            body = "Knowledge Graph — explore entities and how they connect"
        }
        return "\(body) (⌘\(shortcutNumber))"
    }
}

/// Library layout modes
enum LibraryLayout: String, CaseIterable, Codable {
    case icons = "Icons"
    case list = "List"
    case table = "Table"
    case canvas = "Canvas"
    /// The RealityKit 3D "Space" view (#3088). Mirrors `ViewDisplayMode.space`
    /// so the View-menu ⌘5 ↔ toolbar picker bridge stays bijective — without
    /// this case Space would collapse onto `.canvas` and revert on select.
    case space = "Space"

    var icon: String {
        switch self {
        case .icons: "square.grid.2x2"
        case .list: "list.bullet"
        case .table: "tablecells"
        case .canvas: "rectangle.3.group"
        case .space: "cube.transparent"
        }
    }

    /// The `ViewDisplayMode` this menu layout maps to — the inverse of
    /// `ViewDisplayMode.libraryLayout`, the single source of truth for the
    /// LibraryLayout → ViewDisplayMode bridge (#3088).
    var displayMode: ViewDisplayMode {
        switch self {
        case .icons: .icon
        case .list: .list
        case .table: .table
        case .canvas: .canvas
        case .space: .space
        }
    }
}

/// Preview panel mode (matches LayoutMode)
enum PreviewMode: String, CaseIterable {
    case none
    case standard   // Content and preview stacked vertically
    case widescreen // Content and preview side-by-side
}

/// Mail-modeled vocabulary for WHERE the document preview sits relative to the
/// library list (#2032/§6d). This is a thin facade over the canonical
/// `PreviewMode` — it does NOT introduce a parallel stored value. The single
/// source of truth remains `ViewSettings.previewMode` (and its per-window
/// `@SceneStorage("currentLayoutMode")` mirror); `PreviewLayout` just renames
/// the three existing cases into Apple-Mail terms:
///
///   .side   ⇆ .widescreen  — list and preview side-by-side (HStack)
///   .bottom ⇆ .standard    — list above, preview below (VSplitView)
///   .hidden ⇆ .none        — list only, no preview
///
/// Default `.side` preserves current behavior (`previewMode` defaults to
/// `.widescreen`). Use `PreviewMode.layout` / `PreviewLayout.previewMode` to
/// bridge; never store a `PreviewLayout` separately.
enum PreviewLayout: String, CaseIterable {
    case side    // = .widescreen
    case bottom  // = .standard
    case hidden  // = .none

    /// The canonical preview mode this layout maps to.
    var previewMode: PreviewMode {
        switch self {
        case .side: .widescreen
        case .bottom: .standard
        case .hidden: .none
        }
    }
}

extension PreviewMode {
    /// The Mail-vocabulary layout this preview mode corresponds to.
    var layout: PreviewLayout {
        switch self {
        case .widescreen: .side
        case .standard: .bottom
        case .none: .hidden
        }
    }
}

// MARK: - Focused Values

/// Focused value for sidebar mode - allows menu commands to change per-window sidebar mode
extension FocusedValues {
    @Entry var sidebarMode: Binding<SidebarMode>?

    /// Per-window inspector visibility, published by the focused ContentView so
    /// the View-menu "Show/Hide Inspector" command toggles only the focused
    /// window — not every open window (#1451).
    @Entry var showInspector: Binding<Bool>?

    /// Per-window visibility of the major reading-surface panes, published by
    /// the focused ContentView so the View menu mirrors the toolbar toggles
    /// for each pane (#1215). Same per-window rationale as `showInspector`:
    /// each binds the focused window's @SceneStorage flag.
    @Entry var showDocumentGrid: Binding<Bool>?
    @Entry var showDocumentCanvas: Binding<Bool>?
    /// The WebKit/reading content pane (transcript surface).
    @Entry var showReadingPane: Binding<Bool>?

    /// The active representation shown in the document content/WebKit surface
    /// (Transcript/Digest/Graph/Claims/Timeline/Map), published by the focused
    /// `DocumentKGSurface`. Drives the View-menu "Add View" items so the
    /// representation switcher lives in the menu instead of a floating icon bar
    /// over the content (#2032 / reform §G). Nil when no document surface is
    /// focused, so the menu items disable.
    ///
    /// Uses the Equatable `DocumentRepresentationFocus` wrapper (not a raw
    /// `Binding`, which is non-Equatable) so SwiftUI can dedupe it: a `body`
    /// pass with the same active tab does NOT republish, avoiding per-frame
    /// focused-value churn (#2032).
    @Entry var documentRepresentation: DocumentRepresentationFocus?

    /// The active view mode of the global Knowledge Graph browser
    /// (List/Graph/Chart/Timeline/Map), published by the focused
    /// `OntologyBrowser`. Drives the View-menu "Knowledge Graph View" items and
    /// the iOS toolbar View menu so the KG mode switcher lives in the menu /
    /// main toolbar instead of a segmented icon row inside the KG pane toolbar
    /// (#2436, same principle as `documentRepresentation`). Nil when the KG
    /// browser is not focused, so the menu items disable.
    ///
    /// Uses the Equatable `KnowledgeGraphViewModeFocus` wrapper (not a raw
    /// `Binding`) so SwiftUI dedupes it and the switcher does not republish a
    /// "new" focused value every `body` pass.
    @Entry var knowledgeGraphViewMode: KnowledgeGraphViewModeFocus?
}
