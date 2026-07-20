import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - AI Settings

/// Settings for AI providers, defaults, and local model downloads.
///
/// The AI defaults (the persisted settings) live in an `@Observable`
/// `AISettingsStore` this view OBSERVES — the view no longer owns that state or
/// calls the endpoints itself (#3222 / observable-data-layer rule). The per-tier
/// model-picker lists below are transient UI population derived from
/// `store.defaults`; moving those into the store is a follow-up.
struct AISettingsView: View {
    @Environment(AppState.self) var appState
    let featureManager = FeatureManager.shared

    @State var store = AISettingsStore()
    @State private var selectedTab = AISettingsTab.defaults

    // Model lists per category
    @State var textModels: [ModelInfo] = []
    @State var visionModels: [ModelInfo] = []
    @State var audioModels: [ModelInfo] = []
    @State var videoModels: [ModelInfo] = []
    @State var embeddingsModels: [ModelInfo] = []
    // Capability-tier model lists ($small / $medium / $large aliases — #810/#813).
    @State var smallModels: [ModelInfo] = []
    @State var mediumModels: [ModelInfo] = []
    @State var largeModels: [ModelInfo] = []
    @State var visionSmallModels: [ModelInfo] = []
    @State var visionMediumModels: [ModelInfo] = []
    @State var visionLargeModels: [ModelInfo] = []

    private var showsModelManagementTabs: Bool {
        featureManager.isSettingsModelsTabEnabled
    }

    private var effectiveSelectedTab: AISettingsTab {
        guard showsModelManagementTabs else {
            switch selectedTab {
            case .defaults, .advanced:
                return selectedTab
            case .providers, .downloads, .localLLM:
                return .defaults
            }
        }
        return selectedTab
    }

    var body: some View {
        VStack(spacing: 0) {
            if !appState.isBackendRunning {
                Form {
                    Section {
                        Label("Backend not connected", systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.secondary)
                    }
                }
                .formStyle(.grouped)
            } else if store.isLoading {
                Form {
                    Section {
                        ProgressView("Loading defaults...")
                    }
                }
                .formStyle(.grouped)
            } else {
                Picker("", selection: $selectedTab) {
                    Text("Defaults").tag(AISettingsTab.defaults)
                    if showsModelManagementTabs {
                        Text("Models & Providers").tag(AISettingsTab.providers)
                        Text("Downloads").tag(AISettingsTab.downloads)
                        Text("Local LLM").tag(AISettingsTab.localLLM)
                    }
                    Text("Advanced").tag(AISettingsTab.advanced)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.top, 8)

                switch effectiveSelectedTab {
                case .defaults:
                    defaultsTab
                case .providers:
                    providersTab
                case .downloads:
                    downloadsTab
                case .localLLM:
                    localLLMTab
                case .advanced:
                    advancedTab
                }
            }

            if let error = store.errorMessage {
                Text(error)
                    .foregroundStyle(.red)
                    .font(.caption)
                    .padding(.horizontal)
                    .padding(.bottom, 4)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            store.attach(appState)
            await store.load()
            await loadModelLists()
        }
        .onChange(of: showsModelManagementTabs, initial: true) { _, isVisible in
            if !isVisible {
                selectedTab = effectiveSelectedTab
            }
        }
        .onChange(of: store.defaults) {
            Task {
                await store.save()
            }
        }
    }
}

enum AISettingsTab: Hashable {
    case defaults
    case providers
    case downloads
    case localLLM
    case advanced
}

// MARK: - AI Settings Store (#3222)

/// The endpoints the AI-settings store needs. A protocol seam so the store is the
/// only endpoint accessor (observable-data-layer rule) AND so its error-surfacing
/// paths are testable with a fake that throws. `AppState` already implements every
/// member, so it conforms retroactively.
@MainActor
protocol AIDefaultsProviding: AnyObject {
    var providers: [Components.Schemas.ProviderResponse] { get }
    func loadProviders() async
    func fetchAIDefaults() async throws -> AIDefaults
    func saveAIDefaults(_ defaults: AIDefaults) async throws
    func resetAIDefaults() async throws
}

extension AppState: AIDefaultsProviding {}

/// Observable store for the AI defaults settings (#3222). Owns the persisted
/// `defaults`, the load/save/reset lifecycle, and — crucially — surfaces every
/// failure as `errorMessage` instead of swallowing it. The first-launch
/// Apple-Intelligence seed is persisted here too; a save failure there is reported,
/// never shown as if it saved (the exact silent `try?` #3222 removed).
@MainActor
@Observable
final class AISettingsStore {
    /// The persisted defaults. Mutable so the pickers bind to it; a change triggers
    /// `save()` from the view's `onChange`.
    var defaults = AIDefaults()
    private(set) var isLoading = true
    private(set) var isSaving = false
    private(set) var errorMessage: String?

    private var endpoint: (any AIDefaultsProviding)?
    private let log = Logger(subsystem: "app.fichero.fichero", category: "AISettings")

    /// Bind the store to its endpoint accessor. Called from the view's `.task`
    /// because `@Environment` isn't available at `@State` init.
    func attach(_ endpoint: any AIDefaultsProviding) {
        self.endpoint = endpoint
    }

    func load() async {
        guard let endpoint else { return }
        isLoading = true
        defer { isLoading = false }

        await endpoint.loadProviders()

        do {
            var loaded = try await endpoint.fetchAIDefaults()
            let appleAvailable = endpoint.providers.contains { $0.providerType == "apple" }
            let beforeSeed = loaded
            loaded.seedAppleDefaultsIfNeeded(appleAvailable: appleAvailable)
            defaults = loaded

            if loaded != beforeSeed {
                // Persist the seeded defaults; surface a failure instead of showing
                // values that silently evaporate on next launch (#3222 /
                // prefer-raise-over-silent-fallback). Never a silent `try?`.
                do {
                    try await endpoint.saveAIDefaults(loaded)
                    errorMessage = nil
                } catch {
                    log.error("Failed to persist seeded Apple defaults: \(error.localizedDescription)")
                    errorMessage = "Couldn't save the default AI models: \(error.localizedDescription)"
                }
            } else {
                errorMessage = nil
            }
        } catch {
            log.error("Failed to load AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to load: \(error.localizedDescription)"
        }
    }

    func save() async {
        guard let endpoint, !isLoading else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            try await endpoint.saveAIDefaults(defaults)
            errorMessage = nil
        } catch {
            log.error("Failed to save AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to save: \(error.localizedDescription)"
        }
    }

    func reset() async {
        guard let endpoint else { return }
        do {
            try await endpoint.resetAIDefaults()
            defaults = AIDefaults()
            errorMessage = nil
        } catch {
            log.error("Failed to reset AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to reset: \(error.localizedDescription)"
        }
    }
}
