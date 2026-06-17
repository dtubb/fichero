import AppKit
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "FileMenuCommands")

@MainActor
final class KnownLibraryRegistryStore: ObservableObject {
    static let shared = KnownLibraryRegistryStore()

    @Published private(set) var libraries: [KnownLibraryMenuEntry] = []

    private let apiClient = APIClient()

    private init() { }

    func refresh() async {
        do {
            let response: LibraryRegistryMenuResponse = try await apiClient.get("/registry")
            libraries = response.libraries
        } catch {
            libraries = []
        }
    }

    func noteOpenedLibrary(url: URL, displayName: String?) async {
        guard !LibraryManager.shared.isTemporaryLibrary(url) else { return }
        guard url.pathExtension.lowercased() == "fichero" else { return }

        do {
            let _: KnownLibraryMenuEntry = try await apiClient.post(
                "/registry/add",
                query: [
                    "path": url.path,
                    "name": displayName ?? url.lastPathComponent
                ]
            )
            await refresh()
        } catch {
            // Best-effort only: menu recents should never block opening/saving a library.
        }
    }

    func remove(path: String) async {
        let encodedPath = path.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? path
        do {
            try await apiClient.delete("/registry/\(encodedPath)")
            libraries.removeAll { $0.path == path }
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

private struct LibraryRegistryMenuResponse: Decodable {
    let libraries: [KnownLibraryMenuEntry]
    let count: Int
}

struct KnownLibraryMenuEntry: Decodable, Identifiable, Equatable {
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

    enum CodingKeys: String, CodingKey {
        case id
        case path
        case name
        case addedAt = "added_at"
        case lastAccessed = "last_accessed"
    }
}

struct FileMenuCommands: View {
    @EnvironmentObject private var libraryManager: LibraryManager
    @FocusedValue(\.openLibraryAction) private var openLibraryAction
    @FocusedValue(\.newLibraryAction) private var newLibraryAction
    @FocusedValue(\.newWindowAction) private var newWindowAction
    @FocusedValue(\.duplicateWindowAction) private var duplicateWindowAction
    @FocusedValue(\.saveLibraryAction) private var saveLibraryAction
    @FocusedValue(\.closeLibraryAction) private var closeLibraryAction
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows
    @ObservedObject private var registry = KnownLibraryRegistryStore.shared

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
    }

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
