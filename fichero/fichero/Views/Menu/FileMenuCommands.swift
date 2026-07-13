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
    @State private var registry = KnownLibraryRegistryStore.shared

    private var currentLibrary: LibraryManager.LibraryReference? {
        guard let libraryId = libraryManager.currentLibraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    var body: some View {
        Group {
            Button("New Library...") {
                newLibraryAction?.run()
            }
            .keyboardShortcut("n", modifiers: [.command])
            .disabled(newLibraryAction == nil)

            Button("Open...") {
                openLibraryAction?.run()
            }
            .keyboardShortcut("o", modifiers: [.command])
            .disabled(openLibraryAction == nil)

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

            Button("New Window") {
                newWindowAction?.run()
            }
            .keyboardShortcut("t", modifiers: [.command])
            .disabled(newWindowAction == nil)

            // Duplicate Window (#2262): clones the current window's library +
            // selection + active lens into a new window via openWindow(value:).
            // Gated on supportsMultipleWindows so it disables where multiple
            // windows aren't available.
            Button("Duplicate Window") {
                duplicateWindowAction?.run()
            }
            .keyboardShortcut("t", modifiers: [.command, .shift])
            .disabled(duplicateWindowAction == nil || !supportsMultipleWindows)

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
    /// Routes through the DocumentServiceGenerated wrapper (tokened generated
    /// client) after the user picks an output folder; GitHub publish/reimport is
    /// a later layer on top of this export.
    private func exportEleventySite() async {
        #if !os(macOS)
            logger.info("Markdown-site export is macOS-only; a folder picker is needed on iOS.")
        #else
        guard let library = currentLibrary else { return }
        guard let outputURL = await presentDirectoryPanel() else { return }

        do {
            let result = try await library.documentServiceGenerated.exportEleventySite(
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
