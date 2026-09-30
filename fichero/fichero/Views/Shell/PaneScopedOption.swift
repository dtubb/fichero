import SwiftUI

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

/// `@AppStorage`, kept per pane (#5280): a drop-in for a pane view's option. The shared value
/// stays at the option's existing key (so nobody's current setting is lost); the per-pane map sits
/// at `<key>.byPane`. See `PaneScopedOption` for the read and write rules.
@propertyWrapper
struct PaneStorage<Value: Codable>: DynamicProperty {
    @Environment(\.paneLeafId) private var pane
    private let shared: AppStorage<Value>
    private let map: AppStorage<String>

    var wrappedValue: Value {
        get { PaneScopedOption.value(map.wrappedValue, pane: pane, shared: shared.wrappedValue) }
        nonmutating set {
            map.wrappedValue = PaneScopedOption.setting(newValue, in: map.wrappedValue, pane: pane)
            shared.wrappedValue = newValue
        }
    }

    var projectedValue: Binding<Value> {
        Binding(get: { wrappedValue }, set: { wrappedValue = $0 })
    }

    private init(shared: AppStorage<Value>, key: String) {
        self.shared = shared
        self.map = AppStorage(wrappedValue: "{}", key + ".byPane")
    }
}

extension PaneStorage where Value == Bool {
    init(wrappedValue: Bool, _ key: String) { self.init(shared: AppStorage(wrappedValue: wrappedValue, key), key: key) }
}

extension PaneStorage where Value == Int {
    init(wrappedValue: Int, _ key: String) { self.init(shared: AppStorage(wrappedValue: wrappedValue, key), key: key) }
}

extension PaneStorage where Value == Double {
    init(wrappedValue: Double, _ key: String) { self.init(shared: AppStorage(wrappedValue: wrappedValue, key), key: key) }
}

extension PaneStorage where Value == String {
    init(wrappedValue: String, _ key: String) { self.init(shared: AppStorage(wrappedValue: wrappedValue, key), key: key) }
}
