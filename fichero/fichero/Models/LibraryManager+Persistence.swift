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
        UserDefaults.standard.set(paths, forKey: Self.openLibraryPathsKey)
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
        UserDefaults.standard.set(namesByPath, forKey: Self.libraryDisplayNamesByPathKey)
    }

    /// One-time, idempotent migration re-keying stored library paths/names to
    /// NFC (#3076). UserDefaults written before this normalization existed may
    /// hold NFD path strings (from the macOS filesystem); re-key them to NFC so
    /// they match the paths the app now writes and the backend registry uses.
    ///
    /// Merge-preferring-NFC on key collision (an NFD and an NFC entry for the
    /// same visual path collapse to the NFC key, keeping the value already under
    /// the NFC key) so a saved library is never dropped. Running twice is a
    /// no-op — NFC of NFC is itself, so the second pass finds nothing to change.
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
            // Pass 1: entries already NFC win the key outright.
            for (path, name) in names where path == path.nfcNormalized {
                migrated[path] = name
            }
            // Pass 2: NFD-origin entries only fill a key an NFC entry didn't claim.
            for (path, name) in names where path != path.nfcNormalized {
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
        UserDefaults.standard.dictionary(forKey: Self.libraryDisplayNamesByPathKey) as? [String: String] ?? [:]
    }

    /// Get previously open library paths
    func getSavedLibraryPaths() -> [String] {
        return UserDefaults.standard.stringArray(forKey: Self.openLibraryPathsKey) ?? []
    }

    /// Restore libraries from saved paths
    func restoreSavedLibraries() {
        guard backendIsReady else {
            libraryManagerLogger.info("Deferring saved-library restoration until backend ready")
            return
        }

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
            UserDefaults.standard.set(validPaths, forKey: Self.openLibraryPathsKey)
            libraryManagerLogger.info("Pruned \(paths.count - validPaths.count) missing/invalid library paths")
        }
    }
}
