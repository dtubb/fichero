import FicheroAPIClient
import OSLog
import SwiftUI

extension LibraryManager {

    /// Open a library from a URL
    /// If already open, returns the existing reference
    /// - Parameters:
    ///   - url: URL to the .fichero package
    ///   - makeCurrent: When true, update `currentLibraryId` for same-window
    ///     open flows. New-window callers pass false and use the pending scene
    ///     handoff instead.
    /// - Returns: Library reference that can be shared across windows
    func openLibrary(at url: URL, makeCurrent: Bool = true) -> LibraryReference {
        // Check if already open. Compare CANONICAL keys, not raw `URL ==`: the
        // same package reached through a directory URL and a non-directory one
        // is not `==`, which is how a second Global library got opened (#4517).
        let key = Self.canonicalLibraryKey(url)
        if let existing = openLibraries.first(where: { Self.canonicalLibraryKey($0.url) == key }) {
            if makeCurrent {
                currentLibraryId = existing.id
            }
            Task {
                await KnownLibraryRegistryStore.shared.noteOpenedLibrary(
                    url: url,
                    displayName: existing.displayName
                )
            }
            libraryManagerLogger.info("Library already open: \(url.lastPathComponent)")
            return existing
        }

        // Create document for this library (state is managed by backend)
        let document = FicheroDocument()

        // Extract display name from file URL (remove .fichero extension)
        let defaultDisplayName = url.deletingPathExtension().lastPathComponent
        let displayName = getSavedLibraryDisplayNames()[url.path] ?? defaultDisplayName

        // Determine if this is a user-opened library (needs security-scoped access)
        let needsSecurityAccess = !isTemporaryLibrary(url)

        // Create new library reference
        // Note: apiClient.currentLibraryPath is set in LibraryReference.init()
        let library = LibraryReference(
            url: url,
            document: document,
            displayName: displayName,
            startAccessing: needsSecurityAccess
        )

        // Insert after Global library (which is always first)
        if openLibraries.first?.id == Self.globalLibraryId {
            openLibraries.insert(library, at: 1)
        } else {
            openLibraries.append(library)
        }

        if makeCurrent {
            currentLibraryId = library.id
        }
        let clientId = ObjectIdentifier(library.apiClient)
        let securityScoped = needsSecurityAccess
        libraryManagerLogger.info("""
            Opened library: \(url.lastPathComponent, privacy: .public) \
            with APIClient-\(String(describing: clientId), privacy: .public) \
            (security-scoped: \(securityScoped))
            """)

        // Save open libraries for restoration on next launch
        saveOpenLibraryPaths()

        promptForAccessIfUnavailable(url: url, needsSecurityAccess: needsSecurityAccess)

        loadAndRegister(library, at: url, displayName: displayName, needsSecurityAccess: needsSecurityAccess)

        return library
    }

    /// Ask for access when the library folder isn't readable, instead of opening
    /// a library that then silently can't read its files (#4217).
    ///
    /// `LibraryReference.startAccessingSecurityScope()` swallows a refused grant
    /// by design — `if url.startAccessingSecurityScopedResource()` — so a denied
    /// scope and a granted one look identical here. Nothing downstream checks,
    /// so the app proceeds, the engine reads nothing, and the user gets an empty
    /// library with no error to search for.
    ///
    /// This is most likely when a library was added in a NON-SANDBOXED build:
    /// minting a `.withSecurityScope` bookmark requires the sandbox entitlement,
    /// so `mintBookmark` throws and stores nothing. Opened later in a sandboxed
    /// build, there is no bookmark to restore and none could ever have existed.
    /// What that build should DO about it (re-mint? refuse?) is a product
    /// decision (#4217); prompting instead of failing silently is not.
    ///
    /// This paragraph used to say "Dev and DMG builds don't have" the
    /// entitlement. **Dev builds have been sandboxed since 2026-07-29**, so that
    /// reading is wrong and was load-bearing: it is the same stale premise that
    /// left `engineBookmarkPayload()` returning nil for a sandboxed Dev engine.
    /// The property that matters is `FolderAccessManager.isSandboxed`, asked at
    /// runtime — never the build channel.
    private func promptForAccessIfUnavailable(url: URL, needsSecurityAccess: Bool) {
        #if os(macOS)
        guard needsSecurityAccess,
              !FolderAccessManager.shared.hasAccess(to: url.path) else { return }

        libraryManagerLogger.warning(
            "No access to library folder: \(url.path, privacy: .public) — prompting"
        )
        FolderAccessManager.shared.requestFolderAccess(suggestedPath: url.path) { granted in
            libraryManagerLogger.info("Folder access prompt result: \(granted)")
            guard granted else { return }
            // The load that ran alongside this prompt failed without access
            // and was left unloaded — approval must re-trigger it, or the
            // user stares at the library they just granted until they reopen
            // it by hand (2026-08-12: "when I approved it, it didn't reload").
            Task { @MainActor in
                let manager = LibraryManager.shared
                guard let library = manager.openLibraries.first(
                    where: { $0.url.path == url.path }
                ) else { return }
                manager.libraryLoadRetryAttempts.removeValue(forKey: library.id)
                await manager.loadLibraryDataIfNeeded(for: library)
            }
        }
        #endif
    }

