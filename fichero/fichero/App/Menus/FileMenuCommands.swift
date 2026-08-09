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
    @Environment(LibraryManager.self) private var libraryManager
    @FocusedValue(\.openLibraryAction) private var openLibraryAction
    @FocusedValue(\.newLibraryAction) private var newLibraryAction
    @FocusedValue(\.newWindowAction) private var newWindowAction
    @FocusedValue(\.duplicateWindowAction) private var duplicateWindowAction
    @FocusedValue(\.saveLibraryAction) private var saveLibraryAction
    @FocusedValue(\.closeLibraryAction) private var closeLibraryAction
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows
    @Environment(\.openWindow) private var openWindow
    @State private var registry = KnownLibraryRegistryStore.shared

    private var currentLibrary: LibraryManager.LibraryReference? {
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

            Menu("Open Recent") {
                if let fetchError = registry.fetchError,
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
            .disabled(registry.libraries.isEmpty && registry.fetchError == nil)

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
        }
        .task {
            if registry.libraries.isEmpty {
                await registry.refresh()
            }
        }
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

    private func exportBibtex() async {
        #if !os(macOS)
        logger.info("BibTeX export is macOS-only; document picker needed on iOS.")
        #else
        guard let library = currentLibrary else { return }

        do {
            let documentIds = try await fetchAllDocumentIDs(using: library)
            let bibData = try await exportBibtexData(using: library, documentIds: documentIds)

            guard let saveURL = await presentBibtexSavePanel() else { return }

            try bibData.write(to: saveURL, options: .atomic)
            logger.info("Exported BibTeX to \(saveURL.path)")
            revealInFinder(saveURL)
        } catch {
            logger.error("Failed to export BibTeX: \(error.localizedDescription)")
            presentExportError(error, title: "BibTeX Export Failed")
        }
        #endif
    }

    /// Export the current library as a local markdown/11ty static site (#3055).
    /// Routes through the DocumentService wrapper (tokened generated
    /// client) after the user picks an output folder; GitHub publish/reimport is
    /// a later layer on top of this export.
    private func exportEleventySite() async {
        #if !os(macOS)
            logger.info("Markdown-site export is macOS-only; a folder picker is needed on iOS.")
        #else
        guard let library = currentLibrary else { return }
        guard let outputURL = await presentDirectoryPanel() else { return }

        do {
            let result = try await library.documentService.exportEleventySite(
                outputPath: outputURL.path,
                siteTitle: library.displayName
            )
            logger.info(
                "Exported \(result.documentCount) document(s) to markdown static site at \(result.outputPath)"
            )
            revealInFinder(URL(fileURLWithPath: result.outputPath))
        } catch {
            logger.error("Failed to export markdown static site: \(error.localizedDescription)")
            presentExportError(error, title: "Markdown Static Site Export Failed")
        }
        #endif
    }

    #if os(macOS)
    private func presentDirectoryPanel() async -> URL? {
        await withCheckedContinuation { continuation in
            let panel = NSOpenPanel()
            panel.canChooseDirectories = true
            panel.canChooseFiles = false
            panel.canCreateDirectories = true
            panel.prompt = "Export Here"
            panel.message = "Choose a folder for the exported markdown static site"
            panel.begin { result in
                continuation.resume(returning: result == .OK ? panel.url : nil)
            }
        }
    }
    #endif

    private func fetchAllDocumentIDs(using library: LibraryManager.LibraryReference) async throws -> [String] {
        let response = try await library.ficheroClient.api.listDocumentsApiDocumentsGet(.init(query: .init()))
        switch response {
        case .ok(let success):
            return try success.body.json.items.compactMap(\.id)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ExportError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw ExportError.unexpectedResponse
        }
    }

    private func exportBibtexData(
        using library: LibraryManager.LibraryReference,
        documentIds: [String]
    ) async throws -> Data {
        // Route through the service wrapper instead of raw ficheroClient.api
        // (observable-data-layer, #3258); it owns the response handling.
        let bib = try await library.entityService.exportBibliographyBib(documentIds: documentIds)
        return Data(bib.utf8)
    }

    #if os(macOS)
    private func presentBibtexSavePanel() async -> URL? {
        await withCheckedContinuation { continuation in
            let savePanel = NSSavePanel()
            savePanel.nameFieldStringValue = "bibliography.bib"
            if let bibType = UTType(filenameExtension: "bib") {
                savePanel.allowedContentTypes = [bibType]
            }
            savePanel.allowsOtherFileTypes = false
            savePanel.canCreateDirectories = true

            savePanel.begin { result in
                continuation.resume(returning: result == .OK ? savePanel.url : nil)
            }
        }
    }

    private func presentExportError(_ error: Error, title: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = error.localizedDescription
        alert.alertStyle = .warning
        alert.runModal()
    }

    /// Reveal the exported file/folder in Finder so a successful export isn't
    /// silent (#3305). macOS-only — the callers live in os(macOS) branches.
    private func revealInFinder(_ url: URL) {
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
    #endif
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

        let newLibrary = libraryManager.createNewLibrary()
        do {
            try libraryManager.saveLibrary(newLibrary.id, to: finalURL)
            libraryManager.currentLibraryId = newLibrary.id
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

private enum ExportError: Error, LocalizedError {
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
