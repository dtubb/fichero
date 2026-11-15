@testable import Fichero
import Foundation
import Testing

/// `activity.window.models-tree` (#6588, decision 33): the sidebar's Models are place › provider › model, each icon filled while
/// loaded and dotted while working, with its memory, or "—" when nothing measures it.
struct ActivityModelsTreeTests {
    private let kraken = ActivityModelEntry(id: "this-mac|Kraken|blla", name: "blla", place: .thisMac, provider: "Kraken",
                                            loaded: true, active: true, memoryBytes: 2_500_000_000, memoryEstimated: true,
                                            running: 1, pagesToday: 4)
    private let embedder = ActivityModelEntry(id: "this-mac|Embeddings|nomic", name: "nomic", place: .thisMac,
                                              provider: "Embeddings", loaded: true, memoryBytes: 312_000_000)
    private let claude = ActivityModelEntry(id: "cloud|Anthropic|claude", name: "claude", place: .cloud, provider: "Anthropic",
                                            callsToday: 2)
    private let acenet = ActivityModelEntry(id: "remote|acenet|trocr", name: "trocr", place: .remote, provider: "acenet")

    @Test("the tree is This Mac, Remote, Cloud, each its providers in the engine's order, empty places left out")
    func order() {
        let tree = ActivityModelEntry.tree([claude, kraken, embedder, acenet])
        #expect(tree.map(\.place) == [.thisMac, .remote, .cloud])
        #expect(tree[0].providers.map(\.name) == ["Kraken", "Embeddings"])
        #expect(ActivityModelEntry.tree([claude]).map(\.place) == [.cloud])
    }

    @Test("loaded is a filled icon, not loaded hollow; memory measured, estimated with ~, unmeasured a dash")
    func iconsAndMemory() {
        #expect(kraken.symbol == "cpu.fill" && claude.symbol == "cpu")
        #expect(kraken.memoryWords.hasPrefix("~"))
        #expect(!embedder.memoryWords.hasPrefix("~") && embedder.memoryWords != "—")
        #expect(claude.memoryWords == "—")
    }

    @Test("two projects' lists are one: a model in both is one row, loaded or working if either says so, counts added")
    func merged() {
        var idle = kraken
        idle.active = false
        idle.pagesToday = 6
        let one = ActivityModelEntry.merged([[idle, claude], [kraken]])
        #expect(one.count == 2)
        let merged = try? #require(one.first { $0.id == kraken.id })
        #expect(merged?.active == true && merged?.pagesToday == 10)
    }
}
