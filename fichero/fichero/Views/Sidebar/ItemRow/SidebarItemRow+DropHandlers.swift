import OSLog
import SwiftUI
import UniformTypeIdentifiers

func sidebarTemporaryDropDirectories(for urls: [URL]) -> [URL] {
    externalDropTemporaryDirectories(for: urls)
}

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
        sidebarRowLogger.debug(
            "handleProvidersDrop: \(providers.count) provider(s), target=\(targetFolder?.name ?? "root")"
        )
        guard !providers.isEmpty else {
            sidebarRowLogger.warning("  no providers")
            return false
        }
        Task {
            var stableURLs: [URL] = []
            var tempURLs: [URL] = []
            for (idx, provider) in providers.enumerated() {
                if let url = try? await Self.loadAnyFileURL(from: provider) {
                    sidebarRowLogger.debug("  [\(idx)] loaded URL: \(url.lastPathComponent)")
                    // URLs from loadFileRepresentation land in a fichero-drop-UUID temp dir
                    // that macOS cleans up after the drop; they must be COPY-ingested so the
                    // backend moves them to permanent library storage before the dir disappears.
                    if url.path.contains("/fichero-drop-") {
                        tempURLs.append(url)
                    } else {
                        stableURLs.append(url)
                    }
                } else {
                    let utis = provider.registeredTypeIdentifiers.joined(separator: ", ")
                    sidebarRowLogger.warning("  [\(idx)] URL load failed for provider with UTIs: [\(utis)]")
                }
            }
            guard !stableURLs.isEmpty || !tempURLs.isEmpty else {
                sidebarRowLogger.warning("  all URL loads failed — import won't fire")
                return
            }
            if !stableURLs.isEmpty {
                _ = handleExternalFileDrop(urls: stableURLs, targetFolder: targetFolder, mode: .link)
            }
            if !tempURLs.isEmpty {
                sidebarRowLogger.debug("  \(tempURLs.count) temp-copy URL(s) → importing as COPY")
                _ = handleExternalFileDrop(urls: tempURLs, targetFolder: targetFolder, mode: .copy)
            }
        }
        return true
    }

    /// Load a file URL from an NSItemProvider using whichever API works
    /// for the provider's advertised UTIs (#4184: extracted to
    /// `ExternalFileDropLoader` so the root content-pane drop target
    /// shares the SAME fallback chain instead of a weaker one).
    /// `nonisolated` is load-bearing: `SidebarItemRow` is a View, so its
    /// statics inherit @MainActor, while `ExternalFileDropLoader` is a plain
    /// enum and is not isolated. Handing a non-Sendable `NSItemProvider`
    /// across that boundary is a data race — and the boundary only appeared
    /// when #4184 extracted the loader out of this type.
    nonisolated static func loadAnyFileURL(from provider: NSItemProvider) async throws -> URL {
        try await ExternalFileDropLoader.loadAnyFileURL(from: provider)
    }

    /// Which parent each dropped URL imports under. An explicit folder target
    /// takes everything; a root-level drop splits per #4274 — folders at the
    /// root itself (sidebar-visible there), bare files to Inbox so they don't
    /// disappear (invisible at root).
    private func externalDropBatches(
        fileURLs: [URL], targetFolder: SidebarItem?
    ) -> [LibraryRootImportBatch] {
        if let targetFolder,
           case .document(let doc) = targetFolder.itemType,
           doc.docType == .folder {
            return [LibraryRootImportBatch(parentId: doc.id, urls: fileURLs)]
        }
        let inboxId = documentStore?.collections.first(where: {
            $0.name == "Inbox" && $0.parentId == nil && $0.docType == .folder
        })?.id
        return libraryRootImportBatches(
            urls: fileURLs, inboxId: inboxId, isDirectory: libraryDropURLIsDirectory
        )
    }

    func handleExternalFileDrop(urls: [URL], targetFolder: SidebarItem?, mode: IngestMode = .link) -> Bool {
        guard let importService else {
            sidebarRowLogger.warning("External drop rejected: no import service for library")
            return false
        }

        let fileURLs = urls.filter { $0.isFileURL }
        guard !fileURLs.isEmpty else {
            sidebarRowLogger.warning("External drop rejected: no file URLs")
            return false
        }
        let temporaryDirectories = sidebarTemporaryDropDirectories(for: fileURLs)

        let batches = externalDropBatches(fileURLs: fileURLs, targetFolder: targetFolder)

        Task {
            defer {
                for tempDir in temporaryDirectories {
                    try? FileManager.default.removeItem(at: tempDir)
                }
            }
            // Clear any stale drop-error banner before this import so a prior
            // failure doesn't linger over a now-successful drop (#2384; matches
            // the move paths that clear at start).
            await MainActor.run { sidebarState.dropErrorMessage = nil }
            do {
                for batch in batches {
                    _ = try await importService.importFiles(
                        batch.urls,
                        mode: mode,
                        parentId: batch.parentId
                    )
                    if let parentId = batch.parentId {
                        sidebarRowLogger.debug(
                            "Imported \(batch.urls.count) external file(s) to folder \(parentId)"
                        )
                    } else {
                        sidebarRowLogger.debug(
                            "Imported \(batch.urls.count) external file(s) to library root"
                        )
                    }
                }
                // The engine emits a per-file ``document.created`` change event
                // as each file is ingested, so the DocumentStore patches the
                // sidebar incrementally while the import runs (#4065). This
                // trailing refresh is the prompt completion signal the store
                // observes even if a per-file event was lost in flight, and
                // replaces the old double-refresh + 500ms sleep that made the
                // sidebar lag the spinner stop (#4067).
                await documentStore?.refresh()
            } catch {
                sidebarRowLogger.error("External drop import failed: \(error.localizedDescription)")
                // Surface the failure to the user, not just the log — a file drop
                // that silently fails to import must not look like it was added
                // (#2384 acceptance: "the UI reports the failure and does not
                // pretend the file was added"). Uses the same `dropErrorMessage`
                // sidebar surface as the move-failure paths (#2344), for one
                // consistent drop-error banner.
                await MainActor.run { sidebarState.dropErrorMessage = error.localizedDescription }
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
            sidebarRowLogger.debug(" Drop rejected: target \(targetItem.name) is not a document")
            return false
        }

        let documentIds = itemIDs.filter { itemID in
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
                sidebarRowLogger.debug(" Drop rejected: source kind \(src) cannot be reparented via document move")
                return false
            }

            guard itemID != targetItem.id else {
                sidebarRowLogger.debug(" Drop rejected: cannot drop item onto itself")
                return false
            }

            return true
        }

        guard !documentIds.isEmpty else {
            sidebarRowLogger.debug(" No document moves to perform")
            return true
        }

        performTransactionalSiblingReparent(
            documentIds: documentIds,
            targetParentId: targetParentId
        )

        sidebarRowLogger.debug(" ========== DROP BESIDE COMPLETED ==========")
        return true
    }

    private func performTransactionalSiblingReparent(
        documentIds: [String],
        targetParentId: String?
    ) {
        guard let documentStore else { return }

        Task {
            await MainActor.run {
                sidebarState.dropErrorMessage = nil
            }
            let moveResult = await moveSidebarDocumentsTransactionally(
                documentIds,
                toParent: targetParentId,
                move: { itemId, parentId in
                    _ = try await documentStore.moveDocument(
                        extractActualId(from: itemId),
                        toParent: parentId
                    )
                },
                refresh: {
                    await documentStore.refresh()
                }
            )

            guard moveResult.isSuccessful else {
                await MainActor.run {
                    sidebarState.dropErrorMessage = moveResult.errorMessage
                }
                return
            }
        }
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
            sidebarRowLogger.warning("Drop rejected: target \(targetFolder.name) is not a folder")
            return false
        }

        sidebarRowLogger.debug("Target \(targetFolder.name) is a \(String(describing: targetKind)) folder")

        var movedCount = 0
        var asyncOps: [(SidebarDropOperation, String)] = []
        var skips = SidebarDropSkipSummary()
        // Sampled ONCE at the drop moment: ⌥-drop copies document payloads,
        // ⌘⌥-drop makes aliases at the target (Finder modifier grammar).
        let modifiersAtDrop = SidebarDropModifiers.current()
        // The Inbox drag sentinel is an empty id — never a real row, so it
        // must not count as a "skipped item" in the user-facing summary.
        for itemID in itemIDs where !itemID.isEmpty {
            switch processFolderDropItem(
                itemID,
                targetKind: targetKind,
                targetFolder: targetFolder,
                modifiers: modifiersAtDrop,
                skips: &skips
            ) {
            case .moved:
                movedCount += 1
            case .asyncOp(let operation, let bareId):
                asyncOps.append((operation, bareId))
            case .skipped:
                break
            }
        }
        finishFolderDrop(
            targetFolder: targetFolder,
            movedCount: movedCount,
            asyncOps: asyncOps,
            skips: skips
        )
        sidebarRowLogger.debug(" ========== DROP COMPLETED ==========")
        return true
    }

    /// The banner reports REAL outcomes: moves are optimistic (as they always
    /// were), but copies/aliases are awaited before anything claims success —
    /// a review finding: the old banner counted dispatched Tasks as applied,
    /// then contradicted itself when they failed.
    private func finishFolderDrop(
        targetFolder: SidebarItem,
        movedCount: Int,
        asyncOps: [(SidebarDropOperation, String)],
        skips: SidebarDropSkipSummary
    ) {
        let folderId = extractActualId(from: targetFolder.id)
        Task {
            var applied = movedCount
            var failed = 0
            for (operation, bareId) in asyncOps {
                let succeeded: Bool
                switch operation {
                case .copy:
                    succeeded = await copyDocumentIntoFolder(documentId: bareId, folderId: folderId)
                case .alias:
                    succeeded = await aliasDocumentIntoFolder(documentId: bareId, folderId: folderId)
                case .move:
                    succeeded = true
                }
                if succeeded { applied += 1 } else { failed += 1 }
            }
            if let message = sidebarDropOutcomeMessage(
                applied: applied, failed: failed, skips: skips
            ) {
                // Keep the last specific executor error visible alongside the
                // aggregate ("... 2 failed. <reason>").
                let specific = failed > 0 ? sidebarState.dropErrorMessage : nil
                await MainActor.run {
                    sidebarState.dropErrorMessage = [message, specific]
                        .compactMap { $0 }
                        .joined(separator: " ")
                }
            }
        }
    }

    enum FolderDropItemOutcome {
        case moved
        case asyncOp(SidebarDropOperation, bareId: String)
        case skipped
    }

    /// Validate one dropped item against the target: moves dispatch
    /// optimistically (.moved); copies/aliases are RETURNED for the caller's
    /// aggregate Task so the summary can report real outcomes; skip reasons
    /// accumulate in `skips`.
    private func processFolderDropItem(
        _ itemID: String,
        targetKind: SidebarItemKind,
        targetFolder: SidebarItem,
        modifiers: SidebarDropModifiers,
        skips: inout SidebarDropSkipSummary
    ) -> FolderDropItemOutcome {
        let sourceKind = SidebarItemKind(prefixedId: itemID)
        sidebarRowLogger.debug(" Processing drop of item ID: \(itemID) (kind=\(String(describing: sourceKind)))")

        // Cross-section drops aren't meaningful — e.g. dropping a
        // document onto a search folder has no backend contract.
        guard sourceKind == targetKind else {
            skips.crossSection += 1
            return .skipped
        }
        guard itemID != targetFolder.id else {
            skips.selfDrop += 1
            return .skipped
        }
        if isDescendant(targetFolder.id, of: itemID) {
            skips.circular += 1
            return .skipped
        }

        let operation = sidebarDropOperation(modifiers: modifiers, kind: sourceKind)
        switch operation {
        case .copy, .alias:
            sidebarRowLogger.debug(" modifier-drop (\(String(describing: operation))): \(itemID) → \(targetFolder.id)")
            return .asyncOp(operation, bareId: extractActualId(from: itemID))
        case .move:
            sidebarRowLogger.debug(" Validation passed, routeMove \(itemID) → \(targetFolder.id)")
            Task {
                await routeMove(itemId: itemID, targetFolder: targetFolder)
            }
            return .moved
        }
    }

}
