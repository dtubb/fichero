import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Library Persistence

extension LibraryManager {
    // Not `private`: the NFC migration test (#3076) seeds these keys directly.
    static let openLibraryPathsKey = "FicheroOpenLibraryPaths"
    static let libraryDisplayNamesByPathKey = "FicheroLibraryDisplayNamesByPath"

    /// Save current open library paths to UserDefaults.
    /// Excludes temporary/untitled libraries — those live in /var/folders/.../T/
    /// and get cleaned up by macOS, so persisting their paths would log
    /// "Saved library not found" warnings on every subsequent launch.
    func saveOpenLibraryPaths() {
        // NFC-normalize every stored path (#3076) so UserDefaults holds the same
        // canonical bytes the app sends in the library header and the backend
        // registry uses — a re-open can never resolve to a duplicate NFD variant.
        let paths = openLibraries
            .filter { !isTemporaryLibrary($0.url) }
            .map { $0.url.path.nfcNormalized }
        EngineConfig.defaults.set(paths, forKey: Self.openLibraryPathsKey)
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

    /// Restore libraries from saved paths
    func restoreSavedLibraries() {
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

        for path in paths {
            // Validate path is not empty and doesn't contain dangerous characters
            guard !path.isEmpty,
                  !path.contains(".."),
                  path.hasPrefix("/") else {
                libraryManagerLogger.warning("Skipping invalid library path: \(path)")
                prunedAnyPath = true
                continue
            }

            let url = URL(fileURLWithPath: path)

            // Additional security check: ensure it's a .fichero package
            guard url.pathExtension == "fichero" else {
                libraryManagerLogger.warning("Skipping non-fichero path: \(path)")
                prunedAnyPath = true
                continue
            }

            if FileManager.default.fileExists(atPath: path) {
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
                prunedAnyPath = true
            }
        }

        // Persist the pruned list so missing paths don't keep failing on every launch.
        if prunedAnyPath {
            EngineConfig.defaults.set(validPaths, forKey: Self.openLibraryPathsKey)
            libraryManagerLogger.info("Pruned \(paths.count - validPaths.count) missing/invalid library paths")
        }
    }
}