    /// Kick off the engine load + registry-add for a freshly opened library.
    ///
    /// For a user-picked package (needsSecurityAccess), grant the sandboxed engine
    /// access to it and AWAIT that grant BEFORE the load/registry requests, which
    /// are the engine's first reads of the package — otherwise they race the grant
    /// and the library stays unreadable until the app relaunches (#3773). Temporary
    /// libraries live in the app's own container and need no grant.
    private func loadAndRegister(
        _ library: LibraryReference,
        at url: URL,
        displayName: String,
        needsSecurityAccess: Bool
    ) {
        guard needsSecurityAccess else {
            scheduleLoadWhenBackendReady(for: library)
            Task {
                await KnownLibraryRegistryStore.shared.noteOpenedLibrary(url: url, displayName: displayName)
            }
            return
        }
        // Block any other load trigger (restore / backendDidBecomeReady) from
        // reading this package until the grant lands (#3986-A). Set SYNCHRONOUSLY,
        // before the Task, so a tight backend-ready loop can't slip a load in
        // between here and the grant scheduling.
        libraryIdsAwaitingGrant.insert(library.id)
        Task { @MainActor in
            // try?: a denied grant is already surfaced via engineAccessFailure and
            // must stop the load/registry (grantThenEngineWork skips engineWork on a
            // grant throw) without crashing the open.
            try? await FolderAccessManager.grantThenEngineWork(
                grant: { try await FolderAccessManager.shared.saveBookmarkIfDirectory(url) },
                engineWork: {
                    // Grant completed — clear the gate BEFORE scheduling the load so
                    // this path's own load is the first read of the package.
                    libraryIdsAwaitingGrant.remove(library.id)
                    scheduleLoadWhenBackendReady(for: library)
                    await KnownLibraryRegistryStore.shared.noteOpenedLibrary(url: url, displayName: displayName)
                }
            )
        }
    }

    /// Switch the whole app to a known-registry library by its (possibly remote)
    /// path — the iOS path for opening "more than just the default library" (#2394).
    ///
    /// Unlike `openLibrary(at:)` / the macOS `openRecentLibrary` flow, this makes
    /// NO local-filesystem assumptions: registry paths on iOS live on the paired
    /// Mac, so there is no security-scoped resource to acquire and no
    /// `FileManager.fileExists` gate (which would always fail for a remote path).
    /// The generated client talks to `EngineConfig.host` with `libraryPath` set to
    /// this path, so a fresh `LibraryReference` is a valid remote library.
    ///
    /// Reuses an already-open library at the same path; otherwise creates one and
    /// makes it current. Setting `currentLibraryId` re-roots the workspace via
    /// `LibraryWorkspaceSelection.activeLibrary`.
    @discardableResult
    func switchToRemoteLibrary(path: String, displayName: String? = nil) -> LibraryReference? {
        let trimmedPath = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedPath.isEmpty else { return nil }
        let url = URL(fileURLWithPath: trimmedPath)

        // Per-host recents (#3151): remember this library under the CURRENT
        // engine host so the remote-library picker can surface recents first,
        // scoped to the host they belong to (a path on the maintainer's Mac must never
        // leak into Ann's-Mac recents). Recorded on every remote open — reuse
        // included — so re-opening bumps it to the top.
        RemoteLibraryRecents.note(path: trimmedPath, host: EngineConfig.host.absoluteString)

        // Reuse if already open (compare by standardized path, not URL identity).
        if let existing = openLibraries.first(where: { $0.url.path == url.path }) {
            currentLibraryId = existing.id
            return existing
        }

        let resolvedName = displayName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let defaultName = url.deletingPathExtension().lastPathComponent
        let library = LibraryReference(
            url: url,
            document: FicheroDocument(),
            displayName: (resolvedName?.isEmpty == false ? resolvedName! : defaultName),
            startAccessing: false  // remote path — no local security scope
        )

        // Insert after Global (always first), matching openLibrary's ordering.
        if openLibraries.first?.id == Self.globalLibraryId {
            openLibraries.insert(library, at: 1)
        } else {
            openLibraries.append(library)
        }

        currentLibraryId = library.id
        scheduleLoadWhenBackendReady(for: library)
        libraryManagerLogger.info("Switched to remote library: \(url.path, privacy: .public)")
        return library
    }

