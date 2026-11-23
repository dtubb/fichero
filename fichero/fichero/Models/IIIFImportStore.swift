import FicheroAPIClient
import Foundation
import Observation

/// Import from IIIF (#5671): a manifest or collection URL (https only) into a folder bound to it, by reference, as one
/// job in Activity; and a bound folder's Refresh. The engine reads, binds and refreshes (`POST /api/iiif/import`,
/// `POST /api/iiif/folders/{id}/refresh`, the `import-iiif` job); this store asks and says where the job is.
@MainActor
@Observable
final class IIIFImportStore {
    let client: FicheroClient
    /// The sidebar's spinner and error mark for the folder an add fills (#7066).
    let folderImports: FolderImportTracker

    /// The import sheet is open (File › Import from IIIF…).
    var isChoosing = false
    private(set) var isStarting = false
    /// The job the last import or refresh started, for Activity.
    private(set) var startedJobId: String?
    private(set) var refusal: String?

    init(client: FicheroClient, folderImports: FolderImportTracker = FolderImportTracker()) {
        self.client = client
        self.folderImports = folderImports
    }

    /// A pasted source as the engine takes it: an https URL; nil for anything else (an http URL, a word, a file).
    nonisolated static func source(from text: String) -> URL? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), url.scheme?.lowercased() == "https", let host = url.host,
              !host.isEmpty else { return nil }
        return url
    }

    /// Import the source into `folderId` (nil: the folder already bound to it, else a new one named after it).
    /// Returns whether the engine started the job.
    @discardableResult
    func importSource(_ url: URL, into folderId: String?) async -> Bool {
        refusal = nil
        isStarting = true
        defer { isStarting = false }
        do {
            let response = try await client.api.importFromIiifApiIiifImportPost(
                body: .json(.init(url: url.absoluteString, folderId: folderId))
            )
            switch response {
            case .ok(let success):
                let started = try success.body.json
                startedJobId = started.jobId
                watch(jobId: started.jobId, folderId: started.folderId)
                return true
            case .unprocessableContent:
                refusal = "Fichero could not read \(url.host ?? "that address") as a IIIF manifest or collection."
            case .undocumented(let code, let payload):
                refusal = await EngineErrorDetail.message(from: payload) ?? "Could not start the import (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return false }
            refusal = "Could not start the import: \(error.localizedDescription)"
        }
        return false
    }

    /// The folder shows a spinner from the engine's start answer until the job ends; a failed job keeps the row, marked,
    /// with the job's reason (#7066). The job's state is read from the same Activity route the Activity window uses.
    private func watch(jobId: String, folderId: String) {
        folderImports.begin(folderId: folderId)
        Task { [client, folderImports] in
            while !Task.isCancelled {
                if let tree = try? await client.api.getJobTreeApiActivityJobsJobIdGet(path: .init(jobId: jobId)),
                   case .ok(let read) = tree, let job = try? read.body.json {
                    switch job.state {
                    case "done", "completed", "cancelled":
                        folderImports.finish(folderId: folderId)
                        return
                    case "failed":
                        folderImports.fail(folderId: folderId, reason: job.reason ?? "The import failed.")
                        return
                    default: break
                    }
                }
                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    /// Read a bound folder's source again, as one job: what the institution added appears; nothing is made twice.
    @discardableResult
    func refresh(folderId: String) async -> Bool {
        refusal = nil
        isStarting = true
        defer { isStarting = false }
        do {
            let response = try await client.api.refreshIiifFolderApiIiifFoldersFolderIdRefreshPost(
                path: .init(folderId: folderId)
            )
            switch response {
            case .ok(let success):
                let started = try success.body.json
                startedJobId = started.jobId
                watch(jobId: started.jobId, folderId: started.folderId)
                return true
            case .unprocessableContent:
                refusal = "Fichero could not refresh this folder."
            case .undocumented(let code, let payload):
                refusal = await EngineErrorDetail.message(from: payload) ?? "Could not refresh (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return false }
            refusal = "Could not refresh: \(error.localizedDescription)"
        }
        return false
    }
}

/// What a folder bound to a IIIF source says about it (`metadata.iiif_source` and the refresh's counts), or nil for
/// a folder that is not bound.
struct IIIFFolderSource: Equatable {
    let url: String
    let canvases: Int?
    let withdrawn: Int?
    let refreshedAt: String?
    let rights: String?

    static func of(_ document: Document) -> IIIFFolderSource? {
        guard document.docType == .folder,
              let url = document.metadata["iiif_source"]?.value as? String, !url.isEmpty else { return nil }
        let meta = document.metadata
        return IIIFFolderSource(
            url: url,
            canvases: meta["iiif_canvases"]?.value as? Int,
            withdrawn: meta["iiif_withdrawn"]?.value as? Int,
            refreshedAt: meta["iiif_refreshed_at"]?.value as? String,
            rights: meta["iiif_rights"]?.value as? String
        )
    }

    /// The counts in words: "1,204 pages; 3 no longer listed by the source".
    var countsSentence: String? {
        guard let canvases else { return nil }
        var words = canvases == 1 ? "1 page" : "\(canvases.formatted()) pages"
        if let withdrawn, withdrawn > 0 {
            words += "; \(withdrawn) no longer listed by the source, kept here"
        }
        return words
    }
}
