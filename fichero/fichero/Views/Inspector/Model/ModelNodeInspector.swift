import FicheroAPIClient
import SwiftUI

// `source.model.node-inspector` (#5439): selecting a model inside a project's Training node
// shows its Inspector, read from its card through `TrainedModelsStore`. Read-only for now:
// training again, testing and publishing are the node's actions (`source.model.node-actions`).

extension SidebarSelectionState {
    /// The trained model the Inspector shows: the sidebar's routed selection is a model row in
    /// a Training node and nothing in the Library pane has been picked since (a pick there is
    /// the newer selection, as for a project row).
    func inspectedTrainedModel(browserSelection: Set<String>) -> (modelId: String, libraryId: UUID)? {
        guard browserSelection.isEmpty,
              case .trainedModel(let modelId, let libraryId)? = selectedDestination else { return nil }
        return (modelId, libraryId)
    }
}

struct ModelNodeInspector: View {
    let store: TrainedModelsStore
    let modelId: String

    var body: some View {
        Group {
            if let model = store.inspected[modelId] {
                ModelNodeInspectorForm(facts: ModelNodeFacts(model))
            } else if let message = store.inspectErrors[modelId] {
                ContentUnavailableView(
                    "Model Not Available", systemImage: "brain", description: Text(message)
                )
            } else {
                ProgressView().controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task(id: modelId) {
            await store.loadModel(modelId)
        }
    }
}

/// The Inspector's sections, from one model's worded facts.
struct ModelNodeInspectorForm: View {
    let facts: ModelNodeFacts

    var body: some View {
        Form {
            Section {
                LabeledContent("Name", value: facts.name)
                LabeledContent("Kind", value: facts.kind)
                if let summary = facts.summary {
                    Text(summary).foregroundStyle(.secondary)
                }
            }
            Section("Where It Came From") {
                LabeledContent("Base", value: facts.base)
                LabeledContent("Teacher", value: facts.teacher)
                ForEach(facts.trainingSet, id: \.label) { count in
                    LabeledContent(count.label, value: count.value)
                }
                LabeledContent("Trained", value: facts.trainedWhen)
                LabeledContent("Trained On", value: facts.trainedWhere)
                LabeledContent("Job", value: facts.job)
            }
            Section("Held-Out Scores (CER)") {
                if let scores = facts.scores {
                    ForEach(scores, id: \.policy) { score in
                        LabeledContent(score.policy, value: score.cer)
                    }
                    if let measured = facts.scoresMeasured {
                        Text(measured).font(.caption).foregroundStyle(.secondary)
                    }
                } else {
                    Text(ModelNodeFacts.notEvaluated).foregroundStyle(.secondary)
                }
            }
            Section("Size and Where It Runs") {
                LabeledContent("Size", value: facts.size)
                ForEach(facts.runsOn, id: \.self) { place in
                    Text(place)
                }
            }
            Section("Licence and Release") {
                LabeledContent("Licence", value: facts.licence)
                if let note = facts.licenceNote {
                    Text(note).font(.caption).foregroundStyle(.secondary)
                }
                Label(
                    facts.publish,
                    systemImage: facts.mayPublish ? "checkmark.circle" : "lock"
                )
                .foregroundStyle(facts.mayPublish ? .primary : .secondary)
            }
        }
        .formStyle(.grouped)
    }
}

#Preview("Model inspector: evaluated, may be published") {
    let store = TrainedModelPreviewFixtures.store(client: LibraryPreviewFixtures.library.ficheroClient)
    return ModelNodeInspector(store: store, modelId: TrainedModelPreviewFixtures.studentId)
        .frame(width: 320, height: 640)
}

#Preview("Model inspector: not evaluated, not for release") {
    let store = TrainedModelPreviewFixtures.store(client: LibraryPreviewFixtures.library.ficheroClient)
    return ModelNodeInspector(store: store, modelId: TrainedModelPreviewFixtures.readerId)
        .frame(width: 320, height: 640)
}
