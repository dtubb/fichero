#if canImport(AppKit)
import AppKit
#endif
import OSLog
import Observation
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

    /// Save a security-scoped bookmark
    func saveBookmark(for url: URL) {
        // Never bookmark transient temp paths — they're cleaned up after ingest
        // and will always fail to resolve on next launch, producing noisy errors.
        guard !url.path.contains("/fichero-drop-"),
              !url.path.hasPrefix("/var/folders/"),
              !url.path.hasPrefix("/tmp/") else {
            logger.debug("Skipping bookmark for transient path: \(url.path)")
            return
        }
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

    /// Persist access for a directory selected via file importer.
    /// This captures permission at add-time so later reads do not re-prompt.
    func saveBookmarkIfDirectory(_ url: URL) {
        var isDirectory: ObjCBool = false
        let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)
        guard exists, isDirectory.boolValue else {
            return
        }
        saveBookmark(for: url)
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

    func saveBookmarkIfDirectory(_ url: URL) {
        // iOS: importing through document picker already grants access.
    }

    func clearAllAccess() {
        accessedFolders.removeAll()
        UserDefaults.standard.removeObject(forKey: bookmarksKey)
    }
}

#endif
