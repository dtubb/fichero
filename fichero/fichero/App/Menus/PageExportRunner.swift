import Foundation
import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "PageExport")

/// Writes ONE page out as an interchange format — PAGE XML, ALTO or TEI.
///
/// Distinct from `ReaderExportRunner`, which exports what you are READING as
/// Markdown or Word. This exports what the page IS: its segments, their
/// shapes, their language, script and direction, and its reading order, in a
/// format another scholarly tool can open (`source.format.everywhere`).
///
/// **The loss report is not optional decoration.** `source.format.loss-report`
/// says every export states what it could not carry, and a report the person
/// never sees is the swallow shape in a new costume — so the summary is shown
/// after the write, and the losses are SELECTABLE so they can be copied into
/// a note rather than read once and dismissed.
enum PageExportRunner {
    /// The formats a page can be written as, in the order a person meets them.
    /// PAGE XML first: it is what eScriptorium and Transkribus read.
    enum Format: String, CaseIterable {
        case pagexml, alto, tei

        var menuTitle: String {
            switch self {
            case .pagexml: return "PAGE XML"
            case .alto: return "ALTO"
            case .tei: return "TEI"
            }
        }

        /// The suffix, not just an extension: `.page.xml` and `.alto.xml` are
        /// the conventions these communities use, and a bare `.xml` tells the
        /// next tool nothing about which of the three it is holding.
        var suffix: String {
            switch self {
            case .pagexml: return "page.xml"
            case .alto: return "alto.xml"
            case .tei: return "tei.xml"
            }
        }
    }

    // MARK: - The part with no UI in it

    /// Everything here is pure, so it can be tested without an engine, a
    /// window or a build destination.
    enum Text {
        /// `1933 Diary` + `.page.xml`, through the same sanitising rule every
        /// other export uses — a document named "1933/34" must not promise a
        /// file inside a directory that does not exist.
        static func filename(forDocumentNamed name: String, format: Format) -> String {
            let stem = ReaderMarkdownDrag.filename(forDocumentNamed: name)
                .replacingOccurrences(of: ".md", with: "", options: [.anchored, .backwards])
            return "\(stem).\(format.suffix)"
        }

        /// What the export actually did, in one line. It names the pass, the
        /// order and the reading kind because "export this page" is ambiguous
        /// the moment a page has two passes — the engine chose, and the person
        /// is told which.
        static func summary(format: Format, passName: String?, passBasis: String?,
                            orderName: String?, readingKind: String?, segmentCount: Int) -> String {
            summary(formatTitle: format.menuTitle, stated: PageExportChoice.Stated(
                passName: passName, passBasis: passBasis, orderName: orderName,
                readingKind: readingKind, segmentCount: segmentCount
            ))
        }

        /// The same, for a format named by the engine (Inspector › Making's per-pass Export, #5162).
        static func summary(formatTitle: String, stated: PageExportChoice.Stated) -> String {
            let passName = stated.passName, passBasis = stated.passBasis
            let orderName = stated.orderName, readingKind = stated.readingKind, segmentCount = stated.segmentCount
            var parts = ["Exported as \(formatTitle)"]
            if let passName, !passName.isEmpty {
                parts.append(passBasis.map { "pass \(passName) (\($0))" } ?? "pass \(passName)")
            }
            if let orderName, !orderName.isEmpty { parts.append("order \(orderName)") }
            if let readingKind, !readingKind.isEmpty { parts.append("reading \(readingKind)") }
            parts.append("\(segmentCount) segment\(segmentCount == 1 ? "" : "s")")
            return parts.joined(separator: ", ")
        }

        /// The losses, or the sentence that says there were none.
        ///
        /// "Nothing was lost" is said OUT LOUD rather than by showing an empty
        /// list, because silence reads as "no report" and this is a report.
        static func losses(_ items: [(what: String, why: String, count: Int)]) -> String {
            guard !items.isEmpty else { return "Nothing was lost: this format carried everything on the page." }
            let lines = items.map { item -> String in
                let times = item.count > 1 ? " ×\(item.count)" : ""
                return "• \(item.what)\(times) — \(item.why)"
            }
            return "Not carried:\n" + lines.joined(separator: "\n")
        }
    }

    // MARK: - The export

