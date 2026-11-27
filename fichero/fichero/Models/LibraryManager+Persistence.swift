import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Library Persistence

extension LibraryManager {
    // Not `private`: the NFC migration test (#3076) seeds these keys directly.
    static let openLibraryPathsKey = "FicheroOpenLibraryPaths"
    static let libraryDisplayNamesByPathKey = "FicheroLibraryDisplayNamesByPath"
    /// The shared libraries open on a paired Mac, `[["host": root, "path": path]]` (`sharing.guest.library-pinned-to-its-host`).
    static let pinnedLibrariesKey = "FicheroPinnedLibraries"

    /// Save current open library paths to UserDefaults.
    /// Excludes temporary/untitled libraries — those live in /var/folders/.../T/
    /// and get cleaned up by macOS, so persisting their paths would log
    /// "Saved library not found" warnings on every subsequent launch.
    ///
    /// Also excludes the Global/Local library (#4517): it is opened by
    /// CONSTRUCTION in `LibraryManager.init` → `loadGlobalLibrary`, on every
    /// launch, before restore runs. Persisting its path means restore opens it a
    /// SECOND time from a differently-constructed URL — the duplicate-Global bug.
    /// It cannot be lost by omitting it: nothing else can close it
    /// (`closeLibrary` / `closeAndUnregisterLibrary` both refuse `globalLibraryId`).
    func saveOpenLibraryPaths() {
        // NFC-normalize every stored path (#3076) so UserDefaults holds the same
        // canonical bytes the app sends in the library header and the backend
        // registry uses — a re-open can never resolve to a duplicate NFD variant.
        let paths = openLibraries
            .filter { $0.id != Self.globalLibraryId && !$0.pinnedToHost && !isTemporaryLibrary($0.url) }
            .map { $0.url.path.nfcNormalized }
        // A saved library whose volume has not answered yet is still saved (#7105): it is not open, so the list of
        // open libraries alone would drop it.
        let saved = paths + unansweredSavedLibraryPaths.filter { !paths.contains($0) }
        EngineConfig.defaults.set(saved, forKey: Self.openLibraryPathsKey)
        // A pinned library's path is a path on ANOTHER Mac: kept apart, never restored as a local one.
        EngineConfig.defaults.set(
            openLibraries.filter(\.pinnedToHost).map { ["host": $0.host.url.absoluteString, "path": $0.url.path] },
            forKey: Self.pinnedLibrariesKey)
        saveLibraryDisplayNames()
        libraryManagerLogger.info("Saved \(paths.count) library paths to UserDefaults")
    }

    /// Save custom display names by library path. Keys are NFC-normalized (#3076)
    /// so they match the NFC paths written above.
    func saveLibraryDisplayNames() {
        let namesByPath = Dictionary(
            openLibraries.map { ($0.url.path.nfcNormalized, $0.displayName) },
            uniquingKeysWith: { _, latest in latest }
        )
        EngineConfig.defaults.set(namesByPath, forKey: Self.libraryDisplayNamesByPathKey)
    }

    /// One-time, idempotent migration re-keying stored library paths/names to
    /// NFC (#3076). UserDefaults written before this normalization existed may
    /// hold NFD path strings (from the macOS filesystem); re-key them to NFC so
    /// they match the paths the app now writes and the backend registry uses.
    ///
    /// #4024: compares at the unicode-scalar level — Swift `String ==` is canonical (an NFD
    /// string equals its NFC form), so a byte-level check is the only way to tell an already-NFC
    /// key from an NFD one. A surviving NFD-origin key is re-keyed to NFC, keeping any value
    /// already stored under the NFC key. Note: a genuine NFD+NFC key collision is already
    /// collapsed to a single entry by the UserDefaults NSDictionary→Swift bridge on read
    /// (Swift-equal keys), so this never observes both to arbitrate — it re-keys whichever
    /// single representation survived. Running twice is a no-op — NFC of NFC is itself, so the
    /// second pass finds nothing to change.
    /// `static` + injectable `defaults` so it is testable without the singleton.
    static func migrateStoredPathsToNFC(defaults: UserDefaults = .standard) {
        // Open-paths array: normalize, then de-dup preserving order (NFD+NFC of
        // the same library collapse to one — the library is kept, not lost).
        if let paths = defaults.stringArray(forKey: openLibraryPathsKey) {
            var seen = Set<String>()
            let migrated = paths
                .map { $0.nfcNormalized }
                .filter { seen.insert($0).inserted }
            if migrated != paths {
                defaults.set(migrated, forKey: openLibraryPathsKey)
            }
        }

        // Display-names dict keyed by path: re-key to NFC, values preserved.
        if let names = defaults.dictionary(forKey: libraryDisplayNamesByPathKey) as? [String: String] {
            var migrated: [String: String] = [:]
            // Pass 1: entries already NFC win the key outright. #4024: compare at the
            // UNICODE-SCALAR level — Swift `String ==` is canonical (an NFD string equals
            // its own NFC form), so `path == path.nfcNormalized` was true for EVERY path and
            // could never distinguish an already-NFC entry from an NFD one — the NFC-wins
            // preference was unreachable.
            for (path, name) in names
            where path.unicodeScalars.elementsEqual(path.nfcNormalized.unicodeScalars) {
                migrated[path] = name
            }
            // Pass 2: NFD-origin entries only fill a key an NFC entry didn't claim.
            for (path, name) in names
            where !path.unicodeScalars.elementsEqual(path.nfcNormalized.unicodeScalars) {
                let key = path.nfcNormalized
                if migrated[key] == nil { migrated[key] = name }
            }
            if migrated != names {
                defaults.set(migrated, forKey: libraryDisplayNamesByPathKey)
            }
        }
    }

