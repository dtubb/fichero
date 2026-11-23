import FicheroAPIClient
import Foundation
import Observation

/// The Models & Cluster window's verbs over the engine's routes (`models.manage.*`, `models.search.is-the-finder`,
/// `models.bookmark.kept-not-added`, #6588): the found cards (the project's `ModelFinderStore`: load, online search,
/// download), Bookmark and Remove Bookmark, Delete with its confirmation, and Unload. It works out nothing: a card's
/// verb and words are `ModelCandidateRules`, a row's button is `ModelsWindowModel`.
@MainActor
@Observable
final class ModelsWindowStore {
    let finder: ModelFinderStore
    /// The installed row Delete was pressed on, waiting for the person's yes.
    var pendingDelete: ActivityModelEntry?
    var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient, finder: ModelFinderStore) {
        self.client = client
        self.finder = finder
    }

    /// What the rules need of a candidate, taken from the engine's card.
    static func facts(_ candidate: Components.Schemas.ModelCandidate, downloading: Bool) -> ModelCandidateRules.Facts {
        ModelCandidateRules.Facts(
            availability: ModelCandidateRules.Availability(rawValue: candidate.availability.rawValue) ?? .notHere,
            bookmarked: candidate.bookmarked ?? false,
            bookmarkKey: candidate.bookmarkKey,
            refused: candidate.refused,
            downloading: downloading,
            size: candidate.size
        )
    }

    /// The card's facts, with its download's state read from the one download path.
    func facts(_ candidate: Components.Schemas.ModelCandidate) -> ModelCandidateRules.Facts {
        let downloading = ModelFinderStore.downloadKey(candidate).map(finder.downloads.isActive) ?? false
        return Self.facts(candidate, downloading: downloading)
    }

    /// The cards of a list, the engine's order kept.
    func cards(_ list: ModelCandidateRules.List, matching text: String) -> [Components.Schemas.ModelCandidate] {
        finder.candidates.filter {
            ModelCandidateRules.rows(list, in: [facts($0)]).count == 1 && ModelCandidateRules.matches($0.name, text)
        }
    }

    /// Press a card's one verb: Download through the one download path; Bookmark and Remove Bookmark through the routes.
    func press(_ candidate: Components.Schemas.ModelCandidate) async {
        switch ModelCandidateRules.verb(facts(candidate)) {
        case "Download": await finder.download(candidate)
        case "Bookmark": await setBookmark(candidate, kept: true)
        case "Remove Bookmark": await setBookmark(candidate, kept: false)
        default: break
        }
    }

    /// Press a row's one button: Unload frees the idle models; Delete asks first.
    func press(_ row: ActivityModelEntry) async {
        switch ModelsWindowModel.button(for: row) {
        case "Unload": await unloadIdle()
        case "Delete": pendingDelete = row
        default: break
        }
    }

    /// The person said yes to Delete: the engine removes the model, or answers 409 naming the steps that use it.
    func confirmDelete() async {
        guard let row = pendingDelete, let type = row.modelType, let id = row.modelId else { return }
        pendingDelete = nil
        do {
            let response = try await client.api.deleteModelApiLocalModelsModelTypeModelIdDelete(
                path: .init(modelType: type, modelId: id), query: .init(confirm: true))
            switch response {
            case .ok: errorMessage = nil
            case .unprocessableContent: errorMessage = "The engine would not delete \(row.name)."
            case .undocumented(let code, _): errorMessage = "\(row.name) was not deleted (HTTP \(code)): a step may use it."
            }
        } catch {
            errorMessage = "Could not delete \(row.name): \(error.localizedDescription)"
        }
    }

    /// Unload the models nothing is using. ponytail: the engine has no per-model unload (`models.manage.load-and-unload`).
    private func unloadIdle() async {
        do {
            _ = try await client.api.unloadIdleModelsApiActivityModelsUnloadIdlePost().ok
            errorMessage = nil
        } catch {
            errorMessage = "Could not unload: \(error.localizedDescription)"
        }
    }

    private func setBookmark(_ candidate: Components.Schemas.ModelCandidate, kept: Bool) async {
        guard let key = candidate.bookmarkKey else { return }
        let body = Components.Schemas.BookmarkRequest(key: key)
        do {
            if kept {
                _ = try await client.api.bookmarkCandidateApiRecipesCandidatesBookmarkPost(body: .json(body)).ok
            } else {
                _ = try await client.api.removeCandidateBookmarkApiRecipesCandidatesBookmarkDelete(body: .json(body)).ok
            }
            errorMessage = nil
            await finder.reload()
        } catch {
            errorMessage = "Could not \(kept ? "bookmark" : "remove the bookmark of") \(candidate.name): \(error.localizedDescription)"
        }
    }
}
