import Foundation

/// The search models a project may be made with (`search.embedding.chosen-at-project-creation`, #6122). The engine
/// holds the same list (`GET /api/search/embedding`); a new project has no engine to ask yet, so the names are here
/// and the engine refuses any it does not know.
struct EmbeddingModelChoice: Identifiable, Equatable {
    let model: String
    let name: String
    /// One line: what it is good for.
    let blurb: String

    var id: String { model }

    static let defaultModel = "BAAI/bge-m3"

    static let all: [EmbeddingModelChoice] = [
        EmbeddingModelChoice(model: defaultModel, name: "bge-m3",
                             blurb: "Reads every script, including old and rare ones. Recommended."),
        EmbeddingModelChoice(model: "intfloat/multilingual-e5-large", name: "multilingual-e5-large",
                             blurb: "Fast, for modern European languages.")
    ]

    /// What a project that already holds vectors made with `model` is called; the engine's own name when it is not listed.
    static func name(of model: String) -> String {
        all.first { $0.model == model }?.name ?? model
    }
}
