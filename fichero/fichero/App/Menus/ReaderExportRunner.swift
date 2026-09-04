import Foundation
import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ReaderExport")

/// Writes the reader's documents out as `.md` or `.docx`.
///
/// Markdown is written by the app from the text the reader is showing — the
/// SAME bytes `ReaderMarkdownDrag` promises when you drag the proxy icon, so
/// the two affordances cannot disagree about what "the text you are reading"
/// means, and neither needs the engine to reach the user's disk.
///
/// Word goes to the engine's existing `/api/export/word` service (the routes
/// the export lane verified 2026-09-03) through the generated, tokened client
/// — there is no second .docx writer in the app.
enum ReaderExportRunner {
    static let markdownType = UTType("net.daringfireball.markdown") ?? .plainText
    static var wordType: UTType? { UTType(filenameExtension: "docx") }

    // MARK: Markdown

    @MainActor
    static func exportMarkdown(targets: ReaderExportTargets) async {
        #if !os(macOS)
        logger.info("Reader export is macOS-only; a document picker is needed on iOS.")
        #else
        let items = targets.markdownItems
        guard !items.isEmpty else { return }

        do {
            if items.count == 1 {
                let item = items[0]
                let name = ReaderMarkdownDrag.filename(forDocumentNamed: item.name)
                guard let url = await ExportPresentation.savePanel(
                    suggestedName: name, contentType: markdownType
                ) else { return }
                try Data(item.text.utf8).write(to: url, options: .atomic)
                logger.info("Exported reader Markdown to \(url.path)")
                ExportPresentation.revealInFinder(url)
            } else {
                guard let folder = await ExportPresentation.directoryPanel(
                    message: "Choose a folder for the exported Markdown files"
                ) else { return }
                var written: [URL] = []
                for item in items {
                    let url = folder.appendingPathComponent(
                        ReaderMarkdownDrag.filename(forDocumentNamed: item.name)
                    )
                    try Data(item.text.utf8).write(to: url, options: .atomic)
                    written.append(url)
                }
                logger.info("Exported \(written.count) reader Markdown file(s) to \(folder.path)")
                ExportPresentation.revealInFinder(written.first ?? folder)
            }
        } catch {
            logger.error("Failed to export Markdown: \(error.localizedDescription)")
            ExportPresentation.showError(error, title: "Markdown Export Failed")
        }
        #endif
    }

    // MARK: Word

    @MainActor
    static func exportWord(
        targets: ReaderExportTargets,
        library: LibraryManager.LibraryReference
    ) async {
        #if !os(macOS)
        logger.info("Reader export is macOS-only; a document picker is needed on iOS.")
        #else
        guard !targets.isEmpty else { return }

        do {
            if targets.items.count == 1 {
                let item = targets.items[0]
                let name = filename(forDocumentNamed: item.name, extension: "docx")
                guard let url = await ExportPresentation.savePanel(
                    suggestedName: name, contentType: wordType
                ) else { return }
                // `overwrite: true` — the save panel already asked; a 409 from
                // the engine here would be the app asking the same question
                // twice and losing the answer.
                let result = try await library.documentService.exportWord(
                    outputPath: url.path, targetId: item.id, overwrite: true
                )
                logger.info("Exported \(result.documentCount) document(s) to \(result.outputPath)")
                ExportPresentation.revealInFinder(URL(fileURLWithPath: result.outputPath))
            } else {
                guard let folder = await ExportPresentation.directoryPanel(
                    message: "Choose a folder for the exported Word files"
                ) else { return }
                var written: [URL] = []
                for item in targets.items {
                    let url = folder.appendingPathComponent(
                        filename(forDocumentNamed: item.name, extension: "docx")
                    )
                    let result = try await library.documentService.exportWord(
                        outputPath: url.path, targetId: item.id, overwrite: true
                    )
                    written.append(URL(fileURLWithPath: result.outputPath))
                }
                logger.info("Exported \(written.count) Word file(s) to \(folder.path)")
                ExportPresentation.revealInFinder(written.first ?? folder)
            }
        } catch {
            logger.error("Failed to export Word: \(error.localizedDescription)")
            ExportPresentation.showError(error, title: "Word Export Failed")
        }
        #endif
    }

    /// Same sanitising rule `ReaderMarkdownDrag.filename` applies, for any
    /// extension: "1933/34" must not promise a file inside a directory that
    /// does not exist.
    static func filename(forDocumentNamed name: String, extension ext: String) -> String {
        let stem = ReaderMarkdownDrag.filename(forDocumentNamed: name)
            .replacingOccurrences(of: ".md", with: "", options: [.anchored, .backwards])
        return "\(stem).\(ext)"
    }
}
