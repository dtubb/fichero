import FicheroAPIClient
import SwiftUI

/// A project's Training node (#5439, `source.model.node-in-sidebar`; ruled 2026-10-04):
/// training is the sidebar node, and every model Fichero trained or fine-tuned shows inside it.
/// A model downloaded or imported is not here; it lives in Settings. The node draws nothing
/// while there is no trained model (#5413: a row appears only when non-empty).
///
/// Each model row is tagged with its `SidebarDestination`, so the list's own selection routes
/// it (`handleSelectionDestination`) and the Inspector shows it (`ModelNodeInspector`).
struct SidebarTrainingNode: View {
    let store: TrainedModelsStore
    let libraryId: UUID

    @State private var isExpanded = true

    var body: some View {
        if store.showsTrainingNode {
            DisclosureGroup(isExpanded: $isExpanded) {
                ForEach(store.models, id: \.id) { model in
                    Label(model.name, systemImage: "brain")
                        .help(ModelNodeFacts.kindName(model.kind))
                        .tag(SidebarDestination.trainedModel(model.id, libraryId: libraryId))
                        .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
                }
            } label: {
                Label("Training", systemImage: "graduationcap")
            }
            .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
        }
    }
}

#Preview("Training node with two trained models") {
    let store = TrainedModelPreviewFixtures.store(client: LibraryPreviewFixtures.library.ficheroClient)
    return List {
        SidebarTrainingNode(store: store, libraryId: LibraryPreviewFixtures.library.id)
    }
    .listStyle(.sidebar)
    .frame(width: 260, height: 220)
}
