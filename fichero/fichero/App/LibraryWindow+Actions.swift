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

    /// ⌘N: a new WINDOW on this window's library, never a tab (#5286). A plain
    /// `openWindow` let the system's "Prefer tabs" setting decide which one you got.
    func handleNewWindow() {
        openOnThisLibrary(asTab: false)
    }

    /// ⌘T: a new TAB in this window's tab group, whatever the system setting
    /// and whatever `sidebarOpenPrefersTab` says (#5286: ⌘T is always a tab).
    func handleNewTab() {
        openOnThisLibrary(asTab: true)
    }

    private func openOnThisLibrary(asTab: Bool) {
        libraryManager.currentLibraryId = windowState.libraryId
        #if os(macOS)
        WindowOpener.open(libraryId: windowState.libraryId, asTab: asTab, using: openWindow)
        #else
        openWindow(id: "main")
        #endif
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

    /// File › Set Up New Project… (#5482, ruled 2026-10-05): setup opens in THIS window at Where
    /// it lives, which makes the project (Inside Fichero, or a folder the person chooses); when
    /// setup ends the window shows it in place, with `assignLibrary` (#4062, no new window).
    func handleNewLibrary() {
        showingNewProjectSetUp = true
    }
}

/// Set Up New Project…'s sheet on a window (#5482): setup from Your project, which makes the
/// project; `onProjectReady` shows it in this window when setup ends, in place (#4062). Asked
/// with no window to show it (#4530), the first window to see the request takes it.
struct NewProjectSetUpSheet: ViewModifier {
    @Binding var isPresented: Bool
    let onProjectReady: (UUID) -> Void
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(AppState.self) private var appState

    func body(content: Content) -> some View {
        content
            .sheet(isPresented: $isPresented) {
                FirstRunWindow(mode: .newProject, onProjectReady: onProjectReady)
                    .environment(appState)
            }
            .onChange(of: libraryManager.newProjectSetUpRequested, initial: true) { _, requested in
                guard requested else { return }
                libraryManager.newProjectSetUpRequested = false
                isPresented = true
            }
    }
}

extension LibraryWindow {

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
