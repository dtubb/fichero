import Foundation

extension LibraryManager {
    /// Move a project's package to the Trash: recoverable, never an unlink, so a mistaken delete of an archive can be
    /// undone from the bin. The one place Delete Project (the sidebar) and a cancelled new project's Set Up go through.
    nonisolated static func trashPackage(at url: URL) throws {
        try FileManager.default.trashItem(at: url, resultingItemURL: nil)
    }

    /// Delete a project: close it first (`close`: the caller's own closing, which unregisters it), then move its package to
    /// the Trash through `trash`. The ONE sequence behind Delete Project (the sidebar) and a cancelled new project's Set Up
    /// (#6117); `trash` is the seam for a test. Throws what the Trash refused, after the project is closed.
    static func closeAndTrash(_ packageURL: URL, close: () -> Void,
                              trash: (URL) throws -> Void = { try LibraryManager.trashPackage(at: $0) }) throws {
        close()
        try trash(packageURL)
    }
}
