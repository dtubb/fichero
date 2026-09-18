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

        // Priority 0a: a WindowSeed (Duplicate Window, #2262) clones an existing
        // window's library + selection + active lens.
        let seededId = seed.flatMap(resolveSeedLibrary)

        // Priority 0b: cross-window "Open in New Tab/Window" hand-off (#1685).
        let pendingId = libraryManager.pendingWindowLibraryIds.first.flatMap { pendingId in
            libraryManager.getLibrary(id: pendingId) != nil ? pendingId : nil
        }

        // Priority 0c: restore the library this scene was showing last time.
        let restoredId = persistedLibraryId
            .flatMap { UUID(uuidString: $0) }
            .flatMap { restoredId in
                libraryManager.getLibrary(id: restoredId) != nil ? restoredId : nil
            }

        // Priority 1: currentLibraryId (set by handleOpenURL / restoreSavedLibraries).
        let currentId = libraryManager.currentLibraryId.flatMap { currentId in
            libraryManager.getLibrary(id: currentId) != nil ? currentId : nil
        }

        // Priority 2: first open library, if any exist (restored on app launch).
        let firstOpenId = libraryManager.openLibraries.first?.id

        // Priority 3: Global — the pure function's final fallback. Always
        // resolves: `LibraryManager.shared.init` loads Global synchronously,
        // before any window can read it (#4783 — replaces `noLibraryView`).
        let resolvedId = Self.resolvedLibraryID(
            seed: seededId,
            pendingWindow: pendingId,
            restored: restoredId,
            current: currentId,
            firstOpen: firstOpenId,
            global: LibraryManager.globalLibraryId
        )

        // Side effects belong to whichever source actually won — evaluated in
        // the same priority order `resolvedLibraryID` uses. Write the #2273
        // scene-storage keys BEFORE the library mounts so ContentView restores
        // into the cloned state.
        if let seededId, resolvedId == seededId, let seed {
            sceneSelectedItemId = seed.selectedItemId
            sceneViewModeType = seed.viewModeType ?? "library"
            sceneViewModeItemId = seed.viewModeItemId
            libraryWindowLogger.info("Seeded duplicated window from library: \(resolvedId)")
        } else if let pendingId, resolvedId == pendingId {
            libraryWindowLogger.info("Consuming pendingWindowLibraryId: \(pendingId)")
            libraryManager.pendingWindowLibraryIds.removeFirst()
            // Claim the "focus this doc" intent for THIS fresh window only, so a
            // background window sharing the library's documentStore can't
            // consume it on a revision tick and open it in the wrong window
            // (#1685). Moved off the shared singleton the moment we know which
            // window is the newly opened one.
            windowState.pendingOpenDocumentId = libraryManager.pendingOpenDocumentId
            libraryManager.pendingOpenDocumentId = nil
        } else if let restoredId, resolvedId == restoredId {
            libraryWindowLogger.info("Restoring persisted libraryId: \(resolvedId)")
        } else if let currentId, resolvedId == currentId {
            libraryWindowLogger.info("Using currentLibraryId: \(resolvedId)")
        } else if let firstOpenId, resolvedId == firstOpenId {
            libraryWindowLogger.info("Using first library: \(resolvedId)")
        } else {
            libraryWindowLogger.info("No open/restorable library — showing Global (#4783)")
        }

        assignLibrary(id: resolvedId)
    }

    /// The single source of truth for which library THIS window shows.
    /// Resolution never fails: `global` is the final fallback and is always
    /// real — `LibraryManager.shared.init` loads it synchronously before any
    /// window can read it. Every other candidate has ALREADY been validated
    /// to exist by the caller (`nil` otherwise); this only picks between them
    /// in priority order. This is what makes the "Create a new library or
    /// open an existing one" prompt (`noLibraryView`, #4783) provably
    /// unreachable rather than merely un-rendered today.
    static func resolvedLibraryID(
        seed: UUID?,
        pendingWindow: UUID?,
        restored: UUID?,
        current: UUID?,
        firstOpen: UUID?,
        global: UUID
    ) -> UUID {
        seed ?? pendingWindow ?? restored ?? current ?? firstOpen ?? global
    }

    func assignLibrary(id: UUID) {
        windowState.libraryId = id
        persistedLibraryId = id.uuidString
        libraryWindowLogger.info("Assigned library: \(id)")
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
            guard NewLibraryPanel.confirmSyncedLocationIfNeeded(at: finalURL) else {
                handleNewLibrary()  // reopen the panel — the user chose to relocate
                return
            }

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
                NewLibraryPanel.noteChosenDirectory(forLibraryAt: finalURL)
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
