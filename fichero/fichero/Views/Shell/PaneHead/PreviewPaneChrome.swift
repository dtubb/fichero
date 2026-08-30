import SwiftUI

// MARK: - Preview pane head ↔ canvas chrome seam (Daniel, 2026-08-29)
//
// The Preview restructure moves paging and the renditions switcher out of the
// bottom ReaderToolbar and into the pane HEAD (pages ‹ › left of the
// breadcrumb; renditions as a head menu, the reader's transcript/translation
// grammar). The head lives on ContentView while the state lives deep inside
// ZoomableImagePreview / PDFPageWithToolbar, so the canvas PUBLISHES its
// chrome into this observable and the head renders from it.
//
// One instance per ContentView (per window). With split preview panes both
// sides write here and the last active writer wins — the same
// last-writer-wins the focused-value zoom actions already accept.

/// What the preview head needs to know about the mounted canvas.
@MainActor
@Observable
final class PreviewPaneChrome {
    /// Page/sibling stepping for the head's ‹ › cluster. Supplied by the PDF
    /// page controller or the image viewer's sibling walk; nil hides count.
    var pageNav: ReaderPageNav?

    /// Display names of the shown page's renditions, engine order. Empty (or
    /// a single entry) hides the head's renditions menu — a menu with nothing
    /// to switch to is the menu lying.
    var renditionNames: [String] = []
    var renditionIndex: Int = 0
    /// Flips the canvas to the chosen rendition index.
    var selectRendition: ((Int) -> Void)?

    /// Clears everything a departing canvas published, so a pane that swaps
    /// from image to PDF (or to a non-visual document) doesn't keep serving
    /// the old canvas's controls.
    func reset() {
        pageNav = nil
        renditionNames = []
        renditionIndex = 0
        selectRendition = nil
    }
}

// MARK: - Notification seams

extension Notification.Name {
    /// The head's markup row picked an annotation tool. `object` is a
    /// `PreviewMarkupTool` raw value. The image/PDF canvases observe this the
    /// way they observe `.previewSiblingSwipe`.
    static let previewAnnotateTool = Notification.Name("previewAnnotateTool")

    /// The head's markup row invoked a REGION verb (select / draw-region /
    /// delete / combine). `object` is a `PreviewRegionVerb` raw value.
    /// SEAM for the preview-regions lane: the region hit-testing/move/delete/
    /// combine work observes this; nothing consumes it here by design.
    static let previewRegionVerb = Notification.Name("previewRegionVerb")

    /// The quiet bottom bar's info/metadata button. ContentView observes and
    /// toggles the inspector sidebar for this window.
    static let previewShowInfo = Notification.Name("previewShowInfo")
}

/// The markup tools of the head's slide-out row (Daniel, 2026-08-29:
/// Preview.app's markup bar is the model).
enum PreviewMarkupTool: String, CaseIterable, Identifiable {
    case select
    case drawRegion
    case line
    case highlight
    case note

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .select: "cursorarrow"
        case .drawRegion: "rectangle.dashed"
        case .line: "line.diagonal"
        case .highlight: "highlighter"
        case .note: "note.text"
        }
    }

    var label: String {
        switch self {
        case .select: "Select"
        case .drawRegion: "Draw Region"
        case .line: "Line"
        case .highlight: "Highlight"
        case .note: "Text Note"
        }
    }

    /// Tools the annotation machinery already persists (highlight/note draw a
    /// region and save via AnnotationStore). The rest are the preview-regions
    /// lane's verbs or future drawing kinds.
    var mapsToAnnotationKind: Bool {
        self == .highlight || self == .note
    }
}

/// Region-curation verbs (delete/combine act on the selection the
/// preview-regions lane owns; select/drawRegion arm its interactions).
enum PreviewRegionVerb: String {
    case select
    case draw
    case delete
    case combine
}

// MARK: - Highlight style (split-button state, Daniel 2026-08-29)

/// The highlight split-button's persistent state: one of five colors, or an
/// underline/strikethrough mode — Preview.app's highlight menu. The COLOR
/// persists to the engine on each saved highlight (`addNote(color:)` already
/// carries it); underline/strikethrough have no annotation-kind backing yet,
/// so they persist only as the control's state (see the report note).
enum PreviewHighlightStyle: String, CaseIterable, Identifiable {
    case yellow, green, blue, pink, purple
    case underline, strikethrough

    var id: String { rawValue }

    /// The five color cases, menu order.
    static var colors: [PreviewHighlightStyle] { [.yellow, .green, .blue, .pink, .purple] }

    var isColor: Bool { Self.colors.contains(self) }

    var label: String {
        switch self {
        case .yellow: "Yellow"
        case .green: "Green"
        case .blue: "Blue"
        case .pink: "Pink"
        case .purple: "Purple"
        case .underline: "Underline"
        case .strikethrough: "Strikethrough"
        }
    }

    /// The dot swatch / tint the control renders.
    var tint: Color {
        switch self {
        case .yellow: .yellow
        case .green: .green
        case .blue: .blue
        case .pink: .pink
        case .purple: .purple
        case .underline, .strikethrough: .secondary
        }
    }

    /// The engine-persisted color for a saved highlight — HEX, because the
    /// engine's `validate_annotation_color` accepts only `#RRGGBB[AA]` and
    /// would 422 a name. Apple system palette values. nil for the mode cases
    /// (they save an uncolored highlight until a backing kind exists).
    var persistedColor: String? {
        switch self {
        case .yellow: "#FFD60A"
        case .green: "#30D158"
        case .blue: "#0A84FF"
        case .pink: "#FF375F"
        case .purple: "#BF5AF2"
        case .underline, .strikethrough: nil
        }
    }

    /// The AppStorage key the split button and the canvases share.
    static let storageKey = "preview.highlightStyle"
}
