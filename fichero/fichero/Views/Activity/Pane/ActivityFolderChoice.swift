import Foundation

/// A row's Choose Folder…: the project and the kept export the panel chooses a folder for.
struct ActivityFolderChoice: Equatable {
    let libraryId: UUID?
    let exportId: String
}
