#if canImport(AppKit)
import AppKit
#endif
import Observation
import OSLog
import SwiftUI

/// Manages folder access permissions using security-scoped bookmarks
///
/// This class handles macOS security-scoped bookmarks to persist folder access permissions
/// across app launches. Required for accessing files outside the app's sandbox.

#if os(macOS)

@MainActor
@Observable
class FolderAccessManager {
    static let shared = FolderAccessManager()

    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FolderAccess")
    private let bookmarksKey = "FolderAccessBookmarks"
    private(set) var accessedFolders: [URL] = []

    /// Route to the RUNNING engine for handing over a freshly-minted bookmark (#3773).
    ///
    /// Injected by LibraryManager when it builds the API client — this manager is a
    /// singleton created long before any client exists, so it cannot construct one.
    /// nil until then, and permanently nil in the DMG build, which needs no handoff.
    @ObservationIgnored var engineAccessService: SandboxAccessService?

    /// The engine's refusal to open a folder we handed it, or nil when all is well.
    /// Observed, so the UI can say the folder is unreadable at the moment we learn it,
    /// instead of letting it resurface later as an inscrutable DuckDB permission error.
    private(set) var engineAccessFailure: String?

    private init() {
        restoreBookmarks()
    }

    /// Check if we have access to a file path (is it under an accessed folder?)
    func hasAccess(to path: String) -> Bool {
        let url = URL(fileURLWithPath: path)

        // Check if directly readable
        if FileManager.default.isReadableFile(atPath: path) {
            return true
        }

        // Check if under an accessed folder
        for folder in accessedFolders where url.path.hasPrefix(folder.path) {
            return true
        }
        return false
    }

    /// Request access to a folder (shows NSOpenPanel)
    func requestFolderAccess(suggestedPath: String? = nil, completion: @escaping (Bool) -> Void) {
        Task { @MainActor in
            let panel = NSOpenPanel()
            panel.canChooseFiles = false
            panel.canChooseDirectories = true
            panel.allowsMultipleSelection = false

            // Find the best parent folder to suggest
            var suggestedFolder: URL?
            if let path = suggestedPath {
                suggestedFolder = self.findBestParentFolder(for: path)
            }

            if let folder = suggestedFolder {
                panel.message = "Grant access to '\(folder.lastPathComponent)' folder"
                panel.prompt = "Grant Access"
                panel.directoryURL = folder.deletingLastPathComponent() // Navigate to parent so folder is visible
            } else {
                panel.message = "Select a folder to grant Fichero access"
                panel.prompt = "Grant Access"
            }

            panel.begin { response in
                if response == .OK, let selectedURL = panel.url {
                    self.saveBookmark(for: selectedURL)
                    completion(true)
                } else {
                    completion(false)
                }
            }
        }
    }

    /// Get the parent folder for a file path
    private func findBestParentFolder(for path: String) -> URL? {
        return URL(fileURLWithPath: path).deletingLastPathComponent()
    }

    /// The security-scoped bookmarks the SANDBOXED ENGINE needs, as
    /// `{"<path>": "<base64 bookmark>"}` JSON (#3747), or nil if it needs none.
    ///
    /// The engine cannot mint these itself: only the app holds the Powerbox grant
    /// the user created by picking the folder, and that grant is DYNAMIC, so it is
    /// not inherited by a child process. The app hands them over at spawn and the
    /// engine resolves them (`fichero/security_scoped_access.py`) before DuckDB
    /// opens anything.
    ///
    /// App Store build ONLY. The DMG engine is not sandboxed — it can already open
    /// the library directly — so it gets no env var at all. This is a hard gate,
    /// not an optimisation: without it the DMG app would ship its bookmarks to an
    /// unsandboxed engine, which would resolve them, be refused by
    /// startAccessingSecurityScopedResource(), and log a DENIED error per library
    /// on every launch — a behaviour change to a channel that must not change.
    func engineBookmarkPayload() -> String? {
        #if FICHERO_APP_STORE
        let stored = UserDefaults.standard.dictionary(forKey: bookmarksKey) as? [String: Data] ?? [:]
        return Self.bookmarkPayload(from: stored)
        #else
        return nil
        #endif
    }

