#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "FileMenuCommands")

struct FileMenuCommands: View {
    @Environment(LibraryManager.self) var libraryManager
    @FocusedValue(\.openLibraryAction) private var openLibraryAction
    @FocusedValue(\.newLibraryAction) private var newLibraryAction
    @FocusedValue(\.newWindowAction) private var newWindowAction
    @FocusedValue(\.duplicateWindowAction) private var duplicateWindowAction
    @FocusedValue(\.saveLibraryAction) private var saveLibraryAction
    @FocusedValue(\.closeLibraryAction) private var closeLibraryAction
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows
    @Environment(\.openWindow) private var openWindow
    @State private var registry = KnownLibraryRegistryStore.shared

    var currentLibrary: LibraryManager.LibraryReference? {
        guard let libraryId = libraryManager.currentLibraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    var body: some View {
        Group {
            // #4530: never disabled-when-the-focused-action-is-nil. These commands
            // used to be gated on a `focusedSceneValue` that only a key
            // LibraryWindow supplies, so they went dead whenever no window was
            // key — with every window closed, or merely while Settings /
            // Activity / About was frontmost. "New Library doesn't work" and
            // "no way to get a window back" were the same defect seen twice.
            // A window-scoped action is now a PREFERENCE (it creates in-place,
            // #4062), never a precondition; without one, the app-scoped
            // fallback does the same work and opens a window to show it.
            Button("New Library...") {
                if let newLibraryAction {
                    newLibraryAction.run()
                } else {
                    createLibraryAtAppScope()
                }
            }
            .keyboardShortcut("n", modifiers: [.command])

            Button("Open...") {
                if let openLibraryAction {
                    openLibraryAction.run()
                } else {
                    openLibraryAtAppScope()
                }
            }
            .keyboardShortcut("o", modifiers: [.command])

            // Local recents come from `LibraryRecents` — the registry the menu
            // used before is the authoritative OPEN set, so Close Library
            // erased a library from "recent" at exactly the moment Open Recent
            // exists for (Daniel, 2026-08-25: made a library, closed it, gone).
            // Remote hosts keep the registry list: their recents genuinely are
            // the host's known libraries (#3151).
            Menu("Open Recent") {
                if BackendHost.appDefault.isLocal {
                    if LibraryRecents.shared.entries.isEmpty {
                        Text("No Recent Libraries")
                    } else {
                        ForEach(LibraryRecents.shared.entries) { entry in
                            Button(entry.displayName) {
                                openRecentEntry(entry)
                            }
                        }

                        Divider()

                        Button("Clear Menu") {
                            LibraryRecents.shared.clearAll()
                        }
                    }
                } else if let fetchError = registry.fetchError,
                          registry.libraries.isEmpty {
                    Text("Couldn’t load recent libraries")
                    Text(fetchError)
                        .foregroundStyle(.secondary)
                } else if registry.libraries.isEmpty {
                    Text("No Recent Libraries")
                } else {
                    ForEach(registry.libraries) { library in
                        Button(library.displayName) {
                            openRecentLibrary(library)
                        }
                    }

                    Divider()

                    Button("Clear Menu") {
                        Task {
                            await registry.clearAll()
                        }
                    }
                }
            }
            .disabled(
                BackendHost.appDefault.isLocal
                    ? LibraryRecents.shared.entries.isEmpty
                    : registry.libraries.isEmpty && registry.fetchError == nil
            )

            Button("Close Library") {
                closeLibraryAction?.run()
            }
            .keyboardShortcut("w", modifiers: [.command, .control])
            .disabled(closeLibraryAction == nil)

            Divider()

            // Window-opening region, folded into one Group: the outer Group is
            // at @ViewBuilder's 10-entry arity limit, so new entries must join
            // an existing slot rather than add one.
            Group {
                // #4530: with no window key there is no focused action, and
                // this was the command that was supposed to get you a window
                // back — disabled exactly when it was needed. It now falls
                // back to opening the primary scene directly; `openWindow` is
                // app-scoped and does not need a key window. Still gated on
                // `supportsMultipleWindows`, which is a real platform fact.
                Button("New Window") {
                    if let newWindowAction {
                        newWindowAction.run()
                    } else {
                        openWindow(id: "main")
                    }
                }
                .keyboardShortcut("t", modifiers: [.command])
                .disabled(!supportsMultipleWindows)

                // Duplicate Window (#2262): clones the current window's library +
                // selection + active lens into a new window via openWindow(value:).
                // Gated on supportsMultipleWindows so it disables where multiple
                // windows aren't available.
                Button("Duplicate Window") {
                    duplicateWindowAction?.run()
                }
                .keyboardShortcut("t", modifiers: [.command, .shift])
                .disabled(duplicateWindowAction == nil || !supportsMultipleWindows)

                // Open the focused sidebar's selected row (#2496): keyboard/menu
                // parity with double-click, the trailing affordance, and the row
                // context menu. Disabled (not hidden) without a sidebar selection.
                // #116: macOS ONLY, and this gate is the fix. The two actions
                // behind these buttons have bodies that are entirely
                // `#if os(macOS)` (WindowOpener does not exist on iOS), so on
                // iPad these rendered as ENABLED File-menu commands with real
                // key equivalents that did nothing at all — the same empty-body
                // shape as the Copy Name button in #4505, one indirection out.
                // Absent beats a command that cannot work (#4421).
                #if os(macOS)
                FocusedOpenInNewTabButton()
                FocusedOpenInNewWindowButton()
                #endif
            }

            Divider()

            Button("Save Library As...") {
                saveLibraryAction?.run()
            }
            .keyboardShortcut("s", modifiers: [.command, .shift])
            .disabled(saveLibraryAction == nil)

            // Export section (#2088)
            Menu {
                Button {
                    Task { await exportBibtex() }
                } label: {
                    Label("BibTeX (.bib)...", systemImage: "text.quote")
                }
                .disabled(currentLibrary == nil)

                Button {
                    Task { await exportEleventySite() }
                } label: {
                    Label("Markdown Static Site...", systemImage: "globe")
                }
                .disabled(currentLibrary == nil)
            } label: {
                Label("Export", systemImage: "square.and.arrow.up")
            }
            .disabled(currentLibrary == nil)

            // Grant Folder Access… (2026-08-21): linked sources outside every
            // granted root — a Box folder imported in link mode — leave the
            // sandboxed engine with "No source found" and the preview stuck on
            // its thumbnail, and NO existing UI could mint the missing grant:
            // the only prompt covers the library folder itself. The saved
            // bookmark is handed to the RUNNING engine, so previews recover
            // without a relaunch.
            #if os(macOS)
            Button("Grant Folder Access...") {
                FolderAccessManager.shared.requestFolderAccess { granted in
                    logger.info("Manual folder grant: \(granted ? "granted" : "declined")")
                }
            }
            #endif
        }
        .task {
            if registry.libraries.isEmpty {
                await registry.refresh()
            }
        }
    }

    /// Open a LOCAL recents entry, pruning entries whose package is gone.
    private func openRecentEntry(_ entry: LibraryRecents.Entry) {
        let url = URL(fileURLWithPath: entry.path)
        guard FileManager.default.fileExists(atPath: url.path) else {
            LibraryRecents.shared.remove(path: entry.path)
            return
        }
        let opened = libraryManager.openLibrary(at: url)
        libraryManager.currentLibraryId = opened.id
    }

    private func openRecentLibrary(_ library: KnownLibraryMenuEntry) {
        // Remote host (#3151): the path lives on the remote engine, not this
        // Mac's disk, so the `fileExists` gate below would always fail and drop
        // the entry. Open it remotely instead — no local security scope, no gate.
        if !BackendHost.appDefault.isLocal {
            libraryManager.switchToRemoteLibrary(path: library.path, displayName: library.displayName)
            return
        }

        let url = URL(fileURLWithPath: library.path)
        guard FileManager.default.fileExists(atPath: url.path) else {
            Task {
                await registry.remove(path: library.path)
            }
            return
        }

        let opened = libraryManager.openLibrary(at: url)
        libraryManager.currentLibraryId = opened.id
    }

}

// Windowless entry points, in an extension so the struct body stays inside
// the type_body_length budget (#4530). Same file, so they still reach the
// private environment properties above.
private extension FileMenuCommands {

