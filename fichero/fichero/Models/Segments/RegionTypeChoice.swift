import Foundation

/// A type a region can be set to (`source.editor.region-type-is-seen-and-set`): the engine's label with its SegmOnto
/// zone, and whether the page already carries it. The engine owns the list; the app only draws it.
struct RegionTypeChoice: Equatable, Identifiable {
    let label: String
    let zone: String?
    let subtype: String?
    let onPage: Bool
    var id: String { label }

    /// "MainZone · head": the zone a label means, for a menu's help text; nil for a label the page brought.
    var zoneName: String? {
        guard let zone else { return nil }
        return subtype.map { "\(zone) · \($0)" } ?? zone
    }
}
