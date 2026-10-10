import Foundation

/// The always-there project: the engine's global library, on disk `global.fichero` in the app's
/// data folder (`fichero_server.db.paths.GLOBAL_LIBRARY_PACKAGE_NAME`). Everything in the sidebar
/// is a project; this one is always there, cannot be closed or deleted, and is named like any
/// other: it starts as `defaultName` and a person may rename it (ruled 2026-10-10; Zotero's My
/// Library and DEVONthink's Inbox were the models considered). The engine does not name it; the
/// app does, through the same display names every project has
/// (`LibraryManager.libraryDisplayNamesByPathKey`). `library.always-there-project.*` in
/// `docs/contributor_manual/specs/ui/sidebar-crud.md`.
nonisolated enum AlwaysThereProject {
    /// The always-there project's name until a person renames it. Change only this line.
    static let defaultName = "My Project"

    /// Names the app gave it before the ruling. A saved one is not a person's choice, so it reads
    /// as `defaultName`.
    static let retiredNames: Set<String> = ["Local", "Global", "My Library", "Desk", "global"]

    /// The package name on disk. Never changes: naming the project moves no data.
    static let packageName = "global.fichero"

    /// Whether `path` is the always-there project's package. Matched by package NAME, as the
    /// engine's `is_global_library_package` does, because a sandboxed container and an
    /// unsandboxed build put it under different homes.
    static func isPackage(path: String) -> Bool {
        (path as NSString).lastPathComponent == packageName
    }

    /// The name shown for the project at `path`, given the name saved or recorded for it. Any
    /// other project keeps `given`. The always-there project keeps a name a person chose, and reads
    /// as `defaultName` when nothing was chosen: no name, a blank one, or a name the app gave it
    /// before (`retiredNames`, its package stem among them).
    static func displayName(forPath path: String, given: String?) -> String {
        guard isPackage(path: path) else { return given ?? "" }
        let trimmed = given?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if trimmed.isEmpty || retiredNames.contains(trimmed) {
            return defaultName
        }
        return trimmed
    }
}
