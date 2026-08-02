import Foundation

// MARK: - Historical document date, as the UI shows it (#3322)

/// What a document's historical date says — the ONE place that decides how a
/// date reads, so no surface invents its own phrasing or format.
///
/// Four states, and keeping them apart is the point. The engine distinguishes
/// them deliberately and it would be easy to render all four as an empty cell,
/// which would kill the distinction at the last inch:
///
/// | state | means | evidentiary value |
/// |---|---|---|
/// | `.dated` | a date was read from the document | the date |
/// | `.undatedInSource` | the manuscript SAYS undated — n.d. / s.f. | **evidence a historian cites** |
/// | `.noDateFound` | extraction ran and found nothing | weak evidence — we looked |
/// | `.notExamined` | extraction never ran | **no evidence at all** |
///
/// "The manuscript is marked n.d." and "we have not looked yet" are different
/// facts about the world. Collapsing them is the absence-as-answer mistake in
/// its most consequential form for this corpus: a scholar citing "undated"
/// needs to know the manuscript said so, not that a pipeline had not run.
enum DocumentDateDisplay: Equatable {
    /// `text` is the ENGINE's rendered string, never one the client built.
    case dated(text: String)
    case undatedInSource
    case noDateFound
    case notExamined

    /// What the row or field shows.
    ///
    /// The dated case returns the backend's `display` verbatim. The client must
    /// never construct a `Date` from a historical date, nor format one itself:
    /// precision lives server-side (`render_display`), which is what keeps a
    /// year-precision date reading "1791" instead of "1 January 1791". A second
    /// formatter here would be a second opinion about what the manuscript says.
    var text: String {
        switch self {
        case .dated(let text): text
        case .undatedInSource: "Undated in source"
        case .noDateFound: "No date found"
        case .notExamined: "Date not examined"
        }
    }

    /// Whether this reads as an actual date, for surfaces that want to style
    /// "we know" differently from "we do not".
    var isKnown: Bool {
        if case .dated = self { return true }
        return false
    }

    /// Longer phrasing for a tooltip or an inspector detail line, where the
    /// distinction has room to be explained rather than implied.
    var explanation: String {
        switch self {
        case .dated: "Date read from the document."
        case .undatedInSource: "The document itself is marked undated (n.d. / s.f. / sine data)."
        case .noDateFound: "Date extraction ran and found no date in this document."
        case .notExamined: "Date extraction has not run on this document yet."
        }
    }
}

extension DocumentDateDisplay {
    /// Resolve from the three columns the engine writes (#3322).
    ///
    /// The state is carried by `date_meta` — its ABSENCE is what "never
    /// extracted" means, so a nil meta is a real answer here and not a missing
    /// value to paper over. That is why this takes the meta as an optional and
    /// treats nil distinctly rather than defaulting it to empty.
    ///
    /// Unknown future statuses fall to `.notExamined` rather than being shown
    /// raw: inventing a label for a status this build does not understand would
    /// put engine vocabulary in front of the user.
    static func resolve(
        dateOriginal: String?,
        dateJdn: Int?,
        dateMeta: [String: Any]?
    ) -> DocumentDateDisplay {
        guard let dateMeta else { return .notExamined }

        switch dateMeta["status"] as? String {
        case "dated":
            // `display` is the engine's rendering. `date_original` is the
            // verbatim manuscript text and is the honest fallback if an older
            // row predates `display` — still never a client-side format.
            let rendered = (dateMeta["display"] as? String)
                ?? dateOriginal
            guard let rendered, !rendered.isEmpty else {
                // Status says dated and nothing readable came with it. That is
                // a contradiction, not a date — do not invent one from the JDN.
                return .noDateFound
            }
            return .dated(text: rendered)

        case "undated_explicit":
            return .undatedInSource

        case "none_found":
            return .noDateFound

        default:
            return .notExamined
        }
    }
}
