import Foundation

/// A view option kept per pane (#5280). Two panes of one kind used to share a single
/// `@AppStorage` key, so changing one pane's option changed the other's.
///
/// Each option keeps a JSON map `pane leaf id → value` beside its shared value. A pane reads its
/// own entry, else the shared value; a change writes both, so a new pane starts from the last
/// choice made anywhere (as a new Finder window does). Leaf ids are saved with the window's pane
/// list, so the entries survive relaunch. With no pane (nil id) the shared value is all there is.
///
/// ponytail: entries for closed panes are never pruned; prune from the pane list if the map grows.
enum PaneScopedOption {
    static func value<V: Codable>(_ mapJSON: String, pane: UUID?, shared: V) -> V {
        guard let pane, let entry = decode(mapJSON, as: V.self)?[pane.uuidString] else { return shared }
        return entry
    }

    static func setting<V: Codable>(_ value: V, in mapJSON: String, pane: UUID?) -> String {
        guard let pane else { return mapJSON }
        var map = decode(mapJSON, as: V.self) ?? [:]
        map[pane.uuidString] = value
        guard let data = try? JSONEncoder().encode(map) else { return mapJSON }
        return String(decoding: data, as: UTF8.self)
    }

    private static func decode<V: Codable>(_ json: String, as _: V.Type) -> [String: V]? {
        try? JSONDecoder().decode([String: V].self, from: Data(json.utf8))
    }
}
