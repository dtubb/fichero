import FicheroAPIClient
import SwiftUI

// `sidebar.project.click-selects-and-inspects` (#5422): a project row in the sidebar is a
// selection like any other row, and the Inspector shows the project itself. Composed from
// what already exists: the saved recipe and its steps (`RecipeSetupStore`, `RecipeStepsView`),
// Set Up… (`LibraryManager.requestSetUp`), the sharing badge and sheet the project row uses,
// and the engine's own counts (`GET /api/stats`).

extension SidebarSelectionState {
    /// The project the Inspector shows: the sidebar's routed selection is a project row and
    /// nothing in the Library pane has been picked since (a pick there is the newer selection,
    /// and the Inspector follows it, as it follows a folder row).
    func inspectedProjectId(browserSelection: Set<String>) -> UUID? {
        guard browserSelection.isEmpty, case .library(let libraryId)? = selectedDestination else { return nil }
        return libraryId
    }
}

struct ProjectInspector: View {
    let library: LibraryManager.LibraryReference

    @Environment(LibraryManager.self) private var libraryManager
    @Environment(AppState.self) private var appState

    @State private var recipeStore: RecipeSetupStore?
    @State private var stats: Components.Schemas.LibraryStatsResponse?
    @State private var statsError: String?
    @State private var showShareSheet = false

    var body: some View {
        Form {
            Section {
                LabeledContent("Name", value: library.displayName)
                LabeledContent("Location") {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(library.url.path)
                            .textSelection(.enabled)
                            .lineLimit(2)
                            .truncationMode(.middle)
                        Text(library.locationDescriptor.label)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            Section("Contents") {
                if let stats {
                    LabeledContent("Documents", value: "\(stats.documents)")
                    LabeledContent("Artifacts", value: "\(stats.artifacts)")
                } else if let statsError {
                    Text(statsError).foregroundStyle(.secondary)
                } else {
                    ProgressView().controlSize(.small)
                }
            }
            Section("Recipe") {
                if let recipeStore, let recipe = recipeStore.recipe {
                    RecipeStepsView(store: recipeStore, recipe: recipe, bakeoff: .init(project: library))
                } else if let message = recipeStore?.errorMessage {
                    Text(message).foregroundStyle(.secondary)
                } else if recipeStore != nil {
                    Text("This project is not set up yet.").foregroundStyle(.secondary)
                }
                if let recipeStore, recipeStore.recipe != nil {
                    InspectorProjectLayers(store: recipeStore)
                }
                Button("Set Up…") { libraryManager.requestSetUp(for: library.id) }
            }
            KeptExportsInspectorSection(store: library.keptExportStore)
            Section("Sharing") {
                if EngineConfig.multiuserEnabled {
                    HStack {
                        LibrarySharingBadge(library: library)
                        Spacer()
                        Button("Share…") { showShareSheet = true }
                    }
                } else {
                    Text("Sharing is off.").foregroundStyle(.secondary)
                }
            }
        }
        .formStyle(.grouped)
        .sheet(isPresented: $showShareSheet) {
            ShareLibrarySheet(library: library, usersStore: appState.usersStore)
        }
        .task(id: library.id) {
            await load()
        }
    }

    private func load() async {
        recipeStore = nil
        stats = nil
        statsError = nil
        let store = RecipeSetupStore(client: library.ficheroClient, topics: library.topicStore)
        await store.loadSaved()
        await store.loadJobs()
        guard !Task.isCancelled else { return }
        recipeStore = store
        do {
            if case .ok(let success) = try await library.ficheroClient.api.getStatsApiStatsGet() {
                stats = try success.body.json
            } else {
                statsError = "Could not read this project's counts."
            }
        } catch {
            if error.isCancellationError { return }
            statsError = "Could not read this project's counts: \(error.localizedDescription)"
        }
    }
}

#Preview("Project inspector") {
    LibraryPreviewFixtures.environment(ProjectInspector(library: LibraryPreviewFixtures.library))
        .frame(width: 320, height: 520)
}
