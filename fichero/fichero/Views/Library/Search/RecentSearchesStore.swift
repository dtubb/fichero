import Foundation

/// Pure-data store for the recent-search history.
///
/// The state lives in `@SceneStorage` on `SearchView` (so per-window
/// persistence survives launches), but the *logic* of dedupe + cap-at-N
/// is extracted here so it can be unit-tested without spinning up a
/// SwiftUI view hierarchy. `SearchView.recordRecentSearch` delegates to
/// `RecentSearchesStore.recording(_:into:cap:)`.
enum RecentSearchesStore {
    /// Max number of recent queries we remember per window. Older
    /// entries fall off the tail when a new entry is recorded.
    static let defaultCap: Int = 10

    /// Decode a JSON-encoded `[String]` (the @SceneStorage shape) into
    /// a Swift array. Returns empty on any parse error so callers don't
    /// have to defend against corrupt SceneStorage state.
    static func decode(_ json: String) -> [String] {
        guard let data = json.data(using: .utf8),
              let list = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }
        return list
    }

    /// Encode an array back to JSON for @SceneStorage. Returns "[]" on
    /// failure so a corrupt write never blows away the slot.
    static func encode(_ list: [String]) -> String {
        guard let data = try? JSONEncoder().encode(list),
              let json = String(data: data, encoding: .utf8)
        else { return "[]" }
        return json
    }

    /// Insert `query` at the head, removing any case-insensitively-equal
    /// existing entry, and cap the result at `cap` entries. Whitespace-
    /// only queries are ignored (returns input untouched). The inserted
    /// entry preserves the original casing of `query` after trimming.
    static func recording(
        _ query: String,
        into prior: [String],
        cap: Int = defaultCap
    ) -> [String] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return prior }
        let foldedNew = trimmed.lowercased()
        var list = prior.filter { $0.lowercased() != foldedNew }
        list.insert(trimmed, at: 0)
        if list.count > cap {
            list = Array(list.prefix(cap))
        }
        return list
    }
}
