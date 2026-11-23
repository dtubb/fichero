@testable import Fichero
import Foundation
import Testing

/// `models.window.is-activitys-shape` (#6588): the Models & Cluster window is a `Window` scene the owner opens by id from the
/// Window menu, its sidebar sections and badges come from `ModelsWindowModel`, and a row needing you is listed first.
struct ModelsWindowSceneTests {
    private static func source(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private let broken = ActivityModelEntry(id: "this-mac|MLX|chandra", name: "chandra", place: .thisMac, provider: "MLX",
                                            lastFailed: .init(words: "Model failed to load", kind: "model-broken", button: "retry"))
    private let idle = ActivityModelEntry(id: "this-mac|MLX|small", name: "small", place: .thisMac, provider: "MLX")
    private let keyless = ActivityModelEntry(id: "cloud|Anthropic|claude", name: "claude", place: .cloud,
                                             provider: "Anthropic", account: .needsKey)

    @Test("the window is one `Window` scene with a stable id, titled Models & Cluster, and the Window menu lists it")
    func sceneExistsAndOpensByID() throws {
        #expect(ModelsWindowModel.windowID == "models-cluster")
        #expect(ModelsWindowModel.windowTitle == "Models & Cluster")
        let app = try Self.source("FicheroApp.swift")
        #expect(app.contains("ModelsWindowScene(appState:"))
        let scene = try Self.source("Views/Activity/Window/ModelsWindowScene.swift")
        #expect(scene.contains("Window(\"Models & Cluster\", id: ModelsWindowModel.windowID)"))
        #expect(!scene.contains("WindowGroup"))
        #expect(!app.contains("id: ModelsWindowModel.windowID"), "one scene claims the id")
        #expect(try Self.source("Views/Activity/Window/ModelsWindow.swift").contains("ModelsPaneView("))
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
        #expect(sidebar.map(\.section) == [.thisMac, .places, .work])
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

    @Test("the window draws the sidebar and rows from the model and the one list through the generated client")
    func viewReadsTheModel() throws {
        let pane = try Self.source("Views/Activity/Pane/ModelsPaneView.swift")
        #expect(pane.contains("ModelsWindowModel.sidebar("))
        #expect(pane.contains("ModelsWindowModel.rows("))
        #expect(pane.contains("ModelsWindowModel.inspectorLines("))
        #expect(pane.contains("activityService.models()"))
        #expect(!pane.contains("URLSession"))
    }
}