    @MainActor
    static func exportPage(
        documentId: String,
        documentName: String,
        format: Format,
        library: LibraryManager.LibraryReference
    ) async {
        #if !os(macOS)
        logger.info("Page export is macOS-only; a document picker is needed on iOS.")
        #else
        do {
            let suggested = Text.filename(forDocumentNamed: documentName, format: format)
            guard let url = await ExportPresentation.savePanel(
                suggestedName: suggested, contentType: UTType.xml
            ) else { return }

            let result = try await library.documentService.exportPage(
                documentId: documentId, format: format.rawValue
            )
            try Data(result.content.utf8).write(to: url, options: .atomic)
            logger.info("Exported page \(documentId) as \(format.rawValue) to \(url.path)")

            let choices = result.choices
            let summary = Text.summary(
                format: format,
                passName: choices.passName,
                passBasis: choices.passBasis,
                orderName: choices.orderName,
                readingKind: choices.readingKind,
                segmentCount: Int(choices.segmentCount)
            )
            let losses = Text.losses(result.losses.map {
                (what: $0.what, why: $0.why, count: Int($0.count))
            })
            showReport(summary: summary, losses: losses, url: url)
        } catch {
            logger.error("Failed to export page: \(error.localizedDescription)")
            ExportPresentation.showError(error, title: "Page Export Failed")
        }
        #endif
    }

    /// One PASS in a format the engine writes (Inspector › Making, #5162): the export first (a read),
    /// then the save panel under the engine's own name, then the same report.
    @MainActor
    static func exportPass(
        documentId: String, passId: String, format: PageExportChoice.Format, library: LibraryManager.LibraryReference
    ) async {
        #if !os(macOS)
        logger.info("Page export is macOS-only; a document picker is needed on iOS.")
        #else
        do {
            let result = try await library.documentService.exportPage(
                documentId: documentId, format: format.name, passId: passId
            )
            let suggested = PageExportChoice.filename(engine: result.filename, format: format)
            guard let url = await ExportPresentation.savePanel(suggestedName: suggested, contentType: nil) else { return }
            try Data(result.content.utf8).write(to: url, options: .atomic)
            let choices = result.choices
            showReport(
                summary: Text.summary(formatTitle: format.title, stated: PageExportChoice.Stated(
                    passName: choices.passName, passBasis: choices.passBasis, orderName: choices.orderName,
                    readingKind: choices.readingKind, segmentCount: Int(choices.segmentCount)
                )),
                losses: Text.losses(result.losses.map { (what: $0.what, why: $0.why, count: Int($0.count)) }),
                url: url
            )
        } catch {
            logger.error("Failed to export pass: \(error.localizedDescription)")
            ExportPresentation.showError(error, title: "Page Export Failed")
        }
        #endif
    }

    /// A pass AS IMPORTED (#5162): its original file, byte for byte, under its own name. Nothing the
    /// library made of it -- corrections, reorderings -- is in it; that is what Export is for.
    @MainActor
    static func saveOriginal(passId: String, library: LibraryManager.LibraryReference) async {
        #if !os(macOS)
        logger.info("Saving an original is macOS-only; a document picker is needed on iOS.")
        #else
        do {
            guard let original = try await library.segmentService.original(passId: passId) else {
                ExportPresentation.showError(
                    DocumentServiceError.serverError("The original file is not kept for this pass."), title: "Save Original Failed"
                )
                return
            }
            guard let url = await ExportPresentation.savePanel(
                suggestedName: original.fileName ?? "original", contentType: nil
            ) else { return }
            try original.bytes.write(to: url, options: .atomic)
        } catch {
            logger.error("Failed to save the original: \(error.localizedDescription)")
            ExportPresentation.showError(error, title: "Save Original Failed")
        }
        #endif
    }

    #if os(macOS)
    /// The report, in a modal the person dismisses deliberately.
    ///
    /// The losses go in a SELECTABLE accessory rather than the informative
    /// text, so a scholar can copy "named reading orders ×2" into a note. An
    /// alert read once and dismissed by reflex is only marginally better than
    /// a report nobody sees at all.
    @MainActor
    private static func showReport(summary: String, losses: String, url: URL) {
        let alert = NSAlert()
        alert.alertStyle = .informational
        alert.messageText = summary
        alert.informativeText = url.lastPathComponent

        let text = NSTextView(frame: NSRect(x: 0, y: 0, width: 420, height: 92))
        text.string = losses
        text.isEditable = false
        text.isSelectable = true
        text.drawsBackground = false
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 420, height: 92))
        scroll.documentView = text
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        alert.accessoryView = scroll

        alert.addButton(withTitle: "Show in Finder")
        alert.addButton(withTitle: "Done")
        if alert.runModal() == .alertFirstButtonReturn {
            ExportPresentation.revealInFinder(url)
        }
    }
    #endif
}
