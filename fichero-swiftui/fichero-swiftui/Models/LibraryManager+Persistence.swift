import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Library Persistence

extension LibraryManager {
    private static let openLibraryPathsKey = "FicheroOpenLibraryPaths"
    private static let libraryDisplayNamesByPathKey = "FicheroLibraryDisplayNamesByPath"

    /// Save current open library paths to UserDefaults
    func saveOpenLibraryPaths() {
        let paths = openLibraries.map { $0.url.path }
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

        for path in paths {
            // Validate path is not empty and doesn't contain dangerous characters
            guard !path.isEmpty,
                  !path.contains(".."),
                  path.hasPrefix("/") else {
                libraryManagerLogger.warning("Skipping invalid library path: \(path)")
                continue
            }

            let url = URL(fileURLWithPath: path)

            // Additional security check: ensure it's a .fichero package
            guard url.pathExtension == "fichero" else {
                libraryManagerLogger.warning("Skipping non-fichero path: \(path)")
                continue
            }

            if FileManager.default.fileExists(atPath: path) {
                let perLibraryStart = Date()
                let library = openLibrary(at: url)
                let perLibraryMs = Date().timeIntervalSince(perLibraryStart) * 1000
                libraryManagerLogger.info("⏱ Restored \(library.displayName): \(perLibraryMs, format: .fixed(precision: 1))ms")
            } else {
                libraryManagerLogger.warning("Saved library not found: \(path)")
            }
        }
    }
}
