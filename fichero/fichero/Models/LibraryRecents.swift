import Foundation
import Observation

/// The File ▸ Open Recent list (2026-08-25). Client-side and append-only on
/// open/save — deliberately NOT the engine's known-libraries registry, which
/// the menu used before. The registry is the authoritative OPEN set (the
/// sidebar reconciles against it, and Close Library must unregister to make
/// the engine release its DB handle, #1661/#3939) — so a library vanished
/// from "recent" the moment it was closed, which is precisely when Open
/// Recent is needed. Recents have the opposite lifecycle: they must survive
/// close, and must never contain the TMPDIR staging package the create flow
/// materializes before the save panel.
@MainActor
@Observable
final class LibraryRecents {
    static let shared = LibraryRecents()

    struct Entry: Identifiable, Equatable {
        let path: String
        let displayName: String
        var id: String { path }
    }

    private(set) var entries: [Entry] = []

    private static let storageKey = "fichero.recentLibraries"
    private static let cap = 15

    private init() {
        entries = Self.load()
    }

    /// Record a library open/save. Temp staging packages are refused here —
    /// at the seam — so no caller can leak an `Untitled-<UUID>` ghost into
    /// the menu. De-duplicated by `canonicalLibraryKey` (the one "same
    /// library?" answer, #4517), so `/var` vs `/private/var` spellings of one
    /// package can't stack seven deep the way they did in the registry menu.
    func note(url: URL, displayName: String) {
        let tempPath = FileManager.default.temporaryDirectory.path
        guard !url.path.hasPrefix(tempPath), !url.path.hasPrefix("/private" + tempPath) else {
            return
        }
        // The app-managed Global/Local package is always open — it is not a
        // "recent" anything, and it polluted the registry-backed menu.
        guard url.lastPathComponent.lowercased() != "global.fichero" else { return }
        let key = LibraryManager.canonicalLibraryKey(url)
        var updated = entries.filter {
            LibraryManager.canonicalLibraryKey(URL(fileURLWithPath: $0.path)) != key
        }
        updated.insert(Entry(path: url.path, displayName: displayName), at: 0)
        entries = Array(updated.prefix(Self.cap))
        persist()
    }

    /// Drop one entry — the menu prunes entries whose package is gone.
    func remove(path: String) {
        entries.removeAll { $0.path == path }
        persist()
    }

    func clearAll() {
        entries = []
        persist()
    }

    private func persist() {
        let raw = entries.map { ["path": $0.path, "name": $0.displayName] }
        UserDefaults.standard.set(raw, forKey: Self.storageKey)
    }

    private static func load() -> [Entry] {
        let raw = UserDefaults.standard.array(forKey: storageKey) as? [[String: String]] ?? []
        return raw.compactMap { dict in
            guard let path = dict["path"] else { return nil }
            return Entry(path: path, displayName: dict["name"] ?? URL(fileURLWithPath: path).lastPathComponent)
        }
    }
}