    /// Create a new unsaved library
    /// - Returns: Library reference for a new library (not yet saved to disk)
    func createNewLibrary() -> LibraryReference {
        let document = FicheroDocument()

        // Generate Mac-style display name (Untitled, Untitled 2, Untitled 3, etc.)
        let displayName = untitledCounter == 1 ? "Untitled" : "Untitled \(untitledCounter)"

        // Each new library gets a unique temporary path so they're separate
        // Use FileManager.default.temporaryDirectory for sandbox compatibility
        let uuid = UUID().uuidString
        let temporaryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("Untitled-\(uuid).fichero")

        // Create the package structure even for temporary libraries
        // This ensures the backend database is created in the right place
        createPackageStructure(at: temporaryURL)

        // Note: apiClient.currentLibraryPath is set in LibraryReference.init()
        let library = LibraryReference(url: temporaryURL, document: document, displayName: displayName)

        // Insert after Global library (which is always first)
        if openLibraries.first?.id == Self.globalLibraryId {
            openLibraries.insert(library, at: 1)
        } else {
            openLibraries.append(library)
        }

        currentLibraryId = library.id  // Set as current library

        // Increment counter for next new library
        untitledCounter += 1

        let clientId = ObjectIdentifier(library.apiClient)
        let clientIdStr = String(describing: clientId)
        libraryManagerLogger.info("Created new unsaved library '\(displayName)' with APIClient-\(clientIdStr)")

        // Persist open libraries so newly-created databases can be restored on next launch.
        saveOpenLibraryPaths()

        scheduleLoadWhenBackendReady(for: library)

        return library
    }

    /// Get a library by ID
    func getLibrary(id: UUID) -> LibraryReference? {
        return openLibraries.first(where: { $0.id == id })
    }

    /// Rename a library display name (does not rename the package on disk).
    func renameLibrary(id: UUID, to newName: String) {
        let trimmed = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        guard id != Self.globalLibraryId else { return }  // Keep Global/Local fixed in 0.0.1
        guard let library = getLibrary(id: id) else { return }

        library.displayName = trimmed
        saveLibraryDisplayNames()
        libraryManagerLogger.info("Renamed library \(id.uuidString) to: \(trimmed)")
    }

    /// Close a library
    /// Only closes if no windows are using it
    /// Cannot close the Global library
    func closeLibrary(_ id: UUID) {
        // Prevent closing Global library
        if id == Self.globalLibraryId {
            libraryManagerLogger.warning("Cannot close Global library")
            return
        }

        guard let index = openLibraries.firstIndex(where: { $0.id == id }) else {
            return
        }

        let library = openLibraries[index]
        libraryManagerLogger.info("Closing library: \(library.url.lastPathComponent)")

        // Stop accessing security-scoped resource before removing
        library.stopAccessingSecurityScope()

        openLibraries.remove(at: index)

        // Update saved libraries
        saveOpenLibraryPaths()
    }

