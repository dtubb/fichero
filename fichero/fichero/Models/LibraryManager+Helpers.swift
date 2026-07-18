import FicheroAPIClient
import OSLog
import SwiftUI

extension LibraryManager {

    // MARK: - Public Helpers

    /// Check if a library URL is a temporary unsaved library
    /// Uses standardized paths to prevent path traversal attacks
    func isTemporaryLibrary(_ url: URL) -> Bool {
        let tempDir = FileManager.default.temporaryDirectory.standardizedFileURL
        let standardizedURL = url.standardizedFileURL

        // Ensure the path doesn't contain directory traversal
        guard !standardizedURL.path.contains("..") else {
            return false
        }

        return standardizedURL.path.hasPrefix(tempDir.path) &&
            standardizedURL.lastPathComponent.hasPrefix("Untitled-")
    }

    // MARK: - Internal Helpers

    /// Called after EmbeddedBackendService has connected to either the external
    /// development engine or the bundled engine. Until this point, restored
    /// libraries exist as UI state only and do not fire API requests (#1163).
    func backendDidBecomeReady() async {
        backendIsReady = true
        for library in openLibraries {
            library.reconfigureBackendHost()
            await loadLibraryDataIfNeeded(for: library)
        }
    }

    /// The library-side effects that fire when the engine reaches `.ready`,
    /// shared by BOTH platforms (#3113): refresh the known-library registry,
    /// adopt a paired remote library (self-guarded — a no-op unless the host is
    /// external), then reload every open library's data. This is the ONE place
    /// the ready transition hangs its side effects, replacing the copy in
    /// `FicheroApp.connectBackend` and `FicheroApp_iOS.reconnectToConfiguredHost`.
    /// The heartbeat (AppState) and iOS capture-queue resume layer on in the
    /// callers, since those aren't library concerns.
    func refreshAfterBackendBecameReady() async {
        // Flip readiness before any library work so restore's registry writes
        // cannot race the engine's socket bind.
        backendIsReady = true
        restoreSavedLibraries()
        await KnownLibraryRegistryStore.shared.refresh()
        adoptPairedRemoteLibrary()
        reconcileOpenLibrariesFromRegistry()
        await backendDidBecomeReady()
    }

    /// The open set the app shows must MIRROR the backend registry — the set of
    /// libraries the engine actually has open (#3393). Local UserDefaults restore
    /// alone drifts: the backend can hold a dozen open while the sidebar shows two
    /// (or shows one the backend already closed). Reconcile against the registry
    /// the store just fetched: open any registry library not yet open, and drop
    /// any open (non-Global) library the backend no longer lists.
    ///
    /// Local embedded backend only. For a remote host the registry is
    /// recents/known, NOT the set open for remote use (see
    /// `adoptPairedRemoteLibrary`), so remote reconciliation would over-open.
    func reconcileOpenLibrariesFromRegistry() {
        guard !EngineConfig.requiresExternalBackendConnection else { return }

        let registryPaths = KnownLibraryRegistryStore.shared.libraries.map(\.path)
        // Only reconcile against a snapshot that actually refreshed (#3988): a
        // failed fetch leaves `libraries` at its STALE value, so reconciling then
        // could drop a genuinely-open library against data we know is out of date.
        guard Self.shouldReconcile(
            fetchError: KnownLibraryRegistryStore.shared.fetchError,
            registryPaths: registryPaths
        ) else { return }

        let plan = Self.registryReconciliation(
            openLibraries: openLibraries.map { (id: $0.id, path: $0.url.path) },
            registryPaths: registryPaths,
            globalLibraryId: Self.globalLibraryId
        )

        for path in plan.pathsToOpen {
            let url = URL(fileURLWithPath: path)
            // Skip registry entries whose package is gone from disk — opening a
            // missing package would just fail; the backend row is stale.
            guard FileManager.default.fileExists(atPath: url.path) else { continue }
            _ = openLibrary(at: url, makeCurrent: false)
        }
        for id in plan.idsToDrop {
            // Local drop only — the backend already closed it (it's absent from
            // the registry), so no backend DELETE, unlike closeAndUnregisterLibrary.
            closeLibrary(id)
        }
    }

