#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import SwiftUI

#if os(macOS)

// MARK: - Initialization & window/library actions

// Split out of LibraryWindow.swift (file_length/type_body_length): the plain
// initialization and menu-action methods live here so the main file keeps only
// the type-checker-budgeted `body` chain and its #3163-tuned sheet/task wiring.
// The stored properties these methods touch are `internal` (not `private`) in
// LibraryWindow.swift precisely so this same-type, cross-file extension can
// reach them.
extension LibraryWindow {

    // MARK: - Initialization

    func initializeWindow() {
        libraryWindowLogger.info("""
            initializeWindow - openLibraries=\(libraryManager.openLibraries.count), \
            currentLibraryId=\(libraryManager.currentLibraryId?.uuidString ?? "nil")
            """)

        // Priority 0: a WindowSeed (Duplicate Window, #2262) clones an existing
        // window's library + selection + active lens. Write the #2273
        // scene-storage keys BEFORE the library mounts so ContentView restores
        // into the cloned state, then assign the seeded library via the shared
        // assignLibrary path (which also persists it for next launch).
        if let seed, let resolvedId = resolveSeedLibrary(seed) {
            sceneSelectedItemId = seed.selectedItemId
            sceneViewModeType = seed.viewModeType ?? "library"
            sceneViewModeItemId = seed.viewModeItemId
            assignLibrary(id: resolvedId)
            libraryWindowLogger.info("Seeded duplicated window from library: \(resolvedId)")
            return
        }

        if let pendingId = libraryManager.pendingWindowLibraryIds.first,
           libraryManager.getLibrary(id: pendingId) != nil {
            libraryWindowLogger.info("Consuming pendingWindowLibraryId: \(pendingId)")
            libraryManager.pendingWindowLibraryIds.removeFirst()
            assignLibrary(id: pendingId)
            return
        }

        // Priority 0: Restore the library this scene was showing last time.
        if let persistedLibraryId,
           let restoredId = UUID(uuidString: persistedLibraryId),
           libraryManager.getLibrary(id: restoredId) != nil {
            libraryWindowLogger.info("Restoring persisted libraryId: \(restoredId)")
            assignLibrary(id: restoredId)
            return
        }

        // Priority 1: Use currentLibraryId (set by handleOpenURL or restoreSavedLibraries)
        if let currentId = libraryManager.currentLibraryId,
           libraryManager.getLibrary(id: currentId) != nil {
            libraryWindowLogger.info("Using currentLibraryId: \(currentId)")
            assignLibrary(id: currentId)
            return
        }

        // Priority 2: Use first open library if any exist (restored on app launch)
        if let first = libraryManager.openLibraries.first {
            libraryWindowLogger.info("Using first library: \(first.displayName)")
            assignLibrary(id: first.id)
            return
        }

        // Priority 3: No library - show welcome screen
        libraryWindowLogger.info("No library available - showing welcome screen")
    }

    func assignLibrary(id: UUID) {
        windowState.libraryId = id
        persistedLibraryId = id.uuidString
        libraryWindowLogger.info("Assigned library: \(id)")
    }

    func createNewLibrary() {
        let library = libraryManager.createNewLibrary()
        assignLibrary(id: library.id)
        libraryWindowLogger.info("Created and assigned new library: \(library.displayName)")
    }

    // MARK: - Actions

