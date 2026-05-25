import SwiftUI

// MARK: - AI Settings

/// Settings for default AI models with Defaults and Advanced sub-tabs
struct AISettingsView: View {
    @EnvironmentObject var appState: AppState
    @ObservedObject var featureManager = FeatureManager.shared

    @State var defaults = AIDefaults()
    @State var isLoading = true
    @State var isSaving = false
    @State var errorMessage: String?
    @State private var selectedTab = 0

    // Model lists per category
    @State var textModels: [ModelInfo] = []
    @State var visionModels: [ModelInfo] = []
    @State var audioModels: [ModelInfo] = []
    @State var videoModels: [ModelInfo] = []
    @State var embeddingsModels: [ModelInfo] = []
    // Capability-tier model lists ($small / $large aliases — #810/#813).
    @State var smallModels: [ModelInfo] = []
    @State var largeModels: [ModelInfo] = []

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
                if featureManager.isSettingsAIAdvancedTabEnabled {
                    Picker("", selection: $selectedTab) {
                        Text("Defaults").tag(0)
                        Text("Advanced").tag(1)
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal)
                    .padding(.top, 8)
                }

                if !featureManager.isSettingsAIAdvancedTabEnabled || selectedTab == 0 {
                    defaultsTab
                } else {
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
