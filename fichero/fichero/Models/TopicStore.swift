import FicheroAPIClient
import Foundation
import Observation

/// Every topic's and every recipe job's explanation, as the engine's one registry
/// serves it (`GET /api/topics`, `GET /api/topics/{topic_id}`;
/// `source.onboard.topics-written-once`, `source.onboard.teaches-the-method`).
/// Setup and the Inspector read their words from here, so a step is explained in
/// one place and the app writes none of it. Loaded once; a refresh replaces one
/// topic in place.
@MainActor
@Observable
final class TopicStore {
    private(set) var topics: [String: Components.Schemas.TopicInfo] = [:]
    private(set) var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// The topic with this id, or nil when the registry does not know it (the
    /// caller shows what it has, never an invented explanation).
    func topic(_ id: String?) -> Components.Schemas.TopicInfo? {
        id.flatMap { topics[$0] }
    }

    /// The whole registry, once.
    func load() async {
        guard topics.isEmpty else { return }
        do {
            guard case .ok(let success) = try await client.api.listTopicsApiTopicsGet() else {
                errorMessage = "The engine did not give the explanations."
                return
            }
            for topic in try success.body.json.items { topics[topic.id] = topic }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the explanations: \(error.localizedDescription)"
        }
    }

    /// One topic again, replaced in place.
    func refresh(_ id: String) async {
        do {
            if case .ok(let success) = try await client.api.getTopicApiTopicsTopicIdGet(path: .init(topicId: id)) {
                topics[id] = try success.body.json
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the explanation of “\(id)”: \(error.localizedDescription)"
        }
    }
}