    /// Pure JSON encoding of the payload — separated from UserDefaults so the wire
    /// format the engine parses can be unit-tested without a sandbox or a real grant.
    /// Must stay in step with `parse_bookmarks()` in `fichero/security_scoped_access.py`.
    static func bookmarkPayload(from stored: [String: Data]) -> String? {
        guard !stored.isEmpty else { return nil }
        let encoded = stored.mapValues { $0.base64EncodedString() }
        guard let data = try? JSONSerialization.data(withJSONObject: encoded) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// Mint a security-scoped bookmark for `url` and, unless it's a transient
    /// path, persist it to UserDefaults + register it in `accessedFolders`.
    /// Always returns the bookmark data (when minting succeeds) so the caller
    /// can hand it to the RUNNING engine — transient folders the app created
    /// via `loadFileRepresentation` (`/fichero-drop-UUID`, `/var/folders/…`)
    /// still need the engine to read them for the ONE ingest in flight, so we
    /// mint + grant even for transient paths and only skip PERSISTING them
    /// (a stored bookmark for a path that's deleted after ingest would fail to
    /// resolve on next launch and spam the log, #4068). Minting a
    /// `.withSecurityScope` bookmark for a non-security-scoped path throws and
    /// is caught → nil → no grant, which is the correct fallback for paths the
    /// engine can already reach (same-sandbox temp it inherits from the app).
    private func mintBookmark(for url: URL) -> Data? {
        let transient = isTransientPath(url)
        do {
            // Start accessing to create bookmark
            _ = url.startAccessingSecurityScopedResource()

            let bookmarkData = try url.bookmarkData(
                options: .withSecurityScope,
                includingResourceValuesForKeys: nil,
                relativeTo: nil
            )

            if transient {
                logger.debug("Minted transient bookmark (not persisted) for live engine grant: \(url.path)")
            } else {
                // Save to UserDefaults
                var bookmarks = UserDefaults.standard.dictionary(forKey: bookmarksKey) as? [String: Data] ?? [:]
                bookmarks[url.path] = bookmarkData
                UserDefaults.standard.set(bookmarks, forKey: bookmarksKey)

                // Add to accessed folders
                if !accessedFolders.contains(url) {
                    accessedFolders.append(url)
                }
                logger.info("Saved bookmark for: \(url.path)")
            }
            // Don't stop accessing - we need it throughout the app session
            return bookmarkData
        } catch {
            logger.error("Failed to mint bookmark for \(url.path): \(error.localizedDescription)")
            return nil
        }
    }

    /// Transient paths are short-lived temp dirs created by the drag-drop
    /// `loadFileRepresentation` path (`/fichero-drop-UUID`) or the system temp
    /// containers (`/var/folders/`, `/tmp/`). They must NOT be persisted as
    /// bookmarks (deleted after ingest → stale on next launch) but CAN be
    /// granted to the live engine for the one ingest in flight (#4068).
    private func isTransientPath(_ url: URL) -> Bool {
        url.path.contains("/fichero-drop-")
            || url.path.hasPrefix("/var/folders/")
            || url.path.hasPrefix("/tmp/")
    }

    /// Save a security-scoped bookmark, handing it to the RUNNING engine
    /// fire-and-forget (#3773). Fine for callers that don't immediately read the
    /// folder through the engine (the open panel, restore-refresh). Storing it is
    /// not enough on its own: the spawn-time payload is an environment variable,
    /// and an environment cannot change after the process starts — so a library
    /// picked now would be invisible to the live engine until the app relaunched.
    ///
    /// Callers that DO read the path through the engine right after (folder import,
    /// opening a package) must use `saveBookmarkIfDirectory`, which AWAITS the grant.
    func saveBookmark(for url: URL) {
        guard let bookmarkData = mintBookmark(for: url) else { return }
        handOffToEngine(path: url.path, bookmark: bookmarkData)
    }

    /// Hand a freshly-minted bookmark to the live engine, fire-and-forget. App
    /// Store build only. See `grantEngineAccess` for the ORDERED variant a caller
    /// can await before it reads the folder through the engine (#3773).
    ///
    /// Sound for sync callers because the grant is IDEMPOTENT on the engine and
    /// re-sent at every spawn via the env var, so the worst case is ordering: the
    /// open fails with a permission error the app surfaces, and the retry succeeds.
    private func handOffToEngine(path: String, bookmark: Data) {
        #if FICHERO_APP_STORE
        Task { @MainActor in
            // Fire-and-forget: this caller does not immediately read the path, so a
            // denial is swallowed here — it is still surfaced via engineAccessFailure
            // (set before the throw) and re-sent at the next spawn.
            try? await grantEngineAccess(path: path, bookmark: bookmark)
        }
        #endif
    }

    /// Await the engine's grant for a freshly-minted bookmark (#3773). The ordered
    /// counterpart to `handOffToEngine`: a caller about to open/ingest the path
    /// through the engine awaits this so the grant is in place BEFORE the engine
    /// reads it — otherwise the read races the grant and the library stays
    /// unreadable until the app relaunches.
    ///
    /// THROWS when a live engine grant is denied, so the caller stops rather than
    /// reading a folder the engine can't open. Returns normally (no throw) for the
    /// two legitimate no-grant-needed cases: before the engine client exists (the
    /// spawn-time env var covers anything minted that early) and on the
    /// non-App-Store build (no sandbox — nothing to grant).
    private func grantEngineAccess(path: String, bookmark: Data) async throws {
        #if FICHERO_APP_STORE
        guard let service = engineAccessService else {
            logger.debug("No engine access service yet; \(path) will be granted at next spawn")
            return
        }
        do {
            try await service.grantAccess(toPath: path, bookmark: bookmark)
            engineAccessFailure = nil
        } catch {
            // Loud AND fatal to the caller's engine work: the engine cannot read
            // this folder, so ingesting/opening it would fail later with an
            // inscrutable DuckDB permission error. Surface it and stop the read.
            logger.error("Engine refused folder access for \(path): \(error.localizedDescription)")
            engineAccessFailure = error.localizedDescription
            throw error
        }
        #endif
    }

    /// Persist access for a directory (a picked folder, or a `.fichero` package)
    /// and AWAIT the engine grant before returning, so a caller about to read that
    /// path through the engine can't race the grant (#3773). Captures permission
    /// at add-time so later reads do not re-prompt.
    ///
    /// THROWS if a live engine grant is denied — the caller must not proceed to
    /// read a path the engine can't open.
    func saveBookmarkIfDirectory(_ url: URL) async throws {
        var isDirectory: ObjCBool = false
        let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)
        guard exists, isDirectory.boolValue else {
            return
        }
        // Mint + grant even for transient paths (live grant only, no persist)
        // so the engine can read a `fichero-drop-UUID` folder for the one ingest
        // in flight (#4068). Returns nil when minting isn't possible — the
        // engine either inherits same-sandbox access or the grant is a no-op.
        guard let bookmarkData = mintBookmark(for: url) else { return }
        try await grantEngineAccess(path: url.path, bookmark: bookmarkData)
    }

