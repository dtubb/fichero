import Foundation
import Observation

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

/// Where the chooser's answer lives (#4481).
///
/// #4422 made the visible set data and defaulted it to nothing, which was the
/// right call — but it shipped only that half. `chosen:` had no caller, so the
/// resolver took its `nil` branch for every document forever and all ten
/// attributes rendered for nobody. A configurable system with no configuration
/// is not configurable; it is off. This is the missing caller.
///
/// The choice is keyed by **prototype**, not by document, because that is the
/// Tinderbox model `visibleAttributes(for:chosen:)` was written to accept: a
/// diary page and a legal record show different sets, and each kind is
/// configured ONCE rather than per item. It is deliberately the same seam
/// rather than a second visibility mechanism beside it — two mechanisms for one
/// concept is this project's most common defect.
///
/// A document with no prototype is not a special case with its own rules; it is
/// simply the bucket keyed by `untypedBucket`, configured the same way.
@MainActor
@Observable
final class InspectorAttributeChoiceStore {
    /// The app-wide store the inspector reads. Shared so a choice made in one
    /// window is the same choice in every other — the set belongs to the
    /// prototype, not to a window.
    static let shared = InspectorAttributeChoiceStore()

    static let storageKey = "fichero.inspector.attributeChoices"

    /// The bucket for documents with no prototype assigned.
    static let untypedBucket = "__untyped__"

    private let defaults: UserDefaults

    /// prototype bucket → chosen attribute raw values.
    ///
    /// A bucket that is ABSENT means "nobody has chosen" and resolves to
    /// `defaultVisible`. A bucket present but EMPTY means "chosen: show
    /// nothing". Those are different answers and the store keeps them apart, so
    /// "Use Default" can restore inheritance rather than only clearing rows.
    private var choices: [String: [String]]

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.choices = (defaults.dictionary(forKey: Self.storageKey) ?? [:])
            .compactMapValues { $0 as? [String] }
    }

    static func bucket(for prototypeKey: String?) -> String {
        guard let key = prototypeKey, !key.isEmpty else { return untypedBucket }
        return key
    }

    /// The explicit choice for this prototype, or `nil` when nobody has chosen —
    /// exactly the argument `visibleAttributes(for:chosen:)` expects.
    func chosen(forPrototype prototypeKey: String?) -> [InspectorAttribute]? {
        guard let raw = choices[Self.bucket(for: prototypeKey)] else { return nil }
        // Unknown raw values are dropped rather than crashing: a stored choice
        // outlives the build that wrote it, and a removed case must not brick
        // the chooser for every document of that prototype.
        return raw.compactMap(InspectorAttribute.init(rawValue:))
    }

    /// Whether a row is currently on for this prototype — the chooser's tick.
    func isChosen(_ attribute: InspectorAttribute, forPrototype prototypeKey: String?) -> Bool {
        (chosen(forPrototype: prototypeKey)
            ?? InspectorAttributeVisibility.defaultVisible)
            .contains(attribute)
    }

    /// Whether this prototype has an explicit choice at all (vs. inheriting the
    /// default). Drives whether "Use Default" is worth offering.
    func hasChoice(forPrototype prototypeKey: String?) -> Bool {
        choices[Self.bucket(for: prototypeKey)] != nil
    }

    func setChosen(_ attributes: [InspectorAttribute], forPrototype prototypeKey: String?) {
        // Stored in declaration order so the persisted value reads the same
        // however the user assembled it — the same invariant the resolver
        // enforces on the way out.
        let ordered = InspectorAttribute.allCases.filter(attributes.contains)
        choices[Self.bucket(for: prototypeKey)] = ordered.map(\.rawValue)
        persist()
    }

    func toggle(_ attribute: InspectorAttribute, forPrototype prototypeKey: String?) {
        var current = chosen(forPrototype: prototypeKey)
            ?? InspectorAttributeVisibility.defaultVisible
        if let index = current.firstIndex(of: attribute) {
            current.remove(at: index)
        } else {
            current.append(attribute)
        }
        setChosen(current, forPrototype: prototypeKey)
    }

    /// Forget this prototype's choice so it inherits `defaultVisible` again.
    func clearChoice(forPrototype prototypeKey: String?) {
        choices.removeValue(forKey: Self.bucket(for: prototypeKey))
        persist()
    }

    private func persist() {
        defaults.set(choices, forKey: Self.storageKey)
    }
}
