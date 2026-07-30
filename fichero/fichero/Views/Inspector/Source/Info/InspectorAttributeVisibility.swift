import Foundation

/// An attribute the inspector can show ABOUT A DOCUMENT (#4422).
///
/// Two things are deliberately absent, and their absence is the point:
/// **ingest mode** and **storage path**. Those are facts about how the app
/// filed the bytes, not about the document — `files/fi/ca408d0…oad_c84fgjke.pdf`
/// is a generated location containing a generated filename, the same one shown
/// wrongly in the island (#4416) and the same class as a raw `doc:6679…`
/// leaking into a list row (#4398). They are not merely hidden by default; they
/// are not offerable, because there is no configuration in which showing a user
/// their internal storage path is the right answer.
enum InspectorAttribute: String, CaseIterable, Hashable {
    case state
    case documentClass
    case kind
    case fileType
    case format
    case fileSize
    case created
    case modified
    case pageCount
    case dimensions

    /// The label the strip shows.
    var title: String {
        switch self {
        case .state: return "State"
        case .documentClass: return "Class"
        case .kind: return "Kind"
        case .fileType: return "Type"
        case .format: return "Format"
        case .fileSize: return "Size"
        case .created: return "Created"
        case .modified: return "Modified"
        case .pageCount: return "Pages"
        case .dimensions: return "Dimensions"
        }
    }
}

/// Which attributes are visible, as DATA rather than as a hardcoded strip
/// (#4422).
///
/// The default is **nothing**. Filling the inspector with metadata nobody asked
/// for is worse than showing nothing: of the seven rows that used to appear by
/// default, one (`Entities`) was useful and six described the app's own
/// bookkeeping. `Kind` duplicates the icon, `Status` duplicates a badge that
/// #4398 argues should be silent in the ordinary case — and on a folder it
/// disagreed with the list row — and `Created`/`Modified` are filesystem dates,
/// which for historical material are not the date that matters.
///
/// This exists as a resolver, not a constant, because Daniel wants
/// Tinderbox-style visibility later: defined per attribute, per item or per
/// PROTOTYPE, so a diary page and a legal record can show different sets and
/// each kind is configured once rather than per item. Making the visible set
/// data now means that arrives as a change to `visibleAttributes(for:chosen:)`
/// rather than a rewrite of the strip. No prototypes are built here — the point
/// is only not to foreclose them.
enum InspectorAttributeVisibility {
    /// Shown when nobody has chosen otherwise: nothing at all.
    static let defaultVisible: [InspectorAttribute] = []

    /// Everything a user may choose to show. Storage internals are not in this
    /// list because they are not cases of `InspectorAttribute` at all.
    static var selectable: [InspectorAttribute] { InspectorAttribute.allCases }

    /// The attributes to render for `document`.
    ///
    /// - Parameter chosen: an explicit set, once there is a UI to choose one or
    ///   a prototype to inherit from. `nil` means "nobody has chosen", which is
    ///   the state every document is in today.
    ///
    /// The document is taken as a parameter it does not yet read: that is the
    /// seam a per-item or per-prototype resolver needs, and adding it now costs
    /// one unused argument instead of a later signature change at every call
    /// site.
    static func visibleAttributes(
        for document: Document,
        chosen: [InspectorAttribute]? = nil
    ) -> [InspectorAttribute] {
        guard let chosen else { return defaultVisible }
        // Order follows the declaration, not the caller, so the strip reads the
        // same however the choice was assembled.
        return InspectorAttribute.allCases.filter(chosen.contains)
    }

    /// Whether the strip should render at all.
    static func showsAnyAttributes(
        for document: Document,
        chosen: [InspectorAttribute]? = nil
    ) -> Bool {
        !visibleAttributes(for: document, chosen: chosen).isEmpty
    }
}
