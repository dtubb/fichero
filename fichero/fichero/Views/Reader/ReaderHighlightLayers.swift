import Foundation

/// The reader's highlight LAYERS and their precedence (#4355).
///
/// The reader grew several kinds of highlight — find-in-page matches (#4338),
/// recognized-text geometry boxes (#4309), knowledge (entity/claim) highlights,
/// the current page (#4356), and the user's selection. Drawn all at once they
/// turn the page into noise, and one visual language meaning three things is
/// worse than no highlight at all.
///
/// Which layer LEADS is a function of what the user is looking at: with the page
/// image and transcript side by side, find matches lead in the transcript and
/// their boxes light up on the image; with only the image visible, the
/// geometry-anchored highlights carry the meaning; in the knowledge pane,
/// entity/claim highlights lead.
///
/// Pure model + precedence so the rule is one testable place rather than each
/// feature drawing independently.
enum ReaderHighlightLayer: String, CaseIterable, Sendable {
    /// The page the preview pane is showing (#4356).
    case currentPage
    /// Recognized-text bounding boxes on the page image (#4309).
    case geometryBox
    /// Entities and claims tied to the text.
    case entityClaim
    /// In-reader find matches (#4338).
    case findMatch
    /// The user's live text selection / annotation target.
    case selection

    /// The distinct visual treatment for this layer. Two visible layers must
    /// stay distinguishable, so no two layers share a treatment.
    var treatment: Treatment {
        switch self {
        case .currentPage: return .accentEdge
        case .geometryBox: return .thinOutline
        case .entityClaim: return .tint
        case .findMatch: return .findYellow
        case .selection: return .systemSelection
        }
    }

    enum Treatment: String, Sendable {
        /// Accent edge around the page card — a page marker, not a text mark.
        case accentEdge
        /// Thin outline around a recognized-text box on the image.
        case thinOutline
        /// Soft tint behind knowledge-anchored text.
        case tint
        /// System find yellow, reserved for find matches only.
        case findYellow
        /// The platform's own selection appearance.
        case systemSelection
    }
}

/// What the reader currently shows — the input to the precedence rule.
struct ReaderVisibleSplit: Equatable, Sendable {
    /// The page image / PDF is on screen (the Preview pane).
    var showsPageImage: Bool = false
    /// The transcript is on screen (the Reader's Page tab).
    var showsTranscript: Bool = false
    /// A knowledge pane (entities / claims) is on screen.
    var showsKnowledge: Bool = false
    /// Find is active with a live query.
    var isFinding: Bool = false
    /// The user has a live text selection.
    var hasSelection: Bool = false
}

enum ReaderHighlightPrecedence {
    /// The layers to draw for this split, in back-to-front order: the LAST
    /// element is the leading layer, the one whose treatment wins a conflict.
    ///
    /// Rules:
    /// - the current page is always drawn where a transcript is visible — it is a
    ///   page marker, not a text mark, so it never competes for the text;
    /// - find, when active, leads wherever text is visible, pulls the geometry
    ///   layer in so its matches mirror onto the image, and SUPPRESSES the
    ///   knowledge tint — one surface must not carry two meanings at once;
    /// - with only the image visible, geometry carries the meaning;
    /// - knowledge highlights draw wherever text is visible and lead in the
    ///   knowledge pane, while find is inactive;
    /// - a live selection always leads: it is the user's own act.
    static func layers(for split: ReaderVisibleSplit) -> [ReaderHighlightLayer] {
        var layers: [ReaderHighlightLayer] = []

        if split.showsTranscript {
            layers.append(.currentPage)
        }
        if split.showsPageImage {
            layers.append(.geometryBox)
        }

        if split.isFinding, split.showsTranscript || split.showsPageImage {
            layers.append(.findMatch)
        } else if split.showsTranscript || split.showsKnowledge {
            layers.append(.entityClaim)
        }

        if split.hasSelection, split.showsTranscript || split.showsKnowledge {
            layers.append(.selection)
        }
        return layers
    }

    /// The layer whose visual language wins — nil when nothing is highlighted.
    static func leadingLayer(for split: ReaderVisibleSplit) -> ReaderHighlightLayer? {
        layers(for: split).last
    }

    /// Whether a highlight in one pane mirrors into the other: only when BOTH
    /// the transcript and the page image are visible, which is exactly what
    /// #4309's geometry buys (a transcript match lighting its box on the image).
    static func mirrorsAcrossPanes(_ split: ReaderVisibleSplit) -> Bool {
        split.showsTranscript && split.showsPageImage
    }

    /// Whether a given layer draws at all in this split.
    static func isVisible(_ layer: ReaderHighlightLayer, in split: ReaderVisibleSplit) -> Bool {
        layers(for: split).contains(layer)
    }
}
