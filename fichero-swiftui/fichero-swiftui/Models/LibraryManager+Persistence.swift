import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Library Persistence

extension LibraryManager {
    private static let openLibraryPathsKey = "FicheroOpenLibraryPaths"
    private static let libraryDisplayNamesByPathKey = "FicheroLibraryDisplayNamesByPath"

    /// Save current open library paths to UserDefaults.
    /// Excludes temporary/untitled libraries — those live in /var/folders/.../T/
    /// and get cleaned up by macOS, so persisting their paths would log
    /// "Saved library not found" warnings on every subsequent launch.
    func saveOpenLibraryPaths() {
        let paths = openLibraries
            .filter { !isTemporaryLibrary($0.url) }
            .map { $0.url.path }
        UserDefaults.standard.set(paths, forKey: Self.openLibraryPathsKey)
        saveLibraryDisplayNames()
        libraryManagerLogger.info("Saved \(paths.count) library paths to UserDefaults")
    }

    /// Save custom display names by library path.
    func saveLibraryDisplayNames() {
        let namesByPath = Dictionary(uniqueKeysWithValues: openLibraries.map { ($0.url.path, $0.displayName) })
        UserDefaults.standard.set(namesByPath, forKey: Self.libraryDisplayNamesByPathKey)
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
        let paths = getSavedLibraryPaths()
        libraryManagerLogger.info("⏱ Restoring \(paths.count) saved libraries")
        let overallStart = Date()
        defer {
            let overallMs = Date().timeIntervalSince(overallStart) * 1000
            libraryManagerLogger.info("⏱ restoreSavedLibraries total: \(overallMs, format: .fixed(precision: 1))ms for \(paths.count) libraries")
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
                libraryManagerLogger.info("⏱ Restored \(library.displayName): \(perLibraryMs, format: .fixed(precision: 1))ms")
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