    /// Close a library AND unregister it from the global known-library
    /// registry (#1661). The .fichero package on disk is left untouched — this
    /// only removes the library from the open set and the registry, so it
    /// stops appearing in the sidebar and `library list`.
    ///
    /// The Global/Local library can't be closed.
    func closeAndUnregisterLibrary(_ id: UUID) {
        guard id != Self.globalLibraryId else {
            libraryManagerLogger.warning("Cannot close Global library")
            return
        }
        guard let library = getLibrary(id: id) else { return }

        let path = library.url.path
        let apiClient = library.apiClient

        // Remove from the open set immediately so the UI updates without
        // waiting on the network. The registry DELETE is idempotent on the
        // backend, so ordering doesn't matter for correctness.
        closeLibrary(id)

        // Best-effort unregister from the global registry. Failure here is
        // non-fatal — the library is already gone from the app's open set.
        //
        // This DELETE is ALSO the app→engine close (#3939): the engine's
        // `remove_known_library` handler calls `db_manager.close_database(path)`
        // before it removes the registry row (fichero-server .../library_registry.py,
        // added by #3393 c286b4e8b), so this releases the engine's DB handle/cache
        // — it is not a registry-only removal. There is no separate close endpoint
        // to call, and none should be invented.
        // Follow-up (#3939): reference-count shared opens — two windows can hold the
        // same library, and this close_database yanks the handle from the other
        // window. The engine close must key off the app's authoritative open set,
        // not a single window's close. Needs a backend refcount / open-set change.
        Task {
            do {
                // Generated remove_known_library op (#3030); runtime encodes the
                // path param, backend decodes it back to the raw filesystem path.
                let response = try await apiClient.api.removeKnownLibraryApiRegistryLibraryPathDelete(
                    path: .init(libraryPath: path)
                )
                if case .ok = response {
                    libraryManagerLogger.info("Unregistered library from registry: \(path, privacy: .public)")
                } else {
                    libraryManagerLogger.error(
                        "Failed to unregister library \(path, privacy: .public): unexpected registry response"
                    )
                }
            } catch {
                libraryManagerLogger.error(
                    "Failed to unregister library \(path, privacy: .public): \(error.localizedDescription)"
                )
            }
        }
    }

    // Save a library to a new URL (for Save As or initial save)
    func saveLibrary(_ id: UUID, to url: URL) throws {
        guard let index = openLibraries.firstIndex(where: { $0.id == id }) else {
            throw LibraryError.libraryNotFound
        }

        let oldLibrary = openLibraries[index]
        let oldURL = oldLibrary.url
        let fileManager = FileManager.default

        // Start accessing security-scoped resource from save panel
        let didStartAccessing = url.startAccessingSecurityScopedResource()
        libraryManagerLogger.info("Security-scoped resource access: \(didStartAccessing)")
        defer {
            if didStartAccessing {
                url.stopAccessingSecurityScopedResource()
            }
        }

        // Check if this is a temporary library
        let isTempLibrary = isTemporaryLibrary(oldURL)

        do {
            libraryManagerLogger.info("Old URL: \(oldURL.path)")
            libraryManagerLogger.info("New URL: \(url.path)")
            libraryManagerLogger.info("Is temporary library: \(isTempLibrary)")
            libraryManagerLogger.info("Old URL exists: \(fileManager.fileExists(atPath: oldURL.path))")

            try moveOrCreateSavedPackage(from: oldURL, to: url, isTempLibrary: isTempLibrary, fileManager: fileManager)

            // Extract display name from new file URL (remove .fichero extension)
            let displayName = url.deletingPathExtension().lastPathComponent

            // Stop accessing old library's security-scoped resource if needed
            oldLibrary.stopAccessingSecurityScope()

            let library = makeSavedLibraryReference(
                replacing: oldLibrary,
                at: index,
                url: url,
                displayName: displayName
            )

            // The user CHOSE this location in a save panel, so this is exactly
            // the moment access is minted — and until 2026-08-04 nothing minted
            // it. `startAccessingSecurityScopedResource()` above scopes THIS
            // process for the duration of the save; it stores nothing, hands the
            // engine nothing, and is released by the `defer`. So a library the
            // user created was readable by the app and refused by the engine,
            // which reported "Library path is not in an allowed location" for a
            // path the user had just picked.
            //
            // The open path (`loadAndRegister`) has always done this properly,
            // including awaiting the grant before the first read (#3773). Create
            // is the sibling that never got it — same outcome, separate route,
            // only one of them maintained. Routed through the same
            // `grantThenEngineWork` so there is ONE grant-then-load ordering in
            // the app, not two that can drift.
            let alreadyLoadable = isTempLibrary
            Task { @MainActor in
                if !alreadyLoadable {
                    // try?: a refused grant already surfaces on
                    // `engineAccessFailure`; it must stop the load rather than
                    // crash the save the user just completed.
                    try? await FolderAccessManager.grantThenEngineWork(
                        grant: { try await FolderAccessManager.shared.saveBookmarkIfDirectory(url) },
                        engineWork: {
                            loadedLibraryIds.remove(library.id)
                            scheduleLoadWhenBackendReady(for: library)
                        }
                    )
                }
                await KnownLibraryRegistryStore.shared.noteOpenedLibrary(
                    url: url,
                    displayName: displayName
                )
            }

        } catch {
            libraryManagerLogger.error("Failed to save library: \(error.localizedDescription)")
            throw LibraryError.saveFailed
        }
    }