    /// New Library… with NO key window (#4530). Same panel and same on-disk
    /// naming as the in-window path (both go through `NewLibraryPanel`), but
    /// since there is no window to switch in place, it opens one to show the
    /// result — `initializeWindow` picks the library up from `currentLibraryId`,
    /// which `createNewLibrary` has already set.
    ///
    /// A failed save does NOT open a window: a blank window is a worse answer
    /// than the error, and the library reference stays in the open set for the
    /// user to retry via Save Library As.
    private func createLibraryAtAppScope() {
        #if os(macOS)
        let savePanel = NewLibraryPanel.makeSavePanel()
        guard savePanel.runModal() == .OK, let url = savePanel.url else { return }
        let finalURL = NewLibraryPanel.resolvedLibraryURL(for: url)
        guard NewLibraryPanel.confirmSyncedLocationIfNeeded(at: finalURL) else {
            createLibraryAtAppScope()  // reopen the panel — the user chose to relocate
            return
        }

        let newLibrary = libraryManager.createNewLibrary()
        do {
            try libraryManager.saveLibrary(newLibrary.id, to: finalURL)
            libraryManager.currentLibraryId = newLibrary.id
            NewLibraryPanel.noteChosenDirectory(forLibraryAt: finalURL)
            openWindow(id: "main")
            logger.info("Created new library at app scope: \(finalURL.lastPathComponent)")
        } catch {
            logger.error("Failed to create new library at app scope: \(error.localizedDescription)")
            NewLibraryPanel.presentCreateFailure(error, at: finalURL)
        }
        #endif
    }

    /// Open… with NO key window (#4530). The in-window path uses
    /// `.fileImporter`, which needs a view to attach to; with no window there
    /// is none, so this runs the AppKit open panel directly and then opens a
    /// window on the library it picked.
    private func openLibraryAtAppScope() {
        #if os(macOS)
        let panel = NSOpenPanel()
        if let libraryType = UTType.ficheroLibrary {
            panel.allowedContentTypes = [libraryType]
        }
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Open"
        panel.message = "Choose a Fichero library to open."

        guard panel.runModal() == .OK, let url = panel.url else { return }
        let library = libraryManager.openLibrary(at: url)
        libraryManager.currentLibraryId = library.id
        openWindow(id: "main")
        logger.info("Opened library at app scope: \(library.displayName)")
        #endif
    }
}

enum ExportError: Error, LocalizedError {
    case unexpectedResponse
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from the export service."
        case .serverError(let message):
            return message
        }
    }
}
