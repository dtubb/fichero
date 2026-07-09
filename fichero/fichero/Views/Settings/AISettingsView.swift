import SwiftUI

// MARK: - AI Settings

/// Settings for AI providers, defaults, and local model downloads.
struct AISettingsView: View {
    @Environment(AppState.self) var appState
    @ObservedObject var featureManager = FeatureManager.shared

    @State var defaults = AIDefaults()
    @State var isLoading = true
    @State var isSaving = false
    @State var errorMessage: String?
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
            } else if isLoading {
                Form {
                    Section {
                        ProgressView("Loading defaults...")
                    }
                }
                .formStyle(.grouped)
            } else {
                Picker("", selection: $selectedTab) {
                    Text("Defaults").tag(AISettingsTab.defaults)
                    Text("Models & Providers").tag(AISettingsTab.providers)
                    Text("Downloads").tag(AISettingsTab.downloads)
                    Text("Local LLM").tag(AISettingsTab.localLLM)
                    Text("Advanced").tag(AISettingsTab.advanced)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.top, 8)

                switch selectedTab {
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

            if let error = errorMessage {
                Text(error)
                    .foregroundStyle(.red)
                    .font(.caption)
                    .padding(.horizontal)
                    .padding(.bottom, 4)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadDefaults()
        }
        .onChange(of: defaults) {
            Task {
                await saveDefaults()
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
