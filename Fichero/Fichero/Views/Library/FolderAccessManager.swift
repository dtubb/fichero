import SwiftUI
import AppKit
import OSLog

/// Manages folder access permissions using security-scoped bookmarks
///
/// This class handles macOS security-scoped bookmarks to persist folder access permissions
/// across app launches. Required for accessing files outside the app's sandbox.
class FolderAccessManager: ObservableObject {
    static let shared = FolderAccessManager()

    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "FolderAccess")
    private let bookmarksKey = "FolderAccessBookmarks"
    @Published private(set) var accessedFolders: [URL] = []

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
        DispatchQueue.main.async {
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

    /// Save a security-scoped bookmark
    func saveBookmark(for url: URL) {
        do {
            // Start accessing to create bookmark
            _ = url.startAccessingSecurityScopedResource()

            let bookmarkData = try url.bookmarkData(
                options: .withSecurityScope,
                includingResourceValuesForKeys: nil,
                relativeTo: nil
            )

            // Save to UserDefaults
            var bookmarks = UserDefaults.standard.dictionary(forKey: bookmarksKey) as? [String: Data] ?? [:]
            bookmarks[url.path] = bookmarkData
            UserDefaults.standard.set(bookmarks, forKey: bookmarksKey)

            // Add to accessed folders
            if !accessedFolders.contains(url) {
                accessedFolders.append(url)
            }

            logger.info("Saved bookmark for: \(url.path)")

            // Don't stop accessing - we need it throughout the app session
        } catch {
            logger.error("Failed to save bookmark: \(error.localizedDescription)")
        }
    }

    /// Restore bookmarks on app launch
    private func restoreBookmarks() {
        guard let bookmarks = UserDefaults.standard.dictionary(forKey: bookmarksKey) as? [String: Data] else {
            return
        }

        for (path, bookmarkData) in bookmarks {
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
            }
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
