import Foundation

/// What a window shows selected when it opens a project with no selection of its own (ruled
/// 2026-10-10, `sidebar.project.opens-on-sources`): the project's Sources folder, where its
/// material lands, never Workflows. A first launch opens on Sources, in the sidebar's top section
/// (the always-there project's); a project opened with no saved selection opens on its Sources too. The engine makes the folder
/// (`sidebar.project.has-a-sources-folder`) and names it; the app finds it by that name.
/// The order of a section's top-level items (ruled 2026-10-11, Daniel's first launch): Sources, then Workflows,
/// then the rest in the engine's own order; the section's Trash row is drawn after them all. The engine makes both
/// folders (Sources by name, `sidebar.project.has-a-sources-folder`; Workflows as `system-workflows`, which holds the
/// person's workflows and the locked Default Workflows folder inside it).
enum SidebarTopOrder {
    /// The engine's root Workflows folder.
    nonisolated static let workflowsFolderId = "system-workflows"

    /// 0 for Sources, 1 for Workflows, 2 for anything else; only a top-level folder can be either.
    nonisolated static func rank(_ document: Document) -> Int {
        guard document.parentId == nil, document.docType == .folder else { return 2 }
        if document.name == OpeningSelection.sourcesFolderName { return 0 }
        return document.id == workflowsFolderId ? 1 : 2
    }

    /// The items with Sources first and Workflows second; everything else keeps its order.
    static func ordered(_ items: [SidebarItem]) -> [SidebarItem] {
        func rank(_ item: SidebarItem) -> Int {
            if case .document(let document) = item.itemType { return Self.rank(document) }
            return 2
        }
        return items.enumerated()
            .sorted { lhs, rhs in (rank(lhs.element), lhs.offset) < (rank(rhs.element), rhs.offset) }
            .map(\.element)
    }
}

enum OpeningSelection {
    /// The name the engine gives every project's Sources folder (`importers/sources_folder.py`).
    static let sourcesFolderName = "Sources"

    /// The project's Sources folder among its top-level items, if it has one.
    static func sourcesFolder(in roots: [Document]) -> Document? {
        roots.first { $0.parentId == nil && $0.docType == .folder && $0.name == sourcesFolderName }
    }

    /// The sidebar selection id a window opens with: the one it restored; the Activity row for a
    /// window that was on Activity with no run; otherwise, for Items, the project's Sources
    /// folder (nil until the project's top level has loaded, or when it has no Sources).
    static func selectionId(restoredId: String?, viewModeType: String, roots: [Document]) -> String? {
        if let restoredId, restoredId != alwaysThereRootId { return restoredId }
        if viewModeType == "activity" { return "activity-browser" }
        guard viewModeType == "library" else { return nil }
        return sourcesFolder(in: roots).map { "doc:\($0.id)" }
    }

    /// The always-there project's own root, as a selection id. It is never a destination (Daniel, 2026-10-11):
    /// it has no row, and an Items list of its top level (Sources, Workflows) is not a place.
    static let alwaysThereRootId = "library:\(LibraryManager.globalLibraryId.uuidString)"

    /// What a selection routes to: itself, except the always-there project's root, which routes to that
    /// project's Sources (nil, so nothing, until its top level has loaded).
    static func destination(for selected: SidebarDestination, alwaysThereRoots: [Document]) -> SidebarDestination? {
        guard selected == .library(LibraryManager.globalLibraryId) else { return selected }
        return sourcesFolder(in: alwaysThereRoots).map { .document($0.id) }
    }

    /// A first launch: first run not done and no project known but the always-there one
    /// (`firstLaunchOffersSetUp`, ruled 2026-10-10).
    static func isFirstLaunch(firstRunCompleted: Bool, knownProjectPaths: [String]) -> Bool {
        firstLaunchOffersSetUp(firstRunCompleted: firstRunCompleted, knownProjectPaths: knownProjectPaths)
    }

    /// What a window's stored state is reset to on a first launch (Daniel, 2026-10-11): the sidebar shown
    /// (`.all`), the Items view, and no selection of its own, so the window selects the Sources folder as any
    /// project opens on it (`selectionId`, `collectionToOpen`). An old window's collapsed sidebar, its
    /// Workflows or Activity selection, never carry into a first launch.
    struct FirstLaunchState: Equatable {
        var columnVisibilityRaw = 2
        var viewModeType = "library"
        var viewModeItemId: String?
        var selectedItemId: String?
    }

    /// The folder a project's store opens on when nothing is selected: its Sources, else its first
    /// top-level folder (a project made before Sources existed). Never a system folder such as
    /// Default Workflows while Sources is there.
    static func collectionToOpen(in collections: [Document]) -> Document? {
        sourcesFolder(in: collections) ?? collections.first { $0.parentId == nil }
    }
}
