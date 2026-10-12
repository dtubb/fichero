import FicheroAPIClient
import SwiftUI

/// A project's Models node (#5439, `source.model.node-in-sidebar`; ruled 2026-10-04, named Models
/// 2026-10-10, `training.model.node-under-models`; the type renamed to match, #5652):
/// training is the sidebar node, and every model Fichero trained or fine-tuned shows inside it.
/// A model downloaded or imported is not here; it lives in Settings. The node draws nothing
/// while there is no trained model (#5413: a row appears only when non-empty).
///
/// Each model row is tagged with its `SidebarDestination`, so the list's own selection routes
/// it (`handleSelectionDestination`) and the Inspector shows it (`ModelNodeInspector`).
struct SidebarModelsNode: View {
    /// The node's name in the sidebar and to VoiceOver (ruled 2026-10-10: Models, not Training).
    nonisolated static let name = "Models"

    let store: TrainedModelsStore
    let libraryId: UUID
    var selection: Set<SidebarDestination> = []

    @State private var isExpanded = true

    var body: some View {
        if store.showsModelsNode {
            DisclosureGroup(isExpanded: $isExpanded) {
                ForEach(store.models, id: \.id) { model in
                    let destination = SidebarDestination.trainedModel(model.id, libraryId: libraryId)
                    Label(model.name, systemImage: "brain")
                        .help(ModelNodeFacts.kindName(model.kind))
                        .sidebarDropHighlight(false, selected: selection.contains(destination))
                        .tag(destination)
                        .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
                        // The model's verbs: the same items Project › Train renders (#5652 slice 1).
                        .contextMenu {
                            TrainModelMenuItem(projectId: libraryId)
                            if let target = TrainedModelMenuTarget.make(modelId: model.id, store: store),
                               target.livesOnlyHere {
                                MakeModelGlobalMenuItem(target: target)
                            }
                        }
                }
            } label: {
                Label(Self.name, systemImage: "graduationcap")
            }
            .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
        }
    }
}

#Preview("Models node with two trained models") {
    let store = TrainedModelPreviewFixtures.store(client: LibraryPreviewFixtures.library.ficheroClient)
    return List {
        SidebarModelsNode(store: store, libraryId: LibraryPreviewFixtures.library.id)
    }
    .listStyle(.sidebar)
    .frame(width: 260, height: 220)
}
