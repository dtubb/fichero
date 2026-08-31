import Foundation

// MARK: - Library-root drop routing (#4274)

/// One import batch: the URLs and the parent they should land under.
struct LibraryRootImportBatch: Equatable {
    /// nil = the library root itself.
    let parentId: String?
    let urls: [URL]
}

/// Split a root-level drop into import batches (#4274): directories import at
/// the ROOT — that is where the user dropped them — and so do plain files,
/// unless the user has MADE a root folder named "Inbox", in which case loose
/// files go there.
///
/// NOTHING here creates that folder (ruling 2026-08-31). A default Inbox was
/// interface crud: the library root IS the drop zone, and a bare root file is
/// perfectly visible in both surfaces that list roots — the sidebar
/// (`SidebarItemBuilder.isSidebarVisible` returns true for `.file`) and the
/// library pane (`/api/documents/roots`, which filters on `parent_id`, not
/// `doc_type`). The earlier premise that bare root files "disappear" was
/// simply wrong. The `inboxId` branch survives only as a courtesy: a user who
/// has made an Inbox folder has said where they want loose drops to go.
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
