import OSLog
import SwiftUI
import UniformTypeIdentifiers

extension SidebarItemRow {
    // MARK: - NSItemProvider-based file drop (preserves folder URLs, #587)

    /// Handles `.onDrop(of: [.fileURL])` — the NSItemProvider-based API.
    ///
    /// The Transferable-based `.dropDestination(for: URL.self)` unwraps a
    /// Finder folder drag into individual child-file URLs (the Transferable
    /// protocol expects URL to be a file resource). With NSItemProvider we
    /// get whatever the drag source contributed — for a folder drag, that's
    /// one provider holding the folder URL intact. `importService.importFiles`
    /// then correctly detects `isDirectory` and recurses.
    ///
    /// Closure returns `true` immediately while URLs load asynchronously; the
    /// actual import fires from within the Task so the drop destination
    /// contract (sync-return `Bool`) stays honored.
    func handleProvidersDrop(
        _ providers: [NSItemProvider],
        targetFolder: SidebarItem?
    ) -> Bool {
        // #600: use `canLoadObject(ofClass: URL.self)` — UTI-agnostic —
        // rather than `hasItemConformingToTypeIdentifier(fileURL)`. Some
        // Finder drag sources advertise only the content UTI (e.g. `.mov`
        // advertises `com.apple.quicktime-movie` but not always
        // `public.fileURL`), so the old UTI filter silently dropped the
        // provider before the URL-load even attempted. `canLoadObject`
        // asks the provider directly whether it can produce a URL, which
        // works for every file type Finder can drag, including `.mov`.
        let fileProviders = providers.filter { $0.canLoadObject(ofClass: URL.self) }
        guard !fileProviders.isEmpty else { return false }
        Task {
            var urls: [URL] = []
            for provider in fileProviders {
                if let url = try? await Self.loadURL(from: provider) {
                    urls.append(url)
                }
            }
            guard !urls.isEmpty else { return }
            _ = handleExternalFileDrop(urls: urls, targetFolder: targetFolder)
        }
        return true
    }