    /// Restore bookmarks on app launch
    private func restoreBookmarks() {
        guard var bookmarks = UserDefaults.standard.dictionary(forKey: bookmarksKey) as? [String: Data] else {
            return
        }

        var changed = false
        for (path, bookmarkData) in bookmarks {
            // Prune any transient paths that slipped in from prior versions.
            if path.contains("/fichero-drop-") || path.hasPrefix("/var/folders/") || path.hasPrefix("/tmp/") {
                logger.debug("Removing stale transient bookmark: \(path)")
                bookmarks.removeValue(forKey: path)
                changed = true
                continue
            }
            do {
                var isStale = false
                let url = try URL(
                    resolvingBookmarkData: bookmarkData,
                    options: .withSecurityScope,
                    relativeTo: nil,
                    bookmarkDataIsStale: &isStale
                )

                // Start accessing the resource
                let didStart = url.startAccessingSecurityScopedResource()

                if isStale {
                    // Bookmark is stale, try to refresh it
                    logger.info("Stale bookmark for: \(path), refreshing...")
                    saveBookmark(for: url)
                } else if didStart {
                    accessedFolders.append(url)
                    logger.info("Restored access to: \(url.path)")
                }
            } catch {
                logger.error("Failed to restore bookmark for \(path): \(error.localizedDescription)")
                // Remove the unresolvable bookmark so it doesn't log on every launch.
                bookmarks.removeValue(forKey: path)
                changed = true
            }
        }

        if changed {
            UserDefaults.standard.set(bookmarks, forKey: bookmarksKey)
        }
    }

    /// Clear all bookmarks
    func clearAllAccess() {
        // Stop accessing all folders
        for url in accessedFolders {
            url.stopAccessingSecurityScopedResource()
        }
        accessedFolders.removeAll()
        UserDefaults.standard.removeObject(forKey: bookmarksKey)
    }
}

#else

// iOS stub: folder bookmarks are not used the same way in the app sandbox;
// call sites still compile and any access check falls back to readability.
@MainActor
@Observable
class FolderAccessManager {
    static let shared = FolderAccessManager()

    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FolderAccess")
    private let bookmarksKey = "FolderAccessBookmarks"
    private(set) var accessedFolders: [URL] = []

    private init() {}

    func hasAccess(to path: String) -> Bool {
        FileManager.default.isReadableFile(atPath: path)
    }

    func requestFolderAccess(suggestedPath: String? = nil, completion: @escaping (Bool) -> Void) {
        // iOS: no folder picker fallback; caller should use document picker.
        logger.info("requestFolderAccess is a no-op on iOS")
        completion(false)
    }

    func saveBookmark(for url: URL) {
        logger.debug("Bookmark persistence is macOS-only; ignoring on iOS for: \(url.path)")
    }

    func saveBookmarkIfDirectory(_ url: URL) async throws {
        // iOS: importing through document picker already grants access.
    }

    func clearAllAccess() {
        accessedFolders.removeAll()
        UserDefaults.standard.removeObject(forKey: bookmarksKey)
    }
}

#endif

// The grant-before-engine-read ordering seam (#3773), shared across platforms.
extension FolderAccessManager {
    /// Sequence the sandbox grant before engine work that reads the granted path.
    /// Both after-start attach paths — folder import and opening a package — route
    /// through here so the grant runs to completion FIRST; if the engine read
    /// raced ahead, a library added after the engine started would be unreadable
    /// until the app relaunched.
    ///
    /// A DENIED grant throws BEFORE `engineWork` runs, so the engine is never asked
    /// to read a path it can't open (the error propagates to the caller). One
    /// awaited seam so the ordering is unit-testable without a live sandbox
    /// (FICHERO_APP_STORE is off in the test target, so the real grant is a no-op
    /// there — this pins the contract both paths rely on).
    @MainActor
    static func grantThenEngineWork<T>(
        grant: () async throws -> Void,
        engineWork: () async throws -> T
    ) async rethrows -> T {
        try await grant()
        return try await engineWork()
    }
}