    /// Pure decision for whether `reconcileOpenLibrariesFromRegistry` may act on
    /// the current registry snapshot (#3988). Extracted so the guard is testable
    /// without the store / network.
    ///
    /// Reconcile ONLY when the last fetch had no error AND returned a non-empty
    /// set. A `fetchError` means `libraries` is stale (the failed fetch left the
    /// previous value in place) — reconciling could false-drop an open library.
    /// An empty list is still treated as "don't touch": it is ambiguous between a
    /// genuinely-empty backend registry and a fetch that failed on a cold store,
    /// and clearing the sidebar on that ambiguity is the worse failure. Turning a
    /// SUCCESSFUL-empty response into a reconcile-to-empty is deferred to #3988
    /// follow-up — it must first resolve the restore→registry-write ordering
    /// (a restored library's `noteOpenedLibrary` can still be in flight here).
    static func shouldReconcile(fetchError: String?, registryPaths: [String]) -> Bool {
        fetchError == nil && !registryPaths.isEmpty
    }

    /// Pure set-diff between the app's open libraries and the backend registry
    /// (#3393). Extracted so the reconciliation logic is unit-testable without
    /// LibraryReference / FileManager / network side effects. Paths are compared
    /// NFC-normalized (backend keys the registry NFC, #3071/#3076).
    static func registryReconciliation(
        openLibraries: [(id: UUID, path: String)],
        registryPaths: [String],
        globalLibraryId: UUID
    ) -> (pathsToOpen: [String], idsToDrop: [UUID]) {
        let registrySet = Set(registryPaths.map(\.nfcNormalized))
        let openSet = Set(openLibraries.map { $0.path.nfcNormalized })

        let pathsToOpen = registryPaths.filter { !openSet.contains($0.nfcNormalized) }
        let idsToDrop = openLibraries
            .filter { $0.id != globalLibraryId && !registrySet.contains($0.path.nfcNormalized) }
            .map(\.id)
        return (pathsToOpen, idsToDrop)
    }

    func reconfigureGeneratedClientsForCurrentHost() {
        for library in openLibraries {
            library.reconfigureBackendHost()
        }
    }

    /// Remote clients use only the library path explicitly advertised by the
    /// host's pairing payload. Do not infer from the host registry: registry
    /// entries are recents/known libraries, not the set currently open for
    /// remote use.
    func adoptPairedRemoteLibrary() {
        guard EngineConfig.requiresExternalBackendConnection else { return }
        let path = RemoteAccessConfig.pairedLibraryPath
        guard !path.isEmpty else { return }

        let remoteURL = URL(fileURLWithPath: path)
        if let current = globalLibrary, current.url.path == remoteURL.path {
            current.reconfigureBackendHost()
            return
        }

        let library = LibraryReference(
            url: remoteURL,
            document: FicheroDocument(),
            displayName: remoteURL.deletingPathExtension().lastPathComponent,
            id: Self.globalLibraryId,
            startAccessing: false
        )

        openLibraries.removeAll { $0.id == Self.globalLibraryId }
        openLibraries.insert(library, at: 0)
        currentLibraryId = library.id
        loadedLibraryIds.removeAll()
        loadingLibraryIds.removeAll()
        libraryManagerLogger.info("Adopted paired remote library: \(remoteURL.path, privacy: .public)")
    }

    /// Starts a library load immediately when the backend is ready, otherwise
    /// leaves it queued for backendDidBecomeReady().
    func scheduleLoadWhenBackendReady(for library: LibraryReference) {
        guard backendIsReady else {
            libraryManagerLogger.info("Deferring library load until backend ready: \(library.displayName)")
            return
        }

        Task { @MainActor in
            await loadLibraryDataIfNeeded(for: library)
        }
    }

