import Foundation

/// The folder a project's originals were last relinked to, kept as a security-scoped bookmark for THAT project
/// (#5535, `transfer.machine.originals-relinked-from-one-grant`): written after a relink, read at the next open so the
/// project relinks from it with no panel. Keyed by the project's path; one folder per project.
enum RememberedOriginalsRoot {
    private static let key = "originals.rememberedRoots"

    /// Read-write scope, the same the folder grant mints with: a folder recalled with a read-only scope cannot
    /// have a read-write scoped bookmark minted from it, and Locate Originals' grant on it was refused (#7076).
    static var creationOptions: URL.BookmarkCreationOptions {
        #if os(macOS)
        [.withSecurityScope]
        #else
        []
        #endif
    }

    static func remember(_ folder: URL, project: String?, defaults: UserDefaults = .standard) {
        guard let project else { return }
        let accessing = folder.startAccessingSecurityScopedResource()
        defer { if accessing { folder.stopAccessingSecurityScopedResource() } }
        guard let bookmark = try? folder.bookmarkData(options: creationOptions) else { return }
        var roots = defaults.dictionary(forKey: key) as? [String: Data] ?? [:]
        roots[project] = bookmark
        defaults.set(roots, forKey: key)
    }

    /// The remembered folder, its security scope entered for the rest of the run (the engine is granted it again);
    /// nil when none is kept or it no longer resolves.
    static func recall(project: String?, defaults: UserDefaults = .standard) -> URL? {
        guard let project, let bookmark = (defaults.dictionary(forKey: key) as? [String: Data])?[project] else {
            return nil
        }
        #if os(macOS)
        let options: URL.BookmarkResolutionOptions = [.withSecurityScope]
        #else
        let options: URL.BookmarkResolutionOptions = []
        #endif
        var stale = false
        guard let folder = try? URL(
            resolvingBookmarkData: bookmark, options: options, bookmarkDataIsStale: &stale
        ) else { return nil }
        _ = folder.startAccessingSecurityScopedResource()
        if stale { remember(folder, project: project, defaults: defaults) }
        return folder
    }
}
