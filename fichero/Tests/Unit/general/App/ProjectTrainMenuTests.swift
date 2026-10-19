import FicheroAPIClient
import Foundation
@testable import Fichero
import Testing

/// #5652 slice 1: Project › Train › Train a Model… opens the project's Set Up on its Train page (the existing train
/// offers, no new flow), and a trained model's verb is one item in the menu bar, the Models node's row menu and the
/// Inspector. What breaks without these: Train a Model… landing on Ready (or the first page), a menu item that is on
/// when it can do nothing, or a target made for a model the store does not list. The press of Make Available through
/// the target is `TrainedModelNodeActionsTests.makeAvailableThroughTheSharedTarget`, over a stubbed engine.
@MainActor
@Suite("Project › Train and the Models node's verbs (#5652 slice 1)")
struct ProjectTrainMenuTests {
    private func model(livesOnlyHere: Bool, making: Bool = false) -> TrainedModelMenuTarget {
        TrainedModelMenuTarget(
            modelId: "m1", modelName: "Notebook reader", livesOnlyHere: livesOnlyHere, isMakingGlobal: making,
            makeGlobal: {}
        )
    }

    @Test("Train a Model… asks Set Up, which opens Ready (where the plan offers training); none, the first page")
    func setUpOpensOnTrain() {
        #expect(SetupStep.opening(requestedStage: SetupStep.trainStage) == .ready)
        #expect(SetupStep.opening(requestedStage: "statements") == .ready)
        #expect(SetupStep.opening(requestedStage: nil) == nil)
        // Training is not a Set Up step (#5804): Set Up never lists a Train page.
        #expect(!SetupStep.projectSteps(chosenStages: [], isNewProject: false).map { $0.title() }.contains("Train"))
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

    @Test("the sidebar node reads Models")
    func nodeIsModels() {
        #expect(SidebarModelsNode.name == "Models")
    }

    @Test("Train a Model… asks Set Up for the project's Train page, and does nothing without a project")
    func trainAsksSetUpForTrain() {
        var asked: [(UUID, String?)] = []
        let project = UUID()
        TrainModelMenuItem.run(projectId: project) { asked.append(($0, $1)) }
        TrainModelMenuItem.run(projectId: nil) { asked.append(($0, $1)) }
        #expect(asked.count == 1)
        #expect(asked.first?.0 == project)
        #expect(asked.first?.1 == SetupStep.trainStage)
        #expect(SetupStep.opening(requestedStage: asked.first?.1) == .ready)
        #expect(TrainModelMenuItem.title == "Train a Model…")
        #expect(MakeModelGlobalMenuItem.title == "Make Available in Every Project")
    }

    @Test("a model's target is made from the store's own entry, and only for a model it lists")
    func targetFromTheStore() throws {
        let json = """
        [{"id":"m1","name":"Notebook reader","kind":"kraken-reader","may_publish":false,"lives":"project"},
         {"id":"m2","name":"Student","kind":"vision-lora","may_publish":true,"lives":"both"}]
        """
        let models = try JSONDecoder().decode([Components.Schemas.TrainedModelNode].self, from: Data(json.utf8))
        let store = TrainedModelsStore(client: FicheroClient(libraryPath: nil), models: models)
        let here = try #require(TrainedModelMenuTarget.make(modelId: "m1", store: store))
        #expect(here.modelName == "Notebook reader" && here.livesOnlyHere && !here.isMakingGlobal)
        #expect(FocusedTrainButtons.makeGlobalDisabledReason(here) == nil)
        let everywhere = try #require(TrainedModelMenuTarget.make(modelId: "m2", store: store))
        #expect(FocusedTrainButtons.makeGlobalDisabledReason(everywhere) == "It is already available in every project")
        #expect(TrainedModelMenuTarget.make(modelId: "unknown", store: store) == nil)
    }
}