    /// Initialize the backend database, load app data, and create Inbox once
    /// per library. Re-entrant guards avoid duplicate startup tasks when the
    /// window, restore, and backend-ready paths all observe the same library.
    func loadLibraryDataIfNeeded(for library: LibraryReference) async {
        // A security-scoped library must wait for its sandbox grant (#3986-A). The
        // grant's own engineWork re-enters here once it lands; until then this
        // path (restore / backendDidBecomeReady iterating open libraries) must not
        // read the package first and lose the #3773 race.
        guard !libraryIdsAwaitingGrant.contains(library.id) else {
            libraryManagerLogger.info(
                "Deferring library load until sandbox grant completes: \(library.displayName)"
            )
            return
        }

        guard !loadedLibraryIds.contains(library.id),
              !loadingLibraryIds.contains(library.id) else {
            return
        }

        loadingLibraryIds.insert(library.id)
        defer { loadingLibraryIds.remove(library.id) }

        // Ensure the .fichero package exists on disk (mkdir + Info.plist). Moved
        // off LibraryManager.shared's synchronous init so it no longer runs before
        // the first frame; idempotent, so running it per library is safe (#3974).
        createPackageStructure(at: library.url)
        await initializeBackendDatabase(for: library)
        await loadLibraryData(for: library)

        // A load that FAILED must not be marked loaded (#3986-B). DocumentStore
        // swallows a load error into `error`/`isConnected=false` (it never throws),
        // so a load that exhausts the #3972 retry would otherwise be recorded as
        // done forever — sidebar stuck empty until relaunch. Leave it unloaded so
        // the next trigger (heartbeat / reconnect / window .task) retries, and skip
        // Inbox creation which must never run against an unknown collections state.
        let store = library.documentStore
        guard Self.libraryLoadSucceeded(error: store.error, isConnected: store.isConnected) else {
            libraryManagerLogger.error(
                "Library load failed — leaving unloaded for retry: \(library.displayName)"
            )
            return
        }

        await ensureInboxFolder(for: library)
        loadedLibraryIds.insert(library.id)
        librariesLoadVersion += 1
    }

    /// Pure success test for a library's data load (#3986-B). `DocumentStore`
    /// signals a failed `loadCollections()` by leaving `error` non-nil and
    /// `isConnected == false` rather than throwing, so a load only counts as
    /// successful when the collections fetch connected AND recorded no error.
    /// Extracted so the load-gating decision is testable without the store.
    static func libraryLoadSucceeded(error: Error?, isConnected: Bool) -> Bool {
        error == nil && isConnected
    }

    /// Create the .fichero package directory structure
    func createPackageStructure(at url: URL) {
        let fileManager = FileManager.default

        do {
            // Create the package directory if it doesn't exist
            if !fileManager.fileExists(atPath: url.path) {
                try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
                libraryManagerLogger.info("Created .fichero package directory: \(url.path)")
            }

            // Create required subdirectories
            let contentsDir = url.appendingPathComponent("Contents")
            try fileManager.createDirectory(at: contentsDir, withIntermediateDirectories: true)

            // Create a simple plist to mark this as a package
            let infoPlistURL = contentsDir.appendingPathComponent("Info.plist")
            if !fileManager.fileExists(atPath: infoPlistURL.path) {
                let plistContent = """
                <?xml version="1.0" encoding="UTF-8"?>
                <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                <plist version="1.0">
                <dict>
                    <key>CFBundleIdentifier</key>
                    <string>app.fichero.fichero.library</string>
                    <key>CFBundleName</key>
                    <string>\(url.deletingPathExtension().lastPathComponent)</string>
                </dict>
                </plist>
                """
                try plistContent.write(to: infoPlistURL, atomically: true, encoding: .utf8)
            }

            libraryManagerLogger.info("Package structure ready at: \(url.path)")

        } catch {
            libraryManagerLogger.error("Failed to create package structure: \(error.localizedDescription)")
        }
    }

