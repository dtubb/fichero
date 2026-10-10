import Foundation

/// What a window shows selected when it opens a project with no selection of its own (ruled
/// 2026-10-10, `sidebar.project.opens-on-sources`): the project's Sources folder, where its
/// material lands, never Workflows. A first launch opens on Sources, in the sidebar's top section
/// (the always-there project's); a project opened with no saved selection opens on its Sources too. The engine makes the folder
/// (`sidebar.project.has-a-sources-folder`) and names it; the app finds it by that name.
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
        if let restoredId { return restoredId }
        if viewModeType == "activity" { return "activity-browser" }
        guard viewModeType == "library" else { return nil }
        return sourcesFolder(in: roots).map { "doc:\($0.id)" }
    }

    /// The folder a project's store opens on when nothing is selected: its Sources, else its first
    /// top-level folder (a project made before Sources existed). Never a system folder such as
    /// Default Workflows while Sources is there.
    static func collectionToOpen(in collections: [Document]) -> Document? {
        sourcesFolder(in: collections) ?? collections.first { $0.parentId == nil }
    }
}
