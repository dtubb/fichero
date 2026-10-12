import Foundation
@testable import Fichero
import Testing

/// #5652 slice 1: Project › Train › Train a Model… opens the project's Set Up on its Train page (the existing train
/// offers, no new flow), and a trained model's verb is one item in the menu bar, the Models node's row menu and the
/// Inspector. What breaks without these: Train a Model… landing on Ready (or the first page), a menu item that is on
/// when it can do nothing, or a second Make Available that drifts from the Inspector's.
@MainActor
@Suite("Project › Train and the Models node's verbs (#5652 slice 1)")
struct ProjectTrainMenuTests {
    private func model(livesOnlyHere: Bool, making: Bool = false) -> TrainedModelMenuTarget {
        TrainedModelMenuTarget(
            modelId: "m1", modelName: "Notebook reader", livesOnlyHere: livesOnlyHere, isMakingGlobal: making,
            makeGlobal: {}
        )
    }

    @Test("Train a Model… asks Set Up for its Train page; another stage still opens Ready; none, the first page")
    func setUpOpensOnTrain() {
        #expect(SetupStep.opening(requestedStage: SetupStep.trainStage) == .train)
        #expect(SetupStep.opening(requestedStage: "statements") == .ready)
        #expect(SetupStep.opening(requestedStage: nil) == nil)
        // The Train page is in every project's Set Up, so the press always lands on it.
        #expect(SetupStep.projectSteps(chosenStages: [], isNewProject: false).contains(.train))
    }

    @Test("with no project, Train a Model… is off and says why")
    func trainNeedsAProject() {
        #expect(FocusedTrainButtons.trainDisabledReason(hasProject: false) == "Open a project to train a model")
        #expect(FocusedTrainButtons.trainDisabledReason(hasProject: true) == nil)
    }

    @Test("Make Available in Every Project says why it cannot act")
    func makeGlobalReasons() {
        #expect(FocusedTrainButtons.makeGlobalDisabledReason(nil) == "Select a model in the Models node")
        #expect(FocusedTrainButtons.makeGlobalDisabledReason(model(livesOnlyHere: true)) == nil)
        #expect(
            FocusedTrainButtons.makeGlobalDisabledReason(model(livesOnlyHere: false))
                == "It is already available in every project"
        )
        #expect(
            FocusedTrainButtons.makeGlobalDisabledReason(model(livesOnlyHere: true, making: true))
                == "Making it available in every project…"
        )
    }

    @Test("the sidebar node reads Models and its type says so")
    func nodeIsModels() throws {
        #expect(SidebarModelsNode.name == "Models")
        let sections = try Self.appSource("Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift")
        #expect(sections.contains("SidebarModelsNode(store: library.trainedModelsStore"))
        #expect(!sections.contains("SidebarTrainingNode"))
    }

    @Test("the Project menu's Train section renders the focused buttons")
    func projectMenuHasTrain() throws {
        let menus = try Self.appSource("App/Menus/ReadKnowledgeMenuCommands.swift")
        #expect(menus.contains("case .train:\n            Section(stage.title) {\n                FocusedTrainButtons()"))
    }

    @Test("the menu bar, the Models node's row menu and the Inspector render the same items, through one store call")
    func oneComponentEverywhere() throws {
        let buttons = try Self.appSource("App/Menus/FocusedCommands/FocusedCommandButtons+Train.swift")
        #expect(buttons.contains("TrainModelMenuItem(projectId: target?.projectId)"))
        #expect(buttons.contains("MakeModelGlobalMenuItem(target: target?.trainedModel)"))
        #expect(buttons.contains("requestSetUp(for: projectId, stage: SetupStep.trainStage)"))
        #expect(buttons.contains("await store.makeAvailableEverywhere(modelId)"))
        #expect(!buttons.contains(".keyboardShortcut"), "Train's verbs take no chord")
        let node = try Self.appSource("Views/Sidebar/Sections/SidebarModelsNode.swift")
        #expect(node.contains(".contextMenu {\n                            TrainModelMenuItem(projectId: libraryId)"))
        #expect(node.contains("MakeModelGlobalMenuItem(target: target)"))
        let inspector = try Self.appSource("Views/Inspector/Model/ModelNodeInspector.swift")
        #expect(inspector.contains("MakeModelGlobalMenuItem(target: makeGlobal)"))
        #expect(inspector.contains("makeGlobal: TrainedModelMenuTarget.make(modelId: modelId, store: store)"))
        #expect(!inspector.contains("store.makeGlobal("))
        let publisher = try Self.appSource("App/Menus/FocusedCommands/FocusedCommandButtons+Recipe.swift")
        #expect(publisher.contains("trainedModel: selectedTrainedModelTarget"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }
}
