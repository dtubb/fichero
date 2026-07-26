import OSLog
import SwiftUI
import UniformTypeIdentifiers

func sidebarTemporaryDropDirectories(for urls: [URL]) -> [URL] {
    Array(
        Set(
            urls
                .filter { $0.path.contains("/fichero-drop-") }
                .map { $0.deletingLastPathComponent() }
        )
    )
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
    /// for the provider's advertised UTIs.
    ///
    /// Finder drag providers come in multiple shapes and require
    /// different loading strategies:
    ///   - Providers advertising `public.file-url` or conformant UTIs
    ///     respond to `loadObject(ofClass: URL.self)` directly.
    ///   - Providers advertising only content UTIs like `public.jpeg`
    ///     or `public.movie` do NOT respond to `loadObject(URL.self)`
    ///     — `canLoadObject(URL.self)` returns false — but DO respond
    ///     to `loadFileRepresentation(forTypeIdentifier:)` with their
    ///     advertised UTI. This is the case the user hit 2026-04-17
    ///     with a Finder .JPG drag advertising only `public.jpeg`.
    ///
    /// This helper tries `loadObject(URL.self)` first (cheapest and
    /// works for most drags), then falls back to iterating the
    /// provider's registered UTIs and asking each for a file
    /// representation until one produces a URL.
    ///
    /// Returns the URL (copied into a stable location if the provider
    /// supplied a temp path) or throws if no representation yields
    /// anything readable.
    static func loadAnyFileURL(from provider: NSItemProvider) async throws -> URL {
        let utis = provider.registeredTypeIdentifiers
        let canURL = provider.canLoadObject(ofClass: URL.self)
        sidebarRowLogger.debug("loadAnyFileURL: canLoadURL=\(canURL) UTIs=[\(utis.joined(separator: ", "))]")

        // Cheapest path first: direct URL load if the provider advertises it.
        if canURL {
            sidebarRowLogger.debug("  → trying direct URL load (canLoadObject=true)")
            do {
                let url = try await loadURL(from: provider)
                sidebarRowLogger.debug("  direct URL load succeeded: \(url.lastPathComponent) [\(url.pathExtension)]")
                return url
            } catch {
                sidebarRowLogger.warning(
                    "  direct URL load failed despite canLoadObject=true: \(error.localizedDescription)"
                )
                // Fall through to representation-based fallback rather than throwing,
                // in case the provider lied about canLoadObject (seen with some .mov drags).
            }
        }

        // Otherwise iterate the provider's registered UTIs and ask each
        // for a file representation until one produces a URL. This is the
        // case for Finder drags advertising only a content UTI like
        // `public.jpeg` — they don't respond to `loadObject(URL.self)`
        // but do respond to `loadFileRepresentation(forTypeIdentifier:)`.
        guard !utis.isEmpty else {
            sidebarRowLogger.warning("  provider has no UTIs and canLoadObject=false — no path available")
            throw NSError(
                domain: "SidebarDrop",
                code: -1,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Provider advertises neither URL nor any type identifiers"
                ]
            )
        }
        sidebarRowLogger.debug("  → trying loadFileRepresentation fallback for \(utis.count) UTI(s)")
        for identifier in utis {
            sidebarRowLogger.debug("    trying UTI: \(identifier)")
            if let url = try? await loadFileRepresentation(
                from: provider,
                typeIdentifier: identifier
            ) {
                sidebarRowLogger.debug("    representation succeeded for UTI \(identifier): \(url.lastPathComponent)")
                return url
            } else {
                sidebarRowLogger.debug("    representation failed for UTI \(identifier)")
            }
        }
        sidebarRowLogger.warning(
            "  all \(utis.count) UTI representation(s) failed; UTIs=[\(utis.joined(separator: ", "))]"
        )
        throw NSError(
            domain: "SidebarDrop",
            code: -1,
            userInfo: [
                NSLocalizedDescriptionKey:
                    "No representation yielded a file URL; advertised UTIs: \(utis)"
            ]
        )
    }

    /// Wraps `NSItemProvider.loadFileRepresentation(forTypeIdentifier:
    /// completionHandler:)` as async/throws. The provider hands us a
    /// temporary file URL valid only until the completion returns, so
    /// we copy the file to Fichero's caches directory before resolving
    /// — otherwise the import pipeline would race against the temp
    /// file being deleted.
    private static func loadFileRepresentation(
        from provider: NSItemProvider,
        typeIdentifier: String
    ) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadFileRepresentation(
                forTypeIdentifier: typeIdentifier
            ) { temporaryURL, error in
                if let error {
                    sidebarRowLogger.debug("      loadFileRepresentation(\(typeIdentifier)) callback error: \(error.localizedDescription)")
                    continuation.resume(throwing: error)
                    return
                }
                guard let temporaryURL else {
                    sidebarRowLogger.debug(
                        "      loadFileRepresentation(\(typeIdentifier)) callback: nil URL, no error"
                    )
                    continuation.resume(throwing: NSError(
                        domain: "SidebarDrop",
                        code: -2,
                        userInfo: [NSLocalizedDescriptionKey: "Empty URL from loadFileRepresentation"]
                    ))
                    return
                }
                sidebarRowLogger.debug("      loadFileRepresentation(\(typeIdentifier)) temp URL: \(temporaryURL.path)")
                // Copy to a stable caches path — the temporaryURL is
                // deleted as soon as this closure returns.
                let destinationDir = FileManager.default.temporaryDirectory
                    .appendingPathComponent("fichero-drop-\(UUID().uuidString)")
                do {
                    try FileManager.default.createDirectory(at: destinationDir, withIntermediateDirectories: true)
                    let destination = destinationDir.appendingPathComponent(temporaryURL.lastPathComponent)
                    try FileManager.default.copyItem(at: temporaryURL, to: destination)
                    sidebarRowLogger.debug("      copied to stable path: \(destination.path)")
                    continuation.resume(returning: destination)
                } catch {
                    sidebarRowLogger.debug("      copy to stable path failed: \(error.localizedDescription)")
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private static func loadURL(from provider: NSItemProvider) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: URL.self) { url, error in
                if let error {
                    sidebarRowLogger.debug("      loadObject(URL) error: \(error.localizedDescription)")
                    continuation.resume(throwing: error)
                } else if let url {
                    sidebarRowLogger.debug("      loadObject(URL) → \(url.absoluteString)")
                    continuation.resume(returning: url)
                } else {
                    sidebarRowLogger.debug("      loadObject(URL) → nil URL, no error")
                    continuation.resume(throwing: NSError(domain: "SidebarInsertDrop", code: -1))
                }
            }
        }
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

        var targetFolderId: String?
        if let targetFolder,
           case .document(let doc) = targetFolder.itemType,
           doc.docType == .folder {
            targetFolderId = doc.id
        } else {
            // No explicit folder target — route to Inbox so the file doesn't
            // disappear (bare files at library root are invisible in the sidebar).
            targetFolderId = documentStore?.collections.first(where: {
                $0.name == "Inbox" && $0.parentId == nil && $0.docType == .folder
            })?.id
        }

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
                _ = try await importService.importFiles(
                    fileURLs,
                    mode: mode,
                    parentId: targetFolderId
                )
                if let targetFolderId {
                    sidebarRowLogger.debug("Imported \(fileURLs.count) external file(s) to folder \(targetFolderId)")
                } else {
                    sidebarRowLogger.debug(
                        "Imported \(fileURLs.count) external file(s) to library root (no Inbox found)"
                    )
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
        var skips = SidebarDropSkipSummary()
        // The Inbox drag sentinel is an empty id — never a real row, so it
        // must not count as a "skipped item" in the user-facing summary.
        for itemID in itemIDs where !itemID.isEmpty {
            let sourceKind = SidebarItemKind(prefixedId: itemID)
            sidebarRowLogger.debug(" Processing drop of item ID: \(itemID) (kind=\(String(describing: sourceKind)))")

            // Cross-section drops aren't meaningful — e.g. dropping a
            // document onto a search folder has no backend contract.
            guard sourceKind == targetKind else {
                let src = String(describing: sourceKind)
                let tgt = String(describing: targetKind)
                sidebarRowLogger.debug(" Drop rejected: source (\(src)) and target (\(tgt)) sections differ")
                skips.crossSection += 1
                continue
            }

            guard itemID != targetFolder.id else {
                sidebarRowLogger.debug(" Drop rejected: cannot drop item onto itself")
                skips.selfDrop += 1
                continue
            }

            if isDescendant(targetFolder.id, of: itemID) {
                sidebarRowLogger.debug(" Drop rejected: circular reference detected")
                skips.circular += 1
                continue
            }

            sidebarRowLogger.debug(" Validation passed, calling routeMove")
            sidebarRowLogger.debug("    Source ID: \(itemID)")
            sidebarRowLogger.debug("    Target ID: \(targetFolder.id)")
            movedCount += 1
            Task {
                await routeMove(itemId: itemID, targetFolder: targetFolder)
            }
        }
        // Partial application is never silent: say what was skipped and why
        // (#7 from the audit; clean drops produce no banner).
        if let message = sidebarDropSkipMessage(moved: movedCount, skips: skips) {
            sidebarState.dropErrorMessage = message
        }
        sidebarRowLogger.debug(" ========== DROP COMPLETED ==========")
        return true
    }

}
