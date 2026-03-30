import SwiftUI
import OSLog
import FicheroAPIClient

// MARK: - Library Persistence

extension LibraryManager {
    private static let openLibraryPathsKey = "FicheroOpenLibraryPaths"

    /// Save current open library paths to UserDefaults
    func saveOpenLibraryPaths() {
        let paths = openLibraries.map { $0.url.path }
        UserDefaults.standard.set(paths, forKey: Self.openLibraryPathsKey)
        libraryManagerLogger.info("Saved \(paths.count) library paths to UserDefaults")
    }

    /// Get previously open library paths
    func getSavedLibraryPaths() -> [String] {
        return UserDefaults.standard.stringArray(forKey: Self.openLibraryPathsKey) ?? []
    }

    /// Restore libraries from saved paths
    func restoreSavedLibraries() {
        let paths = getSavedLibraryPaths()
        libraryManagerLogger.info("Restoring \(paths.count) saved libraries")

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
                let library = openLibrary(at: url)
                libraryManagerLogger.info("Restored library: \(library.displayName)")
            } else {
                libraryManagerLogger.warning("Saved library not found: \(path)")
            }
        }
    }
}
