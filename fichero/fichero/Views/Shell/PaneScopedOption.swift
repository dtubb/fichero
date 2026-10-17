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

    /// A pane-only option (#5504) passes its declared default as `paneOnly`: a pane with no entry
    /// starts from that, never from the shared key (which an old app-wide toggle may have left off).
    static func value<V: Codable>(_ mapJSON: String, pane: UUID?, shared: V, paneOnly: V?) -> V {
        value(mapJSON, pane: pane, shared: paneOnly ?? shared)
    }

    static func hasEntry(_ mapJSON: String, pane: UUID) -> Bool {
        decode(mapJSON, as: Bool.self)?[pane.uuidString] != nil
    }

    static func setting<V: Codable>(_ value: V, in mapJSON: String, pane: UUID?) -> String {
        guard let pane else { return mapJSON }
        var map = decode(mapJSON, as: V.self) ?? [:]
        map[pane.uuidString] = value
        guard let data = try? JSONEncoder().encode(map) else { return mapJSON }
        return String(bytes: data, encoding: .utf8) ?? mapJSON
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
            if pane != nil {
                map.wrappedValue = PaneScopedOption.setting(newValue, in: map.wrappedValue, pane: pane)
            }
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

/// A switch kept per pane ONLY (#5504): a pane reads its own entry in `<key>.byPane`, else the declared default,
/// and never reads or writes the shared key (an old toggle left `imagePreview.ocrBoxesEnabled` false app-wide, so
/// every new Preview drew no boxes). A view with no pane keeps its choice for its lifetime. Its own type, not a mode
/// of `PaneStorage`: the extra fields would grow every pane option's value (`ViewValueSizeTests`).
@propertyWrapper
struct PaneOnlyStorage: DynamicProperty {
    @Environment(\.paneLeafId) private var pane
    private let map: AppStorage<String>
    /// The last choice made in any pane (#5015, review 52): the START value of a pane with no entry of its own,
    /// when `remembers`. A pane copies it into its own entry on first appearance (`adoptSeed`), so after that the
    /// panes are independent again and only a NEW pane starts from it. Unused when not `remembers`.
    private let last: AppStorage<Bool>
    private let remembers: Bool
    private let initial: Bool
    @State private var unpaned: Bool?

    var wrappedValue: Bool {
        get {
            if pane == nil, let unpaned { return unpaned }
            return PaneScopedOption.value(map.wrappedValue, pane: pane, shared: last.wrappedValue, paneOnly: remembers ? nil : initial)
        }
        nonmutating set {
            if pane != nil {
                map.wrappedValue = PaneScopedOption.setting(newValue, in: map.wrappedValue, pane: pane)
            } else {
                unpaned = newValue
            }
            if remembers { last.wrappedValue = newValue }
        }
    }

    var projectedValue: Binding<Bool> {
        Binding(get: { wrappedValue }, set: { wrappedValue = $0 })
    }

    /// Give this pane its own entry holding what it shows now (the seed, for a pane that never chose), so a later
    /// change in another pane no longer reaches it. A pane with an entry is left alone.
    func adoptSeed() {
        guard remembers, let pane, !PaneScopedOption.hasEntry(map.wrappedValue, pane: pane) else { return }
        map.wrappedValue = PaneScopedOption.setting(wrappedValue, in: map.wrappedValue, pane: pane)
    }

    init(wrappedValue: Bool, _ key: String, remembers: Bool = false) {
        map = AppStorage(wrappedValue: "{}", key + ".byPane")
        last = AppStorage(wrappedValue: wrappedValue, key + ".last")
        self.remembers = remembers
        initial = wrappedValue
    }
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
