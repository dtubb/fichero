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

    // Optional (#4703): the Inspector is a boundary that does not inherit the window's environment, where a
    // non-optional read traps. Set Up… falls back to the one LibraryManager; sharing needs the app's state.
    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    // @AppStorage, not a plain defaults read, so the host mark follows the Sharing switch live.
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) private var hostingEnabled = false
    @Environment(AppState.self) private var appState: AppState?

    @State private var recipeStore: RecipeSetupStore?
    @State private var stats: Components.Schemas.LibraryStatsResponse?
    @State private var statsError: String?
    @State private var showShareSheet = false
    @State private var pairedDevices: [PairedDeviceRecord] = []
    @State private var devicesError: String?

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
                Button("Set Up…") { (libraryManager ?? LibraryManager.shared).requestSetUp(for: library.id) }
            }
            // The model finder (#5611, `source.find.app-finder-three-hosts`): readers for the
            // project's scripts and languages, read only when opened.
            if let recipeStore {
                Section("Readers") {
                    DisclosureGroup("Find a Reader") {
                        ProjectModelFinder(library: library, setup: recipeStore)
                    }
                }
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
                if showsHostMark {
                    Label(SharedMark.hostHelp, systemImage: SharedMark.symbol)
                        .foregroundStyle(.secondary)
                    PairedDevicesSectionView(
                        devices: activePairedDevices(from: pairedDevices),
                        isLoading: false,
                        canHostRemoteAccess: EngineConfig.engineIsLocal,
                        onRefresh: { Task { await loadDevices() } },
                        onRevoke: { id in Task { await revokeDevice(id) } }
                    )
                    if let devicesError {
                        Text(devicesError).font(.caption).foregroundStyle(.orange)
                    }
                }
            }
        }
        .formStyle(.grouped)
        .sheet(isPresented: $showShareSheet) {
            if let appState {
                ShareLibrarySheet(library: library, usersStore: appState.usersStore)
            }
        }
        .task(id: library.id) {
            await loadDevices()
            await load()
        }
    }

    private var showsHostMark: Bool {
        SharedMark.showsOnHost(hostingEnabled: hostingEnabled, isLocal: library.host.isLocal)
    }

    /// The devices paired with this Mac, listed while Sharing is on (`sharing.sidebar.host-mark`).
    private func loadDevices() async {
        guard showsHostMark, EngineConfig.engineIsLocal else { return }
        do {
            pairedDevices = try await PairingService(apiRoot: EngineConfig.host).listDevices()
            devicesError = nil
        } catch {
            if error.isCancellationError { return }
            devicesError = error.localizedDescription
        }
    }

    private func revokeDevice(_ id: String) async {
        do {
            try await PairingService(apiRoot: EngineConfig.host).revokeDevice(id: id)
            await loadDevices()
        } catch {
            devicesError = error.localizedDescription
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
