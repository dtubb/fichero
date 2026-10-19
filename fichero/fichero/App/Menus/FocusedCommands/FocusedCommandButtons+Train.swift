import SwiftUI

// MARK: - Project › Train (#5652 slice 1, `menus.context-matches-bar`)

// Train a Model… opens the project's Set Up on Ready (training is not a step, #5804; the Start plan's train offers,
// `RecipeTrainOffersFields`); no new flow. A trained model's verb, Make Available in Every Project, is ONE item that
// Project › Train, the Models node's row menu and the model's Inspector all render, on the one target `make(…)`
// builds over `TrainedModelsStore.makeAvailableEverywhere`.

/// One trained model, as its verbs see it: Equatable on what they show, never on the closure.
struct TrainedModelMenuTarget: Equatable {
    let modelId: String
    let modelName: String
    /// It lives only in this project, so it can still be made available in every project.
    let livesOnlyHere: Bool
    /// Make Available in Every Project is under way for it.
    let isMakingGlobal: Bool
    let makeGlobal: @MainActor () -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.modelId == rhs.modelId && lhs.modelName == rhs.modelName
            && lhs.livesOnlyHere == rhs.livesOnlyHere && lhs.isMakingGlobal == rhs.isMakingGlobal
    }

    /// The one way a model's target is made; nil when the store does not list it.
    @MainActor static func make(modelId: String, store: TrainedModelsStore) -> Self? {
        guard let model = store.models.first(where: { $0.id == modelId }) else { return nil }
        return Self(
            modelId: modelId, modelName: model.name,
            livesOnlyHere: store.livesOnlyHere(modelId),
            isMakingGlobal: store.makingGlobal.contains(modelId),
            makeGlobal: { Task { await store.makeAvailableEverywhere(modelId) } }
        )
    }
}

/// Train a Model…, as ONE item: Project › Train and the Models node's row menu. Opens Set Up on its Train page for
/// the project.
struct TrainModelMenuItem: View {
    let projectId: UUID?

    var body: some View {
        Button {
            Self.run(projectId: projectId, requestSetUp: LibraryManager.shared.requestSetUp(for:stage:))
        } label: {
            Label(Self.title, systemImage: "graduationcap")
        }
        .disabled(projectId == nil)
    }

    static let title = "Train a Model…"

    /// The press: ask Set Up for the project's Train page; nothing without a project.
    static func run(projectId: UUID?, requestSetUp: (UUID, String?) -> Void) {
        guard let projectId else { return }
        requestSetUp(projectId, SetupStep.trainStage)
    }
}

/// Make Available in Every Project, as ONE item: Project › Train, the Models node's row menu and the Inspector.
struct MakeModelGlobalMenuItem: View {
    let target: TrainedModelMenuTarget?

    var body: some View {
        Button {
            target?.makeGlobal()
        } label: {
            Label(Self.title, systemImage: "square.and.arrow.up.on.square")
        }
        .disabled(FocusedTrainButtons.makeGlobalDisabledReason(target) != nil)
    }

    static let title = "Make Available in Every Project"
}

/// Project › Train: Train a Model… for the key window's project, and Make Available in Every Project for the model
/// selected in its Models node. Each is disabled with its reason under it (the Segment menu's pattern). No chords:
/// neither is a muscle-memory verb.
struct FocusedTrainButtons: View {
    @FocusedValue(\.projectMenu) private var target

    var body: some View {
        TrainModelMenuItem(projectId: target?.projectId)
        if let reason = Self.trainDisabledReason(hasProject: target != nil) {
            Text(reason)
        }
        MakeModelGlobalMenuItem(target: target?.trainedModel)
        // With no project, the one reason under Train a Model… says so for both.
        if target != nil, let reason = Self.makeGlobalDisabledReason(target?.trainedModel) {
            Text(reason)
        }
    }

    /// Why Train a Model… cannot act, or nil when it can.
    static func trainDisabledReason(hasProject: Bool) -> String? {
        hasProject ? nil : "Open a project to train a model"
    }

    /// Why Make Available in Every Project cannot act, or nil when it can.
    static func makeGlobalDisabledReason(_ target: TrainedModelMenuTarget?) -> String? {
        guard let target else { return "Select a model in the Models node" }
        if target.isMakingGlobal { return "Making it available in every project…" }
        return target.livesOnlyHere ? nil : "It is already available in every project"
    }
}
