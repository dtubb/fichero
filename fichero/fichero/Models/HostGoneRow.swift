import Foundation

/// A shared project whose host turned Sharing off (`sharing.sidebar.off-greys-row`, #5739): the guest's
/// sidebar keeps the row, greyed, with one sentence, until the person chooses Forget.
struct HostGoneRow: Identifiable, Equatable, Codable {
    let id: UUID
    let name: String
    let host: String

    var sentence: String {
        host.isEmpty ? "Not available: sharing is off on the host" : "Not available: sharing is off on \(host)"
    }
}

/// The greyed rows, kept on this Mac so they are still there after the app relaunches (#5739, owner ruling
/// 2026-11-05). Local only: a row is this Mac's own record that a host went away. A record that cannot be read is no
/// rows, never a crash.
enum HostGoneRowStore {
    static let key = "fichero.hostGoneRows"

    static func load(from defaults: UserDefaults = .standard) -> [HostGoneRow] {
        guard let data = defaults.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([HostGoneRow].self, from: data)) ?? []
    }

    static func save(_ rows: [HostGoneRow], to defaults: UserDefaults = .standard) {
        if rows.isEmpty {
            defaults.removeObject(forKey: key)
        } else if let data = try? JSONEncoder().encode(rows) {
            defaults.set(data, forKey: key)
        }
    }
}
