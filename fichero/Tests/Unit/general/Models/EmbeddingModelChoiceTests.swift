@testable import Fichero
import Foundation
import Testing

/// #6122: the search models a new project may be made with, and the one preselected.
struct EmbeddingModelChoiceTests {
    @Test("bge-m3 is first and preselected; each choice says what it is in one line")
    func choices() {
        #expect(EmbeddingModelChoice.defaultModel == "BAAI/bge-m3")
        #expect(EmbeddingModelChoice.all.map(\.model) == ["BAAI/bge-m3", "intfloat/multilingual-e5-large"])
        #expect(EmbeddingModelChoice.all.allSatisfy { !$0.blurb.isEmpty && !$0.blurb.contains("\n") })
    }

    @Test("a model not listed is called by the engine's own name")
    func unknownName() {
        #expect(EmbeddingModelChoice.name(of: "BAAI/bge-m3") == "bge-m3")
        #expect(EmbeddingModelChoice.name(of: "someone/new-model") == "someone/new-model")
    }
}
