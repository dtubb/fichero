import FicheroAPIClient
import Foundation

/// The search models a project may be made with (`search.embedding.chosen-at-project-creation`, #6122). The engine
/// holds the list and the blurbs (`GET /api/search/embedding/models`, library-free, #6144); `all` is only the fallback
/// for an engine that cannot be reached, and the engine refuses any model it does not know.
struct EmbeddingModelChoice: Identifiable, Equatable {
    let model: String
    let name: String
    /// One line: what it is good for.
    let blurb: String
    /// The engine's flag for the model it recommends; the menu says so, the blurb does not repeat it.
    var recommended = false

    var id: String { model }

    static let defaultModel = "BAAI/bge-m3"

    static let all: [EmbeddingModelChoice] = [
        EmbeddingModelChoice(model: defaultModel, name: "bge-m3",
                             blurb: "Reads every script, including old and rare ones.", recommended: true),
        EmbeddingModelChoice(model: "intfloat/multilingual-e5-large", name: "multilingual-e5-large",
                             blurb: "Fast, for modern European languages.")
    ]

    /// The engine's list, the recommended model first; nil when it cannot be read (the caller keeps `all`).
    static func fetch(client: FicheroClient) async -> [EmbeddingModelChoice]? {
        guard case .ok(let success)? = try? await client.api.listEmbeddingModelsApiSearchEmbeddingModelsGet(.init()),
              let list = try? success.body.json.models, !list.isEmpty else { return nil }
        return list.map { EmbeddingModelChoice(model: $0.model, name: $0.name, blurb: $0.blurb, recommended: $0.recommended) }
    }

    /// What a project that already holds vectors made with `model` is called; the engine's own name when it is not listed.
    static func name(of model: String, in choices: [EmbeddingModelChoice] = all) -> String {
        choices.first { $0.model == model }?.name ?? model
    }
}