    /// Get custom display names by library path.
    func getSavedLibraryDisplayNames() -> [String: String] {
        EngineConfig.defaults.dictionary(forKey: Self.libraryDisplayNamesByPathKey) as? [String: String] ?? [:]
    }

    /// Get previously open library paths
    func getSavedLibraryPaths() -> [String] {
        if let testLibrary = uiTestRestoredLibraryURL() {
            return [testLibrary.path]
        }
        return EngineConfig.defaults.stringArray(forKey: Self.openLibraryPathsKey) ?? []
    }

    /// Reopens the shared libraries that were open, beside the local ones, for each host still paired. The current library
    /// stays what restore made it. The host is not asked here: an unanswering one shows its own failure when used.
    func restorePinnedLibraries(
        saved: [[String: String]], paired: Set<String> = Set(PairedMachineStore.load().map(\.id))
    ) {
        let current = currentLibraryId
        for entry in saved {
            guard let host = entry["host"], paired.contains(host), let root = URL(string: host), let path = entry["path"] else { continue }
            _ = switchToRemoteLibrary(path: path, pinnedTo: root)
        }
        currentLibraryId = current
        saveOpenLibraryPaths()  // the list now says what is open (a host no longer paired is dropped)
    }

    /// The shared libraries saved last time. Read BEFORE the local libraries reopen: each reopen saves the open list, which
    /// has no shared library in it yet and would write this key empty.
    static func savedPinnedLibraries() -> [[String: String]] {
        EngineConfig.defaults.array(forKey: pinnedLibrariesKey) as? [[String: String]] ?? []
    }

    /// Restore libraries from saved paths.
    ///
    /// Whether each path exists is asked off the main thread, every path at once, and this waits `probeTimeout` for the
    /// answers (#7105): a saved library on an unmounted, slow or iCloud volume held the main thread for as long as the
    /// volume took. A path that has not answered is not opened and not pruned; `savedLibraryAnsweredLate` opens it
    /// when its answer arrives. `exists` is the test seam for a volume that does not answer.
    func restoreSavedLibraries(
        probeTimeout: TimeInterval = SavedLibraryProbe.timeout,
        exists: @escaping @Sendable (String) -> Bool = { FileManager.default.fileExists(atPath: $0) }
    ) {
        let pinned = Self.savedPinnedLibraries()
        // No backend-ready guard (launch-speed, #4036): materializing a
        // LibraryReference is purely local (UserDefaults paths + security
        // scope), per-library DATA loads already defer through
        // `scheduleLoadWhenBackendReady`, and the registry write in
        // `noteOpenedLibrary` is best-effort with a silent catch. Restoring
        // eagerly lets the first window frame mount the library shell while
        // the engine is still booting; `refreshAfterBackendBecameReady` calls
        // this again (idempotent) and then loads data.

        // Canonicalize any legacy NFD-keyed defaults before reading them (#3076);
        // idempotent, so running on every launch is harmless.
        Self.migrateStoredPathsToNFC()
        let paths = getSavedLibraryPaths()
        libraryManagerLogger.info("⏱ Restoring \(paths.count) saved libraries")
        let overallStart = Date()
        defer {
            let overallMs = Date().timeIntervalSince(overallStart) * 1000
            let libraryCount = paths.count
            libraryManagerLogger.info(
                "⏱ restoreSavedLibraries total: \(overallMs, format: .fixed(precision: 1))ms for \(libraryCount) libs"
            )
        }

        var validPaths: [String] = []
        var prunedAnyPath = false

        // Self-heal defaults written before #4517: the Global library's path may
        // already be stored. `openLibrary`'s canonical dedup now returns the
        // existing reference rather than a duplicate, but dropping the entry here
        // means an install stops carrying it after one launch.
        let globalKey = globalLibrary.map { Self.canonicalLibraryKey($0.url) }

        let restorable = paths.filter { restorablePathIsValid($0) }
        if restorable.count < paths.count { prunedAnyPath = true }
        let answers = askSavedLibraries(restorable, probeTimeout: probeTimeout, exists: exists)

        for path in restorable {
            let url = URL(fileURLWithPath: path)

            if unansweredSavedLibraryPaths.contains(path) {
                noteSavedLibraryDidNotAnswer(path, within: probeTimeout)
                validPaths.append(path)
            } else if answers[path] == .present, let globalKey, Self.canonicalLibraryKey(url) == globalKey {
                // Compared only once the path has answered: the canonical key resolves symlinks on its volume.
                libraryManagerLogger.info("Skipping Global library in restore list (#4517)")
                prunedAnyPath = true
            } else if answers[path] == .present {
                let perLibraryStart = Date()
                let library = openLibrary(at: url)
                let perLibraryMs = Date().timeIntervalSince(perLibraryStart) * 1000
                LaunchProfile.milestone(
                    "restored library",
                    detail: "\(library.displayName) \(Int(perLibraryMs))ms"
                )
                libraryManagerLogger.info(
                    "⏱ Restored \(library.displayName): \(perLibraryMs, format: .fixed(precision: 1))ms"
                )
                validPaths.append(path)
            } else {
                libraryManagerLogger.warning("Pruning missing saved library: \(path)")
                MissingLibraryNotice.shared.report(path)
                prunedAnyPath = true
            }
        }

        // Persist the pruned list so missing paths don't keep failing on every launch.
        if prunedAnyPath {
            EngineConfig.defaults.set(validPaths, forKey: Self.openLibraryPathsKey)
            libraryManagerLogger.info("Pruned \(paths.count - validPaths.count) missing/invalid library paths")
        }
        restorePinnedLibraries(saved: pinned)
    }

