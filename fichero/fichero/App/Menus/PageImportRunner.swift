import Foundation
import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "PageImport")

/// Reads ONE interchange file into a page as a NEW PASS — the other half of
/// `PageExportRunner` (`source.format.everywhere`, `source.format.import-is-pass`).
///
/// Three things an import has that an export does not, and all three are shown
/// rather than logged:
///
/// * **Which format was actually recognised.** The engine decides by the file's
///   bytes, not its extension, so a file named `notes.txt` may come back as PAGE
///   XML. Reading it as something other than what the person named, without
///   saying so, is the defect the engine's own importer was written to avoid.
/// * **`geometryProblems`** — how many segments had a shape the file could not
///   express and were repaired. A page where forty boxes were repaired is a page
///   somebody should look at, so it leads the report rather than trailing it.
/// * **The same bytes twice** answer 409 and name the pass that already holds
///   them. That is an ANSWER ("you already imported this, it is over there"),
///   not a failure, and it is presented as one.
enum PageImportRunner {
    // MARK: - The part with no UI in it

    /// Everything here is pure, so it is testable without an engine or a window.
    enum Text {
        /// The engine's format names, as a person knows them.
        static func formatTitle(_ raw: String) -> String {
            switch raw.lowercased() {
            case "pagexml": return "PAGE XML"
            case "alto": return "ALTO"
            case "tei": return "TEI"
            case "hocr": return "hOCR"
            case "yolo": return "YOLO"
            default: return raw
            }
        }

        /// The file extensions a format is normally saved under. Used only to notice
        /// a DISAGREEMENT with the recognised format, never to decide one.
        private static func usualExtensions(_ raw: String) -> [String] {
            switch raw.lowercased() {
            case "pagexml", "alto", "tei": return ["xml"]
            case "hocr": return ["hocr", "html", "xml"]
            case "yolo": return ["txt"]
            default: return []
            }
        }

        /// `Read notes.txt as PAGE XML`, and — when the extension says something
        /// else — the sentence that says the CONTENTS decided.
        static func recognisedLine(fileName: String, recognisedFormat: String) -> String {
            let title = formatTitle(recognisedFormat)
            var line = "Read \(fileName) as \(title)."
            let ext = (fileName as NSString).pathExtension.lowercased()
            let usual = usualExtensions(recognisedFormat)
            if !usual.isEmpty, !usual.contains(ext) {
                let shown = ext.isEmpty ? "no extension" : ".\(ext)"
                line += " Its name says \(shown), but its contents are \(title); the contents decide."
            }
            return line
        }

        /// What arrived, in one line. Counts, singular where it is one.
        static func summary(segments: Int, readings: Int, orderEntries: Int) -> String {
            func n(_ count: Int, _ one: String, _ many: String) -> String {
                "\(count) \(count == 1 ? one : many)"
            }
            return "Imported \(n(segments, "segment", "segments")), \(n(readings, "reading", "readings")), "
                + n(orderEntries, "reading-order entry", "reading-order entries")
        }

        /// The warning for repaired shapes, or nil when there were none. Not a footnote:
        /// the caller puts it first.
        static func geometryWarning(count: Int) -> String? {
            guard count > 0 else { return nil }
            let noun = count == 1 ? "segment" : "segments"
            let verb = count == 1 ? "has" : "have"
            return "\(count) \(noun) \(verb) a shape the file could not express properly "
                + "and \(count == 1 ? "was" : "were") repaired (clamped to the page, or given a minimum size). "
                + "Worth a look."
        }

        /// The pages a multi-page file did NOT bring in, or nil when it brought in all of them
        /// (#5308). The engine takes one page onto one page and names the rest (#5143); the report
        /// said nothing, so a 24-page edition looked like a complete import.
        static func pagesLeftOutWarning(pagesInFile: Int, leftOut: [String]) -> String? {
            guard !leftOut.isEmpty else { return nil }
            let taken = max(pagesInFile - leftOut.count, 1)
            return "This file has \(pagesInFile) pages and brought in \(taken) of its \(pagesInFile) pages "
                + "onto this one. Left out: \(leftOut.joined(separator: ", ")). "
                + "Import them onto their own pages, or import the file with its images as a folder."
        }

        /// A new import is a pass BESIDE the existing ones; it is not the working pass.
        static let notWorkingPass =
            "It arrived as a new pass. It is not the working pass, and nothing already on the page was changed."

        /// The whole report, top to bottom, in the order a person needs it: the shape
        /// warning first, then what was read, then what arrived and where it stands.
        static func report(
            fileName: String,
            recognisedFormat: String,
            segments: Int,
            readings: Int,
            orderEntries: Int,
            geometryProblems: Int,
            pagesInFile: Int = 1,
            pagesLeftOut: [String] = []
        ) -> String {
            var lines: [String] = []
            if let left = pagesLeftOutWarning(pagesInFile: pagesInFile, leftOut: pagesLeftOut) { lines.append(left) }
            // No glyph here: the alert itself is presented at `.warning` style when
            // geometryProblems > 0 (see `importPage` below), which already shows a
            // warning icon — a second one in plain text beside it would be a
            // duplicate, and a `String` can't hold an SF Symbol anyway.
            if let warning = geometryWarning(count: geometryProblems) { lines.append(warning) }
            lines.append(recognisedLine(fileName: fileName, recognisedFormat: recognisedFormat))
            lines.append(summary(segments: segments, readings: readings, orderEntries: orderEntries) + ".")
            lines.append(notWorkingPass)
            return lines.joined(separator: "\n\n")
        }

