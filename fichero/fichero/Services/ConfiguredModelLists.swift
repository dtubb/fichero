import FicheroAPIClient
import Foundation

/// One fetch of a provider's configured models, however many pickers ask at once (#6376).
///
/// Settings opens ten model pickers together and each used to list every provider's models itself,
/// so the engine answered the same request ten times per provider. Callers that arrive while a
/// fetch is running share it, and a result is reused for a moment (`reuseSeconds`) so the pickers
/// that appear together share one fetch; reopening Settings later fetches again.
///
/// A provider the engine has no model list for (HTTP 404: the local runtimes omlx, spacy, kraken
/// and whisper keep their models in their own catalog, not in the configured-models table) has an
/// empty list. That is not an error and is not logged as one.
@MainActor
final class ConfiguredModelLists {
    typealias Models = [Components.Schemas.UserModelResponse]

    static let reuseSeconds: TimeInterval = 2

    private var inflight: [String: Task<Models, Error>] = [:]
    private var recent: [String: (at: Date, models: Models)] = [:]
    private let now: () -> Date

    init(now: @escaping () -> Date = Date.init) {
        self.now = now
    }

    func models(providerId: String, fetch: @escaping @MainActor () async throws -> Models) async throws -> Models {
        if let hit = recent[providerId], now().timeIntervalSince(hit.at) < Self.reuseSeconds {
            return hit.models
        }
        if let running = inflight[providerId] {
            return try await running.value
        }
        let task = Task { @MainActor in
            do {
                return try await fetch()
            } catch ProviderAPIServiceError.unexpectedResponse(404) {
                return Models()
            }
        }
        inflight[providerId] = task
        defer { inflight[providerId] = nil }
        let result = try await task.value
        recent[providerId] = (now(), result)
        return result
    }
}
