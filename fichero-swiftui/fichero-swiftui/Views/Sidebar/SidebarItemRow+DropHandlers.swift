import OSLog
import SwiftUI

extension SidebarItemRow {
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
            targetFolderId = targetFolder.id
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

        let targetParentId: String?
        if case .document(let targetDoc) = targetItem.itemType {
            targetParentId = targetDoc.parentId
            sidebarRowLogger.debug(" Target parent ID: \(targetParentId ?? "root")")
        } else {
            sidebarRowLogger.debug(" ⚠️ Target item is not a document, cannot determine parent")
            return false
        }

        for itemID in itemIDs {
            sidebarRowLogger.debug(" Moving item \(itemID) to be sibling of \(targetItem.name)")

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

        guard case .document(let targetDoc) = targetFolder.itemType,
              targetDoc.docType == .folder else {
            sidebarRowLogger.warning("❌ Drop rejected: target \(targetFolder.name) is not a folder")
            return false
        }

        let docTypeDesc = String(describing: targetDoc.docType)
        sidebarRowLogger.debug("Target \(targetFolder.name) is valid folder (docType: \(docTypeDesc))")
        sidebarRowLogger.debug("Target document ID from doc: \(targetDoc.id)")

        for itemID in itemIDs {
            sidebarRowLogger.debug(" Processing drop of item ID: \(itemID)")

            guard itemID != targetFolder.id else {
                sidebarRowLogger.debug(" ⚠️ Drop rejected: cannot drop item onto itself")
                continue
            }

            if isDescendant(targetFolder.id, of: itemID) {
                sidebarRowLogger.debug(" ⚠️ Drop rejected: circular reference detected")
                continue
            }

            sidebarRowLogger.debug(" ✅ Validation passed, calling moveItemToFolder")
            sidebarRowLogger.debug("    Source ID: \(itemID)")
            sidebarRowLogger.debug("    Target ID: \(targetFolder.id)")
            Task {
                await moveItemToFolder(itemId: itemID, targetFolderId: targetFolder.id)
            }
        }
        sidebarRowLogger.debug(" ========== DROP COMPLETED ==========")
        return true
    }

    func handleDropOntoItem(itemIDs: [String], targetItem: SidebarItem) -> Bool {
        sidebarRowLogger.debug(" Drop onto non-folder item not supported")
        return false
    }
}
