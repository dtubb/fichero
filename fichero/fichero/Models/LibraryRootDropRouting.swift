import Foundation

// MARK: - Library-root drop routing (#4274)
//
// Dropping onto a library's TOP LEVEL (the header row, or the content pane
// while browsing root) used to route EVERYTHING into Inbox — the rationale
// being that bare files at root are invisible in the sidebar. Correct for
// files, wrong for FOLDERS: a folder is a first-class sidebar row at root, so
// redirecting a dropped folder into Inbox buries it where the user isn't
// looking — which reads as "the drop didn't import at all" (#4274).

/// One import batch: the URLs and the parent they should land under.
struct LibraryRootImportBatch: Equatable {
    /// nil = the library root itself.
    let parentId: String?
    let urls: [URL]
}

/// Split a root-level drop into import batches (#4274): directories import at
/// the ROOT (they're sidebar-visible there — that is where the user dropped
/// them), plain files route to Inbox when one exists (bare files at root are
/// invisible in the sidebar). With no Inbox, everything lands at root rather
/// than being dropped on the floor.
///
/// Pure over an injected `isDirectory` so the routing is testable without a
/// filesystem.
func libraryRootImportBatches(
    urls: [URL],
    inboxId: String?,
    isDirectory: (URL) -> Bool
) -> [LibraryRootImportBatch] {
    guard let inboxId else {
        return urls.isEmpty ? [] : [LibraryRootImportBatch(parentId: nil, urls: urls)]
    }
    let folders = urls.filter(isDirectory)
    let files = urls.filter { !isDirectory($0) }
    var batches: [LibraryRootImportBatch] = []
    if !folders.isEmpty {
        batches.append(LibraryRootImportBatch(parentId: nil, urls: folders))
    }
    if !files.isEmpty {
        batches.append(LibraryRootImportBatch(parentId: inboxId, urls: files))
    }
    return batches
}

/// Filesystem-backed `isDirectory` for the live call sites.
func libraryDropURLIsDirectory(_ url: URL) -> Bool {
    var isDirectory: ObjCBool = false
    let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)
    return exists && isDirectory.boolValue
}