    /// Move the temp package on disk to its new location, or create a fresh
    /// package structure for a Save As on an already-saved library.
    private func moveOrCreateSavedPackage(
        from oldURL: URL,
        to url: URL,
        isTempLibrary: Bool,
        fileManager: FileManager
    ) throws {
        if isTempLibrary && fileManager.fileExists(atPath: oldURL.path) {
            // Temporary libraries can be moved from sandbox temp dir
            libraryManagerLogger.info("Moving temporary library from \(oldURL.path) to \(url.path)")

            // Check if destination already exists
            if fileManager.fileExists(atPath: url.path) {
                libraryManagerLogger.warning("Destination exists, removing: \(url.path)")
                try fileManager.removeItem(at: url)
            }

            // Move the entire package directory
            try fileManager.moveItem(at: oldURL, to: url)
            libraryManagerLogger.info(
                "Successfully moved package from \(oldURL.lastPathComponent) to \(url.lastPathComponent)"
            )

        } else {
            // Not a temp library, create new package (for Save As on already-saved libraries)
            createPackageStructure(at: url)
            libraryManagerLogger.info("Created new package at: \(url.lastPathComponent)")
        }
    }

    /// Create the post-save `LibraryReference` (preserving ID and reusing
    /// APIClient/DocumentStore), point its clients at the new path, and store
    /// it back into `openLibraries` at `index`.
    private func makeSavedLibraryReference(
        replacing oldLibrary: LibraryReference,
        at index: Int,
        url: URL,
        displayName: String
    ) -> LibraryReference {
        // Create new library reference with saved URL, preserving the ID and reusing APIClient/DocumentStore
        // Always need security-scoped access for user-saved libraries
        let library = LibraryReference(
            url: url,
            document: oldLibrary.document,
            displayName: displayName,
            id: oldLibrary.id,  // IMPORTANT: Preserve library ID so windows don't lose track
            apiClient: oldLibrary.apiClient,  // Reuse existing APIClient
            documentStore: oldLibrary.documentStore,  // Reuse existing DocumentStore
            startAccessing: true  // Always start accessing for saved libraries
        )

        // Update the API client's library path to the new location
        library.apiClient.currentLibraryPath = url.path
        library.ficheroClient.currentLibraryPath = url.path

        // Update the reference in our array
        openLibraries[index] = library
        libraryManagerLogger.info("Saved library to: \(url.lastPathComponent)")

        return library
    }
}

/// Per-host MRU of remote library paths the user has opened (#3151). Backs the
/// remote-library picker's "recents first" ordering. Keyed by NORMALIZED host —
/// the same normalization the per-host session/device tokens use
/// (`AuthTokenMiddleware.normalizedRemoteHostString`) — so recents for one
/// engine never bleed into another's. Local-only (`UserDefaults`); never
/// carries a secret, just paths that live on that engine host.
enum RemoteLibraryRecents {
    private static let storageKey = "fichero.remote.recentLibraries"
    private static let maxPerHost = 12

    private static func hostKey(_ hostString: String) -> String {
        AuthTokenMiddleware.normalizedRemoteHostString(hostString: hostString)
    }

    private static func store() -> [String: [String]] {
        EngineConfig.defaults.dictionary(forKey: storageKey) as? [String: [String]] ?? [:]
    }

    /// Recently opened library paths for `hostString`, most-recent first.
    static func paths(forHost hostString: String) -> [String] {
        store()[hostKey(hostString)] ?? []
    }

    /// Record `path` as the most-recent open for `hostString`, de-duplicated and
    /// capped. No-op for a blank path.
    static func note(path: String, host hostString: String) {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let key = hostKey(hostString)
        var all = store()
        var list = all[key] ?? []
        list.removeAll { $0 == trimmed }
        list.insert(trimmed, at: 0)
        if list.count > maxPerHost { list = Array(list.prefix(maxPerHost)) }
        all[key] = list
        EngineConfig.defaults.set(all, forKey: storageKey)
    }

    /// Forget all recents for `hostString` — the hook for unpairing / removing a
    /// remote engine so its libraries stop appearing in the picker.
    static func clear(host hostString: String) {
        var all = store()
        all[hostKey(hostString)] = nil
        EngineConfig.defaults.set(all, forKey: storageKey)
    }
}