        /// The 32-hex pass id the engine's refusal names, if it can be found. The wording
        /// is the engine's and is shown in full regardless; this only lets the app say
        /// which pass in a sentence of its own.
        static func passID(fromDetail detail: String) -> String? {
            guard let range = detail.range(of: #"pass [0-9a-f]{32}"#, options: .regularExpression) else { return nil }
            return String(detail[range].dropFirst("pass ".count))
        }

        /// "You already imported this" — an answer, with the pass when it is named.
        static func alreadyImported(fileName: String, detail: String) -> (title: String, body: String) {
            let title = "Already imported"
            if let pass = passID(fromDetail: detail) {
                return (title, "\(fileName) is already on this page as pass \(pass). Nothing was written.\n\n\(detail)")
            }
            return (title, "\(fileName) is already on this page. Nothing was written.\n\n\(detail)")
        }
    }

    // MARK: - The import

    /// What the engine said, as plain values (so the report needs no generated types).
    struct Result: Equatable {
        let passId: String
        let format: String
        let segments: Int
        let readings: Int
        let orderEntries: Int
        let geometryProblems: Int
        /// How many pages the file has, and the ones it did not bring in (#5308).
        var pagesInFile: Int = 1
        var pagesLeftOut: [String] = []
    }

    enum Outcome: Equatable {
        case imported(Result)
        /// 409: this exact file is already a pass. `detail` is the engine's own sentence.
        case alreadyImported(detail: String)
    }

    @MainActor
    static func importPage(
        documentId: String,
        documentName: String,
        library: LibraryManager.LibraryReference
    ) async {
        #if !os(macOS)
        logger.info("Page import is macOS-only; a document picker is needed on iOS.")
        #else
        guard let url = await chooseFile(
            message: "Choose a PAGE XML, ALTO, TEI, hOCR or YOLO file to add to “\(documentName)” as a new pass"
        ) else { return }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            let data = try Data(contentsOf: url)
            let outcome = try await library.documentService.importPage(
                documentId: documentId, data: data, filename: url.lastPathComponent
            )
            switch outcome {
            case .imported(let result):
                logger.info("Imported \(url.lastPathComponent) into \(documentId) as pass \(result.passId)")
                showReport(
                    title: Text.summary(segments: result.segments, readings: result.readings,
                                        orderEntries: result.orderEntries),
                    body: Text.report(
                        fileName: url.lastPathComponent, recognisedFormat: result.format,
                        segments: result.segments, readings: result.readings,
                        orderEntries: result.orderEntries, geometryProblems: result.geometryProblems,
                        pagesInFile: result.pagesInFile, pagesLeftOut: result.pagesLeftOut
                    ),
                    style: result.geometryProblems > 0 || !result.pagesLeftOut.isEmpty ? .warning : .informational
                )
            case .alreadyImported(let detail):
                let answer = Text.alreadyImported(fileName: url.lastPathComponent, detail: detail)
                showReport(title: answer.title, body: answer.body, style: .informational)
            }
        } catch {
            logger.error("Failed to import page: \(error.localizedDescription)")
            ExportPresentation.showError(error, title: "Page Import Failed")
        }
        #endif
    }

    #if os(macOS)
    @MainActor
    private static func chooseFile(message: String) async -> URL? {
        await withCheckedContinuation { continuation in
            let panel = NSOpenPanel()
            panel.canChooseFiles = true
            panel.canChooseDirectories = false
            panel.allowsMultipleSelection = false
            panel.message = message
            panel.prompt = "Import"
            // No type filter: the engine decides by the file's bytes, and a filter would
            // refuse a renamed file the engine could read.
            panel.begin { result in
                continuation.resume(returning: result == .OK ? panel.url : nil)
            }
        }
    }

    /// The report, in a modal the person dismisses deliberately, with the text
    /// SELECTABLE so it can be copied into a note (as the export's is).
    @MainActor
    private static func showReport(title: String, body: String, style: NSAlert.Style) {
        let alert = NSAlert()
        alert.alertStyle = style
        alert.messageText = title

        let text = NSTextView(frame: NSRect(x: 0, y: 0, width: 440, height: 150))
        text.string = body
        text.isEditable = false
        text.isSelectable = true
        text.drawsBackground = false
        text.textContainerInset = NSSize(width: 0, height: 4)
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 440, height: 150))
        scroll.documentView = text
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        alert.accessoryView = scroll
        alert.addButton(withTitle: "Done")
        alert.runModal()
    }
    #endif
}
