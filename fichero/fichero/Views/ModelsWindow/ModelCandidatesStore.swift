import FicheroAPIClient
import Foundation
import Observation

/// The Models window's found models (`models.search.is-the-finder`, `models.bookmark.kept-not-added`, #6588): the engine's
/// candidates read through the project's `ModelFinderStore` (its load, online search and download), and the bookmark verbs
/// over the engine's routes. It works out nothing: the rules for a card are `ModelCandidateRules`.
@MainActor
@Observable
final class ModelCandidatesStore {
    let finder: ModelFinderStore
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

    /// The card's facts with its download's state read from the one download path.
    func facts(_ candidate: Components.Schemas.ModelCandidate) -> ModelCandidateRules.Facts {
        let downloading = ModelFinderStore.downloadKey(candidate).map(finder.downloads.isActive) ?? false
        return Self.facts(candidate, downloading: downloading)
    }

    /// Press a card's one verb: Download through the one download path, Bookmark and Remove Bookmark through the routes.
    func press(_ candidate: Components.Schemas.ModelCandidate) async {
        switch ModelCandidateRules.verb(facts(candidate)) {
        case "Download": await finder.download(candidate)
        case "Bookmark": await setBookmark(candidate, kept: true)
        case "Remove Bookmark": await setBookmark(candidate, kept: false)
        default: break
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
