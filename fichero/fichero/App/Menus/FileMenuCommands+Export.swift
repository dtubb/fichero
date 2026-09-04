import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "FileMenuCommands")

// MARK: - Export actions (split from FileMenuCommands for file_length).

extension FileMenuCommands {
    func exportBibtex() async {
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
    func exportEleventySite() async {
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
    func presentDirectoryPanel() async -> URL? {
        await ExportPresentation.directoryPanel(
            message: "Choose a folder for the exported markdown static site"
        )
    }
    #endif

    func fetchAllDocumentIDs(using library: LibraryManager.LibraryReference) async throws -> [String] {
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

    func exportBibtexData(
        using library: LibraryManager.LibraryReference,
        documentIds: [String]
    ) async throws -> Data {
        // Route through the service wrapper instead of raw ficheroClient.api
        // (observable-data-layer, #3258); it owns the response handling.
        let bib = try await library.entityService.exportBibliographyBib(documentIds: documentIds)
        return Data(bib.utf8)
    }

    #if os(macOS)
    func presentBibtexSavePanel() async -> URL? {
        await ExportPresentation.savePanel(
            suggestedName: "bibliography.bib",
            contentType: UTType(filenameExtension: "bib")
        )
    }
    #endif

    #if os(macOS)
    func presentExportError(_ error: Error, title: String) {
        ExportPresentation.showError(error, title: title)
    }
    #endif

    #if os(macOS)
    /// Reveal the exported file/folder in Finder so a successful export isn't
    /// silent (#3305). macOS-only — the callers live in os(macOS) branches.
    func revealInFinder(_ url: URL) {
        ExportPresentation.revealInFinder(url)
    }
    #endif
}
