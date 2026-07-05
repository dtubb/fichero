#if canImport(AppKit)
import AppKit
#endif
import Observation
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "FileMenuCommands")

@MainActor
@Observable
final class KnownLibraryRegistryStore {
    static let shared = KnownLibraryRegistryStore()

    private(set) var libraries: [KnownLibraryMenuEntry] = []
    private(set) var fetchError: String?

    private let apiClient = APIClient()
    private var hostChangeObservation: NSObjectProtocol?

    private init() {
        // Rebind on a pairing / Settings host change (#2349) — otherwise the
        // known-library registry menu keeps querying the launch host (localhost)
        // after the app has moved to a remote engine.
        hostChangeObservation = NotificationCenter.default.addObserver(
            forName: EngineConfig.engineHostDidChangeNotification,
            object: nil,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor in
                self?.apiClient.reconfigure(baseURL: EngineConfig.host)
            }
        }
    }

    deinit {
        if let hostChangeObservation {
            NotificationCenter.default.removeObserver(hostChangeObservation)
        }
    }

    func refresh() async {
        do {
            let response = try await apiClient.api.listKnownLibrariesApiRegistryGet(.init())
            switch response {
            case .ok(let okResponse):
                let body = try okResponse.body.json
                libraries = body.libraries.map { lib in
                    KnownLibraryMenuEntry(
                        id: lib.id ?? lib.path,
                        path: lib.path,
                        name: lib.name,
                        addedAt: lib.addedAt,
                        lastAccessed: lib.lastAccessed
                    )
                }
                fetchError = nil
            default:
                fetchError = "Unexpected response from registry"
            }
        } catch {
            fetchError = error.localizedDescription
        }
    }

    func noteOpenedLibrary(url: URL, displayName: String?) async {
        guard !LibraryManager.shared.isTemporaryLibrary(url) else { return }
        guard url.pathExtension.lowercased() == "fichero" else { return }

        do {
            // NFC-normalize path + name (#3076) so the global registry keys this
            // library canonically and never records a second NFD variant.
            // Generated add_known_library op via the shared typed client (#3030).
            let response = try await apiClient.api.addKnownLibraryApiRegistryAddPost(
                query: .init(
                    path: url.path.nfcNormalized,
                    name: (displayName ?? url.lastPathComponent).nfcNormalized
                )
            )
            if case .ok = response {
                await refresh()
            }
        } catch {
            // Best-effort only: menu recents should never block opening/saving a library.
        }
    }

    func remove(path: String) async {
        // Compare/address by NFC (#3076): registry entries from `refresh()` are
        // NFC (backend #3071), so normalize the incoming path or an NFD caller
        // would fail to match and silently leave the entry behind.
        let path = path.nfcNormalized
        do {
            // Generated remove_known_library op (#3030); the runtime percent-encodes
            // the path param, and the backend decodes it back to the raw path.
            let response = try await apiClient.api.removeKnownLibraryApiRegistryLibraryPathDelete(
                path: .init(libraryPath: path)
            )
            if case .ok = response {
                libraries.removeAll { $0.path.nfcNormalized == path }
            } else {
                await refresh()
            }
        } catch {
            await refresh()
        }
    }

    func clearAll() async {
        let paths = libraries.map(\.path)
        for path in paths {
            await remove(path: path)
        }
    }
}

struct KnownLibraryMenuEntry: Identifiable, Equatable {
    let id: String
    let path: String
    let name: String?
    let addedAt: Date?
    let lastAccessed: Date?

    var displayName: String {
        if let trimmedName = name?.trimmingCharacters(in: .whitespacesAndNewlines),
           !trimmedName.isEmpty {
            return trimmedName
        }

        return URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
    }
}

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
                if registry.libraries.isEmpty {
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
            .disabled(registry.libraries.isEmpty)

            Button("Close Database") {
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

            Button("Save Database As...") {
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
                    Label("Static Site (11ty)...", systemImage: "globe")
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
        } catch {
            logger.error("Failed to export BibTeX: \(error.localizedDescription)")
            presentExportError(error)
        }
        #endif
    }

    /// Export the current library as an Eleventy static site (#3055). Routes
    /// through the DocumentServiceGenerated wrapper (tokened generated client),
    /// after the user picks an output folder.
    private func exportEleventySite() async {
        #if !os(macOS)
        logger.info("Static-site export is macOS-only; a folder picker is needed on iOS.")
        #else
        guard let library = currentLibrary else { return }
        guard let outputURL = await presentDirectoryPanel() else { return }

        do {
            let result = try await library.documentServiceGenerated.exportEleventySite(
                outputPath: outputURL.path,
                siteTitle: library.displayName
            )
            logger.info(
                "Exported \(result.documentCount) document(s) to static site at \(result.outputPath)"
            )
        } catch {
            logger.error("Failed to export static site: \(error.localizedDescription)")
            presentExportError(error)
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
            panel.message = "Choose a folder for the generated static site"
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
        let request = Components.Schemas.FicheroApiRoutesBibliographyExportRequest(documentIds: documentIds)
        let response = try await library.ficheroClient.api.exportBibtexApiBibliographyExportBibPost(
            .init(body: .json(request))
        )
        switch response {
        case .ok(let success):
            let body = try success.body.plainText
            return try await Data(collecting: body, upTo: 10 * 1024 * 1024)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ExportError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw ExportError.unexpectedResponse
        }
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

    private func presentExportError(_ error: Error) {
        let alert = NSAlert()
        alert.messageText = "BibTeX Export Failed"
        alert.informativeText = error.localizedDescription
        alert.alertStyle = .warning
        alert.runModal()
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