    /// Initialize the backend database for a library
    func initializeBackendDatabase(for library: LibraryReference) async {
        do {
            _ = try await library.apiClient.healthCheck()  // generated health_check op (#3030)
            libraryManagerLogger.info("Initialized backend database for: \(library.displayName)")
        } catch {
            libraryManagerLogger.error("Failed to initialize backend database: \(error.localizedDescription)")
        }
    }

    /// Load all data for a library (documents, searches, conversations, workflows)
    func loadLibraryData(for library: LibraryReference) async {
        libraryManagerLogger.info("⏱ loadLibraryData entry — library: \(library.displayName)")
        guard !Task.isCancelled else { return }
        await library.documentStore.loadCollections()
        let docCount = library.documentStore.collections.count
        libraryManagerLogger.info("⏱ loadLibraryData documents loaded (\(docCount) items)")

        guard !Task.isCancelled else { return }
        if FeatureManager.shared.isVisible(.workflows) {
            await library.workflowStore.loadWorkflows()
            libraryManagerLogger.info("⏱ loadLibraryData workflows loaded")
        }

        guard !Task.isCancelled else { return }
        if FeatureManager.shared.isVisible(.chat) {
            try? await library.conversationService.loadConversations()
            libraryManagerLogger.info("⏱ loadLibraryData conversations loaded")
        }

        guard !Task.isCancelled else { return }
        try? await library.savedSearchService.loadSavedSearches()
        libraryManagerLogger.info("⏱ loadLibraryData exit — library: \(library.displayName)")
    }

    /// Ensure every library has a default "Inbox" folder
    func ensureInboxFolder(for library: LibraryReference) async {
        // Never create against an unknown collections state (#3970). `hasInbox` is
        // inferred from `documentStore.collections`, which is empty both when the
        // library genuinely has no Inbox AND when the preceding load FAILED. In the
        // latter window creating "Inbox" makes a SECOND one against a library that
        // already has it. Bail if the load errored — the caller already leaves such
        // a library unloaded (#3986-B), so a later retry re-checks once the load
        // actually succeeds.
        guard library.documentStore.error == nil else {
            libraryManagerLogger.error(
                "Skipping Inbox check — preceding load errored: \(library.displayName)"
            )
            return
        }

        // Check if Inbox folder exists (collections should already be loaded)
        let hasInbox = library.documentStore.collections.contains { doc in
            doc.name == "Inbox" && doc.docType == .folder && doc.parentId == nil
        }

        let collectionCount = library.documentStore.collections.count
        libraryManagerLogger.info(
            "\(library.displayName) library has \(collectionCount) documents, hasInbox: \(hasInbox)"
        )

        if !hasInbox {
            // Create Inbox folder
            do {
                let inbox = try await library.documentService.createCollection(
                    name: "Inbox",
                    parentId: nil
                )
                libraryManagerLogger.info(
                    "Created default Inbox folder in \(library.displayName) library: \(inbox.id)"
                )

                // Reload documents to include the new Inbox
                await library.documentStore.loadCollections()
                let reloadedCount = library.documentStore.collections.count
                libraryManagerLogger.info("Reloaded collections, now have \(reloadedCount) documents")
            } catch {
                // Surface a persistent create failure instead of only logging
                // (#3970): record it on the store's error channel — the same
                // surface a failed collections load uses — so a library whose
                // Inbox never got created isn't left silently half-initialized.
                libraryManagerLogger.error(
                    "Failed to create Inbox folder in \(library.displayName): \(error.localizedDescription)"
                )
                library.documentStore.error = error
            }
        } else {
            libraryManagerLogger.info("Inbox folder already exists in \(library.displayName) library")
        }
    }
}