    func handleFileImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            let library = libraryManager.openLibrary(at: url)
            assignLibrary(id: library.id)
            libraryWindowLogger.info("Opened library: \(library.displayName)")
        case .failure(let error):
            libraryWindowLogger.error("Failed to open library: \(error.localizedDescription)")
        }
    }

    func handleNewWindow() {
        libraryManager.currentLibraryId = windowState.libraryId
        openWindow(id: "main")
    }

    /// Resolve the library a WindowSeed refers to: prefer the already-open
    /// library by id (the Duplicate Window case — same process, same library),
    /// falling back to re-opening it from its on-disk path if a restored seed
    /// outlived the source library being closed.
    func resolveSeedLibrary(_ seed: WindowSeed) -> UUID? {
        if let id = UUID(uuidString: seed.libraryId),
           libraryManager.getLibrary(id: id) != nil {
            return id
        }
        if let path = seed.libraryPath {
            return libraryManager.openLibrary(at: URL(fileURLWithPath: path), makeCurrent: false).id
        }
        return nil
    }

    /// Duplicate Window (#2262): clone THIS window's library + selection + lens
    /// into a brand-new window. Reads the live #2273 scene-storage state and
    /// hands it to the value-seeded `WindowGroup(for: WindowSeed.self)` via
    /// `openWindow(value:)`. `nil` when no library is open (menu item disabled).
    var duplicateWindowAction: FocusedLibraryAction? {
        guard windowState.library != nil else { return nil }
        return FocusedLibraryAction(isEnabled: true, run: { handleDuplicateWindow() })
    }

    func handleDuplicateWindow() {
        guard let library = windowState.library else { return }
        let seed = WindowSeed(
            libraryId: library.id.uuidString,
            libraryPath: libraryManager.isTemporaryLibrary(library.url) ? nil : library.url.path,
            selectedItemId: sceneSelectedItemId,
            viewModeType: sceneViewModeType,
            viewModeItemId: sceneViewModeItemId
        )
        openWindow(value: seed)
        libraryWindowLogger.info("Duplicated window for library: \(library.id)")
    }

    func handleNewLibrary() {
        // Panel configuration and the on-disk naming decision are shared with
        // the app-scoped File-menu fallback (#4530) so the two paths cannot
        // drift; see NewLibraryPanel.
        let savePanel = NewLibraryPanel.makeSavePanel()

        if savePanel.runModal() == .OK, let url = savePanel.url {
            let finalURL = NewLibraryPanel.resolvedLibraryURL(for: url)

            // Create unsaved library, immediately save to chosen location, then
            // switch THIS window to it in-place — no new window (#4062). New
            // Library… is distinct from New Window (which reuses the current
            // library): it creates a fresh library and selects it in the
            // current window's sidebar, mirroring Finder's "New Folder" flow.
            // Keeping it in-window also preserves the current window's
            // connection/store, so we don't re-trigger #3362's new-window
            // re-auth path.
            let newLibrary = libraryManager.createNewLibrary()
            do {
                try libraryManager.saveLibrary(newLibrary.id, to: finalURL)
                assignLibrary(id: newLibrary.id)
                libraryWindowLogger.info("Created and saved new library in-place: \(finalURL.lastPathComponent)")
            } catch {
                // #4530: a failed create used to be log-only, so the user
                // pressed Create, got no library and no reason. Rule zero —
                // fail loudly.
                libraryWindowLogger.error("Failed to create new library: \(error.localizedDescription)")
                NewLibraryPanel.presentCreateFailure(error, at: finalURL)
            }
        }
    }

    func handleSaveLibrary() {
        guard let library = windowState.library else { return }

        let savePanel = NSSavePanel()
        savePanel.allowedContentTypes = [.package]
        savePanel.canCreateDirectories = true
        savePanel.nameFieldStringValue = library.displayName + ".fichero"
        savePanel.message = "Choose a location to save your library"

        savePanel.begin { response in
            guard response == .OK, let url = savePanel.url else { return }

            // NFC-normalize the package name before saving (#3076) so a name
            // like "Chocó" is never written as an NFD-variant path.
            let finalURL = url.nfcNormalizedLastComponent
            do {
                try libraryManager.saveLibrary(windowState.libraryId, to: finalURL)
                libraryWindowLogger.info("Saved library to: \(finalURL.path)")
            } catch {
                libraryWindowLogger.error("Failed to save: \(error.localizedDescription)")
            }
        }
    }

    var closeLibraryAction: FocusedLibraryAction? {
        guard let library = windowState.library,
              library.id != LibraryManager.globalLibraryId else {
            return nil
        }

        return FocusedLibraryAction(isEnabled: true, run: {
            closeLibraryFromCurrentWindow(library)
        })
    }

    func closeLibraryFromCurrentWindow(_ library: LibraryManager.LibraryReference) {
        let wasCurrent = windowState.libraryId == library.id
        libraryManager.closeAndUnregisterLibrary(library.id)
        if wasCurrent {
            windowState.libraryId = LibraryManager.globalLibraryId
            persistedLibraryId = LibraryManager.globalLibraryId.uuidString
        }
    }

    func syncHostWindowMetadata() {
        hostWindow?.representedURL = windowState.library?.url
    }
}

#endif
