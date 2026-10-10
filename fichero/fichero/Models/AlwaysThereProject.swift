import Foundation

/// The always-there project: the engine's global library, on disk `global.fichero` in the app's
/// data folder (`fichero_server.db.paths.GLOBAL_LIBRARY_PACKAGE_NAME`). It has NO NAME in the UI
/// (ruled 2026-10-10, final, replacing "My Project"): the sidebar's top section has no heading row
/// and shows its own items (Sources, Workflows, Models) directly, and the projects a person sets up
/// are listed below under Projects, the Mail/Finder pattern. It cannot be closed, deleted or
/// renamed; it has no row to do any of that from. `sidebar.top-section-is-the-always-there-project`
/// and `library.always-there-project.*` in `docs/contributor_manual/specs/ui/sidebar-crud.md`.
nonisolated enum AlwaysThereProject {
    /// The package name on disk. Never changes.
    static let packageName = "global.fichero"

    /// Whether `path` is the always-there project's package. Matched by package NAME, as the
    /// engine's `is_global_library_package` does, because a sandboxed container and an
    /// unsandboxed build put it under different homes.
    static func isPackage(path: String) -> Bool {
        (path as NSString).lastPathComponent == packageName
    }

    /// The name shown for the project at `path`, given the name saved or recorded for it. Any other
    /// project keeps `given`. The always-there project has no name, whatever was saved for it before
    /// (Local, Global, My Library, Desk, My Project, or a rename made under the earlier ruling).
    static func displayName(forPath path: String, given: String?) -> String {
        isPackage(path: path) ? "" : (given ?? "")
    }
}

/// The sidebar's two parts (ruled 2026-10-10, `sidebar.top-section-is-the-always-there-project`,
/// `sidebar.projects-heading`): the always-there project's items at the top with no heading row,
/// then a Projects section listing every other open project. Pure over the library headers so the
/// split is testable without a rendered List.
enum SidebarProjectSections {
    /// The heading over the projects a person set up, drawn in the platform's sidebar section style.
    static let projectsHeading = "Projects"

    /// Splits `items` (one per open project, in sidebar order) into the always-there project's
    /// (drawn headless at the top) and the rest (under `projectsHeading`, order kept).
    static func split<Item>(
        _ items: [Item],
        libraryId: (Item) -> UUID?,
        alwaysThereId: UUID
    ) -> (top: Item?, projects: [Item]) {
        let top = items.first { libraryId($0) == alwaysThereId }
        let projects = items.filter { libraryId($0) != alwaysThereId }
        return (top, projects)
    }
}
