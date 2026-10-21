import FicheroAPIClient
import Foundation
import Observation

/// What a project's pages' readers made of the same lines, for choosing between them (`source.compare.readers-answer`, #5900):
/// `GET /api/documents/{page_id}/compare-readers`, read once per page and kept. One per project.
@MainActor
@Observable
final class ReaderComparisonStore {
    typealias Comparison = Components.Schemas.CompareReadersResponse

    enum State: Equatable {
        case loading
        case loaded(Comparison)
        case unavailable(String)
    }

    private(set) var pages: [String: State] = [:]
    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    func comparison(of pageId: String) -> Comparison? {
        if case .loaded(let comparison) = pages[pageId] { return comparison }
        return nil
    }

    /// `readers` narrows to those readers' ids, `onlyDiffering` leaves out the lines where they agree, `tryStage` answers the
    /// same shape from that stage's Try candidates (nothing to pick). A refusal is said in the engine's words.
    func load(pageId: String, readers: [String] = [], onlyDiffering: Bool = false, tryStage: String? = nil) async {
        if pages[pageId] == nil { pages[pageId] = .loading }
        do {
            let response = try await client.api.getCompareReadersApiDocumentsPageIdCompareReadersGet(
                path: .init(pageId: pageId),
                query: .init(readers: readers.isEmpty ? nil : readers.joined(separator: ","),
                             onlyDiffering: onlyDiffering, tryStage: tryStage))
            switch response {
            case .ok(let success):
                let found = try success.body.json
                if pages[pageId] != .loaded(found) { pages[pageId] = .loaded(found) }
            case .unprocessableContent:
                pages[pageId] = .unavailable("Fichero could not compare this page's readers.")
            case .undocumented(let code, let payload):
                let words = await EngineErrorDetail.message(from: payload)
                pages[pageId] = .unavailable(words ?? "Could not compare the readers (HTTP \(code)).")
            }
        } catch {
            if error.isCancellationError { return }
            pages[pageId] = .unavailable(error.localizedDescription)
        }
    }
}
