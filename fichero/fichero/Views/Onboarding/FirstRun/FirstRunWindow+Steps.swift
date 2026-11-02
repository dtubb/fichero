import SwiftUI

extension FirstRunWindow {
    /// The pages each way in starts with (`source.onboard.project.one-view`). Pure, for the tests.
    static func flow(for mode: Mode, isCompanionPlatform: Bool = SetupFlow.runsOnCompanionPlatform) -> SetupFlow {
        switch mode {
        case .firstRun: SetupFlow(includesApp: true, project: .none, isCompanionPlatform: isCompanionPlatform)
        case .newProject: SetupFlow(includesApp: false, project: .new)
        case .setUp: SetupFlow(includesApp: false, project: .existing)
        }
    }

    /// The pages, with one per stage chosen so far, and the stage page the person is on even if they just unticked it.
    var steps: [SetupStep] {
        var current = flow
        let onStage: String? = if case .stage(let id) = step { id } else { nil }
        current.chosenStages = store?.stageIds(keeping: onStage) ?? []
        current.includesHow = FeatureManager.shared.isWideSetUpEnabled
        return current.steps
    }
}
