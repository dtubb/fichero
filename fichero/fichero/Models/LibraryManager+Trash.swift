import Foundation

extension LibraryManager {
    /// Move a project's package to the Trash: recoverable, never an unlink, so a mistaken delete of an archive can be
    /// undone from the bin. The one place Delete Project (the sidebar) and a cancelled new project's Set Up go through.
    nonisolated static func trashPackage(at url: URL) throws {
        try FileManager.default.trashItem(at: url, resultingItemURL: nil)
    }
}
