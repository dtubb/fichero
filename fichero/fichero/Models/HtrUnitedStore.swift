import FicheroAPIClient
import Foundation
import Observation

/// The HTR-United datasets offered for a project (#5571, Swift half): `GET /api/recipes/htr-united`.
/// The engine matches the kept catalogue to the languages and scripts and says what each dataset may be
/// used as (`as`: a bake-off test set, training data) and what to accept first (`accept`); the app shows
/// that and never works out a licence or a use. The call never reaches the network (the search job keeps
/// the catalogue), so a project with no kept catalogue gets an empty list and `fetchedAt == nil`.
@MainActor
@Observable
final class HtrUnitedStore {
    private(set) var datasets: [Components.Schemas.HtrUnitedDataset] = []
    /// When the engine kept the catalogue; nil when it never has.
    private(set) var fetchedAt: String?
    private(set) var isLoading = false
    var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// Read the datasets kept for these languages and scripts (codes or names). Languages are required by
    /// the engine, so none is an empty list with no call.
    func load(languages: [String], scripts: [String]) async {
        guard !languages.isEmpty else {
            datasets = []
            fetchedAt = nil
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await client.api.htrUnitedDatasetsApiRecipesHtrUnitedGet(
                query: .init(languages: languages.joined(separator: ","), scripts: scripts.joined(separator: ","))
            )
            switch response {
            case .ok(let success):
                let list = try success.body.json
                datasets = list.datasets
                fetchedAt = list.fetchedAt
                errorMessage = nil
            case .unprocessableContent:
                errorMessage = "The engine would not look for datasets for these languages and scripts."
            case .undocumented(let code, _):
                errorMessage = "Could not read the datasets (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the datasets: \(error.localizedDescription)"
        }
    }

    /// Whether a dataset may be used as `use` ("test-set" or "training") now; false until its licence is accepted.
    static func allows(_ dataset: Components.Schemas.HtrUnitedDataset, _ use: String) -> Bool {
        dataset._as.contains(use)
    }
}
