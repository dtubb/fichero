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

    @Test("every place set up is in the tree, used or not: another Mac, a cluster, a cloud provider; This Mac always")
    func placesSetUp() {
        let places: [ActivityModelEntry.SetUp] = [
            .init(place: .thisMac, provider: "This Mac"), .init(place: .remote, provider: "studio.example"),
            .init(place: .remote, provider: "ACENET"), .init(place: .cloud, provider: "Anthropic")
        ]
        let quiet = ActivityModelEntry.tree([], places: places)
        #expect(quiet.map(\.place) == [.thisMac, .remote, .cloud], "a quiet project still shows where work can run")
        #expect(quiet[0].providers.isEmpty, "the place's own name is not a provider under it")
        #expect(quiet[1].providers.map(\.name) == ["studio.example", "ACENET"])

        let used = ActivityModelEntry.tree([claude, kraken], places: places)
        #expect(used[2].providers.map(\.name) == ["Anthropic"], "a provider used and set up is one node")
        #expect(used[2].providers[0].models == [claude])
        #expect(used[0].providers.map(\.name) == ["Kraken"])
    }

    @Test("two projects' answers are one: places once each, models merged")
    func answersMerged() {
        let here = ActivityModelEntry.SetUp(place: .thisMac, provider: "This Mac")
        let cloud = ActivityModelEntry.SetUp(place: .cloud, provider: "Anthropic")
        let one = ActivityModelsAnswer.merged([.init(models: [kraken], places: [here, cloud]),
                                               .init(models: [kraken, claude], places: [here])])
        #expect(one.places == [here, cloud])
        #expect(one.models.map(\.id) == [kraken.id, claude.id])
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
