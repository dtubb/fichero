import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime

/// A project's kept exports (#5485, `source.onboard.kept-exported`; section 7b, screen 3): folders
/// outside the project that Fichero keeps an up-to-date copy of the work in, each in one format,
/// one file per page or per document. One-way: Fichero writes the folder and never reads it back.
/// The app half of `/api/export/kept`, through the generated client only.
///
/// One per project (`LibraryReference.keptExportStore`), over that project's client. Setup's
/// screen holds rows not yet kept (`drafts`) and keeps them on Continue; the project Inspector
/// lists the kept ones with Write Now and Remove. Each change splices the one export it touched;
/// only `load()` replaces the list.
@MainActor
@Observable
final class KeptExportStore {
    typealias Format = Components.Schemas.KeptExportRequest.FormatPayload
    typealias Per = Components.Schemas.KeptExportRequest.PerPayload

    /// A row on setup's screen, not kept yet: its folder (nil until chosen), format and per.
    struct Draft: Identifiable, Equatable {
        let id = UUID()
        var folder: URL?
        var format: Format = .word {
            // A page format is one file per page only (the engine refuses per document).
            didSet { if !KeptExportStore.allowsPerDocument(format) { per = .page } }
        }
        var per: Per = .document {
            didSet { if per == .document, !KeptExportStore.allowsPerDocument(format) { per = .page } }
        }
    }

    /// The project's kept exports as the engine last reported them (`GET /api/export/kept`).
    private(set) var exports: [Components.Schemas.KeptExport] = []
    /// Setup's rows not yet kept.
    var drafts: [Draft] = []
    /// Exports a Write Now was just asked for (their job is in Activity).
    private(set) var writing: Set<String> = []
    private(set) var hasLoaded = false
    var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    // MARK: Formats

    /// The formats offered, in the spec's order (section 7b, screen 3).
    static let formats: [Format] = [.word, .markdown, .plainText, .alto, .pagexml, .tei, .hocr]

    static func title(of format: Format) -> String {
        switch format {
        case .word: "Word"
        case .markdown: "Markdown"
        case .plainText: "Plain text"
        case .alto: "ALTO XML"
        case .pagexml: "PAGE XML"
        case .tei: "TEI"
        case .hocr: "hOCR"
        }
    }

    /// The page formats (ALTO, PAGE, TEI, hOCR) describe one page each: per page only, as the
    /// engine rules (`kept_export.PAGE_FORMATS`).
    nonisolated static func allowsPerDocument(_ format: Format) -> Bool {
        switch format {
        case .word, .markdown, .plainText: true
        case .alto, .pagexml, .tei, .hocr: false
        }
    }

    /// A kept export's format, as the list names it.
    static func title(of format: Components.Schemas.KeptExport.FormatPayload) -> String {
        Format(rawValue: format.rawValue).map { title(of: $0) } ?? format.rawValue
    }

    static func title(of per: Components.Schemas.KeptExport.PerPayload) -> String {
        per == .page ? "One file per page" : "One file per document"
    }

    // MARK: Reading

    /// Read the project's kept exports; the one place the list is replaced whole.
    func load() async {
        do {
            exports = try await client.api.listKeptExportsApiExportKeptGet().ok.body.json.exports
            hasLoaded = true
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read this project's kept exports: \(error.localizedDescription)"
        }
    }

    // MARK: Setup's rows

    func addDraft() { drafts.append(Draft()) }

    func removeDraft(_ id: UUID) { drafts.removeAll { $0.id == id } }

    /// Keep every row that has a folder (`POST /api/export/kept` for each); a row with no folder
    /// chosen is not an export and is dropped. A kept row leaves `drafts` and joins `exports`; a
    /// refused one stays with the engine's sentence. Returns whether every row was kept.
    @discardableResult
    func keepDrafts() async -> Bool {
        drafts.removeAll { $0.folder == nil }
        var allKept = true
        for draft in drafts {
            guard let folder = draft.folder else { continue }
            if await keep(folder: folder, format: draft.format, per: draft.per) {
                drafts.removeAll { $0.id == draft.id }
            } else {
                allKept = false
            }
        }
        return allKept
    }

    /// Keep one export (`POST /api/export/kept`): the folder (granted to the engine first, the
    /// import path's own call, so a sandboxed engine may write there), the format and per.
    @discardableResult
    func keep(folder: URL, format: Format, per: Per) async -> Bool {
        errorMessage = nil
        // The panel's URL is security-scoped: open it while the grant mints its bookmark. A
        // failed grant logs; the engine's own refusal is then the honest answer.
        let didStartAccess = folder.startAccessingSecurityScopedResource()
        try? await FolderAccessManager.shared.grantAccessForImport(folder)
        if didStartAccess { folder.stopAccessingSecurityScopedResource() }
        let per = Self.allowsPerDocument(format) ? per : .page
        do {
            switch try await client.api.keepExportApiExportKeptPost(
                body: .json(.init(folder: folder.path, format: format, per: per))
            ) {
            case .ok(let success):
                let kept = try success.body.json
                if let index = exports.firstIndex(where: { $0.id == kept.id }) {
                    exports[index] = kept
                } else {
                    exports.append(kept)
                }
                return true
            case .unprocessableContent:
                errorMessage = "The engine would not keep an export in \(folder.lastPathComponent)."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not keep an export in \(folder.lastPathComponent) (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = await Self.engineWords(error)
                ?? "Could not keep an export in \(folder.lastPathComponent): \(error.localizedDescription)"
        }
        return false
    }

    // MARK: Kept ones

    /// Stop keeping an export (`DELETE /api/export/kept/{id}`); the files it wrote stay.
    @discardableResult
    func remove(_ exportId: String) async -> Bool {
        errorMessage = nil
        do {
            switch try await client.api.removeKeptExportApiExportKeptExportIdDelete(path: .init(exportId: exportId)) {
            case .ok:
                exports.removeAll { $0.id == exportId }
                writing.remove(exportId)
                return true
            case .unprocessableContent:
                errorMessage = "The engine did not understand which export to remove."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not remove this export (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = "Could not remove this export: \(error.localizedDescription)"
        }
        return false
    }

    /// Write an export now (`POST /api/export/kept/{id}/write`), as a background job in Activity.
    @discardableResult
    func writeNow(_ exportId: String) async -> Bool {
        errorMessage = nil
        do {
            switch try await client.api.writeKeptExportApiExportKeptExportIdWritePost(
                path: .init(exportId: exportId)
            ) {
            case .ok:
                writing.insert(exportId)
                return true
            case .unprocessableContent:
                errorMessage = "The engine did not understand which export to write."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not write this export (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = "Could not write this export: \(error.localizedDescription)"
        }
        return false
    }

    /// A refusal in words (a 422 whose `detail` is a sentence) cannot decode as the generated
    /// validation shape: say the engine's sentence, never the decoding error.
    private static func engineWords(_ error: Error) async -> String? {
        guard let clientError = error as? ClientError, let body = clientError.responseBody,
              let data = try? await Data(collecting: body, upTo: 1 << 16) else { return nil }
        return EngineErrorDetail.message(from: data)
    }
}
