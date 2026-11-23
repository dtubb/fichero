@testable import Fichero
import Foundation
import Testing

/// `models.window.is-activitys-shape` (#6588): the Models & Cluster window is a `Window` scene the owner opens by id from the
/// Window menu, its sidebar sections and badges come from `ModelsWindowModel`, and a row needing you is listed first.
struct ModelsWindowSceneTests {
    private let broken = ActivityModelEntry(id: "this-mac|MLX|chandra", name: "chandra", place: .thisMac, provider: "MLX",
                                            lastFailed: .init(words: "Model failed to load", kind: "model-broken", button: "retry"))
    private let idle = ActivityModelEntry(id: "this-mac|MLX|small", name: "small", place: .thisMac, provider: "MLX")
    private let keyless = ActivityModelEntry(id: "cloud|Anthropic|claude", name: "claude", place: .cloud,
                                             provider: "Anthropic", account: .needsKey)

    @Test("the window opens by a stable id and is titled Models & Cluster, the name the Window menu lists")
    func opensByID() {
        #expect(ModelsWindowModel.windowID == "models-cluster")
        #expect(ModelsWindowModel.windowTitle == "Models & Cluster")
    }

    @Test("the window is a pane kind a main window can hold, kept by its own name")
    func paneKind() throws {
        #expect(PaneSpec.Kind.selectableKinds.contains(.models))
        #expect(PaneSpec.Kind.models.title == "Models & Cluster")
        let data = try JSONEncoder().encode([PaneKind.models])
        #expect(String(bytes: data, encoding: .utf8) == "[\"models\"]")
        #expect(PaneFocus.models.paneKind == .models)
    }

    @Test("the sidebar's sections and items, each badged with its rows needing you, come from the model")
    func sidebarFromTheModel() {
        let sidebar = ModelsWindowModel.sidebar([broken, idle, keyless])
        #expect(sidebar.map(\.section) == [.models, .thisMac, .places, .work])
        let entries = sidebar.flatMap(\.entries)
        #expect(entries.map(\.item) == ModelsWindowModel.items.flatMap(\.items))
        #expect(entries.first { $0.item == .thisMac }?.badge == 1)
        #expect(entries.first { $0.item == .place(.cloud) }?.badge == 1)
        #expect(entries.first { $0.item == .runningNow }?.badge == 0)
        #expect(entries.allSatisfy { !$0.title.isEmpty && !$0.icon.isEmpty })
    }

    @Test("a row needing you is listed first in its item")
    func needsYouSortsFirst() {
        #expect(ModelsWindowModel.rows(.thisMac, in: [idle, broken]).map(\.name) == ["chandra", "small"])
    }

    @Test("the Inspector follows the selection: the selected listed row, nothing for none or an unlisted one")
    func inspectorFollowsTheSelection() {
        let rows = [broken, idle]
        #expect(ModelsWindowModel.selectedRow(idle.id, in: rows)?.name == "small")
        #expect(ModelsWindowModel.selectedRow(broken.id, in: rows)?.name == "chandra")
        #expect(ModelsWindowModel.selectedRow(nil, in: rows) == nil)
        #expect(ModelsWindowModel.selectedRow(keyless.id, in: rows) == nil)
    }

    @MainActor
    @Test("the shared models store keeps an answer once and merges the libraries asked for")
    func sharedStore() {
        let store = ModelsAnswerStore()
        let one = UUID(), two = UUID()
        #expect(store.record(ActivityModelsAnswer(models: [idle]), for: one))
        #expect(!store.record(ActivityModelsAnswer(models: [idle]), for: one), "the same answer redraws nothing")
        #expect(store.record(ActivityModelsAnswer(models: [keyless]), for: two))
        #expect(Set(store.answer(for: [one, two]).models.map(\.name)) == ["small", "claude"])
        #expect(store.answer(for: [one]).models.map(\.name) == ["small"])
        #expect(store.answer(for: [UUID()]).models.isEmpty)
    }
}