    /// Asks whether each path exists, off the main thread, and records the ones that did not answer in time (#7105).
    private func askSavedLibraries(
        _ restorable: [String], probeTimeout: TimeInterval, exists: @escaping @Sendable (String) -> Bool
    ) -> [String: SavedLibraryProbe.Answer] {
        // A path still waiting from an earlier call is not asked again: its answer comes to `savedLibraryAnsweredLate`.
        let waiting = unansweredSavedLibraryPaths
        let answers = SavedLibraryProbe.answers(
            for: restorable.filter { !waiting.contains($0) },
            timeout: probeTimeout,
            exists: exists,
            late: { path, found in
                Task { @MainActor in LibraryManager.shared.savedLibraryAnsweredLate(path: path, exists: found) }
            }
        )
        // Set before any library opens: `openLibrary` saves the list, and these must be in it.
        unansweredSavedLibraryPaths = restorable.filter { waiting.contains($0) || answers[$0] == .unanswered }
        return answers
    }

    private func noteSavedLibraryDidNotAnswer(_ path: String, within timeout: TimeInterval) {
        libraryManagerLogger.warning("Saved library did not answer within \(timeout)s, opening it when it does: \(path)")
        LaunchProfile.milestone("saved library did not answer", detail: (path as NSString).lastPathComponent)
    }

    /// The answer for a saved library whose volume was slower than restore's timeout (#7105): it opens beside the others
    /// without taking the window, or is reported missing as restore reports one.
    func savedLibraryAnsweredLate(path: String, exists: Bool) {
        guard unansweredSavedLibraryPaths.contains(path) else { return }
        unansweredSavedLibraryPaths.removeAll { $0 == path }
        if exists {
            let library = openLibrary(at: URL(fileURLWithPath: path), makeCurrent: false)
            LaunchProfile.milestone("restored library (late answer)", detail: library.displayName)
        } else {
            libraryManagerLogger.warning("Pruning missing saved library: \(path)")
            MissingLibraryNotice.shared.report(path)
            saveOpenLibraryPaths()
        }
    }

    /// True when `path` lies inside a Trash folder: a volume's `.Trashes` or the home `.Trash`
    /// (#6377). A library moved there is not one the person has open; the engine refuses it
    /// at every launch, so it leaves the reopen list.
    nonisolated static func isInsideTrash(_ path: String) -> Bool {
        let parts = (path as NSString).pathComponents
        return parts.contains(".Trashes") || parts.contains(".Trash")
    }

    /// A restore-list entry the loop should attempt: non-empty absolute
    /// `.fichero` path with no traversal. Reads no file: the Global library (#4517) is told apart in the loop.
    private func restorablePathIsValid(_ path: String) -> Bool {
        guard !path.isEmpty, !path.contains(".."), path.hasPrefix("/") else {
            libraryManagerLogger.warning("Skipping invalid library path: \(path)")
            return false
        }
        let url = URL(fileURLWithPath: path)
        guard url.pathExtension == "fichero" else {
            libraryManagerLogger.warning("Skipping non-fichero path: \(path)")
            return false
        }
        if Self.isInsideTrash(path) {
            libraryManagerLogger.info("Dropping saved library inside a Trash folder (#6377): \(path)")
            return false
        }
        return true
    }
}