    private static func loadURL(from provider: NSItemProvider) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: URL.self) { url, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let url {
                    continuation.resume(returning: url)
                } else {
                    continuation.resume(throwing: NSError(domain: "SidebarInsertDrop", code: -1))
                }
            }
        }
    }

    func handleExternalFileDrop(urls: [URL], targetFolder: SidebarItem?) -> Bool {
        guard let importService else {
            sidebarRowLogger.warning("❌ External drop rejected: no import service for library")
            return false
        }

        let fileURLs = urls.filter { $0.isFileURL }
        guard !fileURLs.isEmpty else {
            sidebarRowLogger.warning("❌ External drop rejected: no file URLs")
            return false
        }

        let targetFolderId: String?
        if let targetFolder,
           case .document(let doc) = targetFolder.itemType,
           doc.docType == .folder {
            // Use the actual document ID, not the sidebar item ID (which has a "doc:" prefix)
            targetFolderId = doc.id
        } else {
            targetFolderId = nil
        }

        Task {
            do {
                _ = try await importService.importFiles(
                    fileURLs,
                    mode: .link,
                    parentId: targetFolderId
                )
                if let targetFolderId {
                    sidebarRowLogger.debug("✅ Imported \(fileURLs.count) external file(s) to folder \(targetFolderId)")
                } else {
                    sidebarRowLogger.debug("✅ Imported \(fileURLs.count) external file(s) to library root")
                }
                // Refresh twice: once immediately, again after 500ms to catch
                // the race where the backend hasn't finished indexing new
                // documents when the first refresh fires.
                await documentStore?.refresh()
                try? await Task.sleep(for: .milliseconds(500))
                await documentStore?.refresh()
            } catch {
                sidebarRowLogger.error("❌ External drop import failed: \(error.localizedDescription)")
            }
        }

        return true
    }

    func handleDropBesideItem(itemIDs: [String], targetItem: SidebarItem) -> Bool {
        sidebarRowLogger.debug(" ========== DROP BESIDE STARTED ==========")
        sidebarRowLogger.debug(" handleDropBesideItem called with \(itemIDs.count) items beside \(targetItem.name)")

        // Drop-beside today is documents-only: the target must be a
        // document leaf so we can determine its parentId. Saved-search /
        // workflow / conversation leaves don't have a parentId in the
        // same sense (they use folderPath strings), so we reject them
        // explicitly rather than silently falling through to
        // `documentStore.moveDocument` with a non-doc ID. Sidebar
        // review 2026-04-17 — cross-section drop-beside hole.
        let targetParentId: String?
        if case .document(let targetDoc) = targetItem.itemType {
            targetParentId = targetDoc.parentId
            sidebarRowLogger.debug(" Target parent ID: \(targetParentId ?? "root")")
        } else {
            sidebarRowLogger.debug(" ⚠️ Drop rejected: target \(targetItem.name) is not a document")
            return false
        }

        for itemID in itemIDs {
            let sourceKind = SidebarItemKind(prefixedId: itemID)
            sidebarRowLogger.debug(" Moving item \(itemID) (kind=\(String(describing: sourceKind))) to be sibling of \(targetItem.name)")

            // The sibling-reparent call path goes through
            // `documentStore.moveDocument`, which only accepts document
            // IDs. Reject non-document sources up front so the user sees
            // a deterministic no-op rather than a confusing silent
            // failure where the backend gets a saved-search UUID and
            // returns 404.
            guard sourceKind == .document else {
                let src = String(describing: sourceKind)
                sidebarRowLogger.debug(" ⚠️ Drop rejected: source kind \(src) cannot be reparented via document move")
                continue
            }

            guard itemID != targetItem.id else {
                sidebarRowLogger.debug(" ⚠️ Drop rejected: cannot drop item onto itself")
                continue
            }

            Task {
                if let parentId = targetParentId {
                    await moveItemToFolder(itemId: itemID, targetFolderId: parentId)
                } else {
                    let actualItemId = extractActualId(from: itemID)
                    guard let documentStore = documentStore else { return }
                    do {
                        _ = try await documentStore.moveDocument(actualItemId, toParent: nil)
                        sidebarRowLogger.debug(" ✅ Move to root successful")
                    } catch {
                        sidebarRowLogger.debug(" ❌ Move to root failed: \(error.localizedDescription)")
                    }
                }
            }
        }

        sidebarRowLogger.debug(" ========== DROP BESIDE COMPLETED ==========")
        return true
    }

    func handleDropIntoFolder(itemIDs: [String], targetFolder: SidebarItem) -> Bool {
        sidebarRowLogger.debug(" ========== DROP STARTED ==========")
        sidebarRowLogger.debug(" handleDropIntoFolder called with \(itemIDs.count) items onto \(targetFolder.name)")
        sidebarRowLogger.debug("Item IDs: \(itemIDs)")
        sidebarRowLogger.debug("Target folder ID: \(targetFolder.id)")
        sidebarRowLogger.debug("Target folder itemType: \(String(describing: targetFolder.itemType))")

        // #585 / sidebar plan Step 9: accept any folder row as a drop target
        // (document folders, search folders, workflow folders, chat folders).
        // `SidebarItem.folderKind` returns the enum kind the target accepts
        // and nil for anything that isn't a folder.
        guard let targetKind = targetFolder.folderKind else {
            sidebarRowLogger.warning("❌ Drop rejected: target \(targetFolder.name) is not a folder")
            return false
        }

        sidebarRowLogger.debug("Target \(targetFolder.name) is a \(String(describing: targetKind)) folder")

        for itemID in itemIDs {
            let sourceKind = SidebarItemKind(prefixedId: itemID)
            sidebarRowLogger.debug(" Processing drop of item ID: \(itemID) (kind=\(String(describing: sourceKind)))")

            // Cross-section drops aren't meaningful — e.g. dropping a
            // document onto a search folder has no backend contract. Reject
            // silently so the user can try again rather than getting a
            // spurious success toast.
            guard sourceKind == targetKind else {
                let src = String(describing: sourceKind)
                let tgt = String(describing: targetKind)
                sidebarRowLogger.debug(" ⚠️ Drop rejected: source (\(src)) and target (\(tgt)) sections differ")
                continue
            }

            guard itemID != targetFolder.id else {
                sidebarRowLogger.debug(" ⚠️ Drop rejected: cannot drop item onto itself")
                continue
            }

            if isDescendant(targetFolder.id, of: itemID) {
                sidebarRowLogger.debug(" ⚠️ Drop rejected: circular reference detected")
                continue
            }

            sidebarRowLogger.debug(" ✅ Validation passed, calling routeMove")
            sidebarRowLogger.debug("    Source ID: \(itemID)")
            sidebarRowLogger.debug("    Target ID: \(targetFolder.id)")
            Task {
                await routeMove(itemId: itemID, targetFolder: targetFolder)
            }
        }
        sidebarRowLogger.debug(" ========== DROP COMPLETED ==========")
        return true
    }

}
