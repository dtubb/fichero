import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "Settings")

// MARK: - AI Defaults Model

/// Default AI model configuration per category.
/// Matches the Python AIDefaults Pydantic model.
struct AIDefaults: Codable, Equatable {
    var visionProvider: String = ""
    var visionModel: String = ""
    var textProvider: String = ""
    var textModel: String = ""
    var audioProvider: String = ""
    var audioModel: String = ""
    var videoProvider: String = ""
    var videoModel: String = ""
    var temperature: String = ""
    var maxTokens: String = ""
    var promptPrefix: String = ""
    var embeddingsModel: String = ""

    enum CodingKeys: String, CodingKey {
        case visionProvider = "vision_provider"
        case visionModel = "vision_model"
        case textProvider = "text_provider"
        case textModel = "text_model"
        case audioProvider = "audio_provider"
        case audioModel = "audio_model"
        case videoProvider = "video_provider"
        case videoModel = "video_model"
        case temperature
        case maxTokens = "max_tokens"
        case promptPrefix = "prompt_prefix"
        case embeddingsModel = "embeddings_model"
    }
}

// MARK: - Settings View

/// Main settings view with tabs for General, AI, Backend, and Models
struct SettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        TabView {
            GeneralSettingsView()
                .tabItem {
                    Label("General", systemImage: "gear")
                }

            AISettingsView()
                .tabItem {
                    Label("AI", systemImage: "brain")
                }

            BackendSettingsView()
                .tabItem {
                    Label("Backend", systemImage: "server.rack")
                }

            LocalModelsSettingsView()
                .tabItem {
                    Label("Models", systemImage: "arrow.down.circle")
                }
        }
        .frame(width: 550, height: 450)
    }
}

// MARK: - AI Settings

/// Settings for default AI models with Defaults and Advanced sub-tabs
struct AISettingsView: View {
    @EnvironmentObject var appState: AppState

    @State private var defaults = AIDefaults()
    @State private var isLoading = true
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var selectedTab = 0

    // Model lists per category
    @State private var textModels: [ModelInfo] = []
    @State private var visionModels: [ModelInfo] = []
    @State private var audioModels: [ModelInfo] = []
    @State private var videoModels: [ModelInfo] = []

    var body: some View {
        VStack(spacing: 0) {
            if !appState.isBackendRunning {
                Form {
                    Section {
                        Label("Backend not connected", systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.secondary)
                    }
                }
                .padding()
            } else if isLoading {
                Form {
                    Section {
                        ProgressView("Loading defaults...")
                    }
                }
                .padding()
            } else {
                Picker("", selection: $selectedTab) {
                    Text("Defaults").tag(0)
                    Text("Advanced").tag(1)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.top, 8)

                if selectedTab == 0 {
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

    // MARK: - Defaults Tab

    @ViewBuilder
    private var defaultsTab: some View {
        Form {
            Section("Text (Summarize, Extract, Classify)") {
                providerPicker(selection: $defaults.textProvider)
                modelPicker(selection: $defaults.textModel, models: textModels)
            }

            Section("Vision (Describe, Analyze)") {
                providerPicker(selection: $defaults.visionProvider)
                modelPicker(selection: $defaults.visionModel, models: visionModels)
            }

            Section("Audio (Transcription)") {
                providerPicker(selection: $defaults.audioProvider)
                modelPicker(selection: $defaults.audioModel, models: audioModels)
            }

            Section("Video") {
                providerPicker(selection: $defaults.videoProvider)
                modelPicker(selection: $defaults.videoModel, models: videoModels)
            }

            Section {
                Button("Reset All Defaults", role: .destructive) {
                    Task { await resetDefaults() }
                }
            }
        }
        .padding()
        .onChange(of: defaults.textProvider) { _, newValue in
            loadModels(for: newValue, into: $textModels)
        }
        .onChange(of: defaults.visionProvider) { _, newValue in
            loadModels(for: newValue, into: $visionModels)
        }
        .onChange(of: defaults.audioProvider) { _, newValue in
            loadModels(for: newValue, into: $audioModels)
        }
        .onChange(of: defaults.videoProvider) { _, newValue in
            loadModels(for: newValue, into: $videoModels)
        }
    }

    // MARK: - Advanced Tab

    @ViewBuilder
    private var advancedTab: some View {
        Form {
            Section("Embeddings") {
                Picker("Model", selection: $defaults.embeddingsModel) {
                    Text("multilingual-e5-large (default)").tag("")
                    Text("multilingual-e5-large").tag("intfloat/multilingual-e5-large")
                    Text("multilingual-e5-base (smaller)").tag("intfloat/multilingual-e5-base")
                    Text("bge-small-en (fast, English)").tag("BAAI/bge-small-en-v1.5")
                    Text("all-MiniLM-L6-v2 (tiny, English)").tag("all-MiniLM-L6-v2")
                }
                Text("Changing model requires re-indexing all documents")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Generation") {
                HStack {
                    Text("Temperature")
                    Slider(value: temperatureBinding, in: 0...2, step: 0.1)
                    Text(temperatureDisplay)
                        .monospacedDigit()
                        .frame(width: 30)
                }
                TextField("Max Tokens", text: $defaults.maxTokens)
                    .textFieldStyle(.roundedBorder)
            }

            Section("Prompt") {
                TextField("Prompt Prefix (prepended to all prompts)", text: $defaults.promptPrefix, axis: .vertical)
                    .lineLimit(3...6)
            }
        }
        .padding()
    }

    // MARK: - Helpers

    private var temperatureBinding: Binding<Double> {
        Binding(
            get: { Double(defaults.temperature) ?? 0.7 },
            set: { defaults.temperature = String(format: "%.1f", $0) }
        )
    }

    private var temperatureDisplay: String {
        defaults.temperature.isEmpty ? "0.7" : defaults.temperature
    }

    @ViewBuilder
    private func providerPicker(selection: Binding<String>) -> some View {
        Picker("Provider", selection: selection) {
            Text("None").tag("")
            ForEach(appState.providers, id: \.providerType) { provider in
                Text(provider.name).tag(provider.providerType)
            }
        }
    }

    @ViewBuilder
    private func modelPicker(selection: Binding<String>, models: [ModelInfo]) -> some View {
        Picker("Model", selection: selection) {
            Text("None").tag("")
            ForEach(models, id: \.modelId) { model in
                Text(model.fullName).tag(model.modelId)
            }
        }
    }

    private func loadModels(for providerType: String, into models: Binding<[ModelInfo]>) {
        guard !providerType.isEmpty else {
            models.wrappedValue = []
            return
        }
        Task {
            do {
                models.wrappedValue = try await appState.providerService.listAvailableModels(
                    providerType: providerType
                )
            } catch {
                logger.error("Failed to load models for \(providerType): \(error.localizedDescription)")
            }
        }
    }

    private func loadDefaults() async {
        isLoading = true
        defer { isLoading = false }
        do {
            defaults = try await appState.fetchAIDefaults()
            // Load model lists for any pre-configured providers
            if !defaults.textProvider.isEmpty {
                loadModels(for: defaults.textProvider, into: $textModels)
            }
            if !defaults.visionProvider.isEmpty {
                loadModels(for: defaults.visionProvider, into: $visionModels)
            }
            if !defaults.audioProvider.isEmpty {
                loadModels(for: defaults.audioProvider, into: $audioModels)
            }
            if !defaults.videoProvider.isEmpty {
                loadModels(for: defaults.videoProvider, into: $videoModels)
            }
        } catch {
            logger.error("Failed to load AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to load: \(error.localizedDescription)"
        }
    }

    private func saveDefaults() async {
        guard !isLoading else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            try await appState.saveAIDefaults(defaults)
            errorMessage = nil
        } catch {
            logger.error("Failed to save AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to save: \(error.localizedDescription)"
        }
    }

    private func resetDefaults() async {
        do {
            try await appState.resetAIDefaults()
            defaults = AIDefaults()
            textModels = []
            visionModels = []
            audioModels = []
            videoModels = []
            errorMessage = nil
        } catch {
            logger.error("Failed to reset AI defaults: \(error.localizedDescription)")
            errorMessage = "Failed to reset: \(error.localizedDescription)"
        }
    }
}

// MARK: - General Settings

/// General application settings
struct GeneralSettingsView: View {
    @AppStorage("thumbnailSize") private var thumbnailSize: Double = 120
    @AppStorage("autoExtractText") private var autoExtractText: Bool = true
    @AppStorage("autoCreateEmbeddings") private var autoCreateEmbeddings: Bool = true

    var body: some View {
        Form {
            Section("Display") {
                Slider(value: $thumbnailSize, in: 80...200) {
                    Text("Thumbnail Size")
                }
            }

            Section("Ingestion") {
                Toggle("Auto-extract text from documents", isOn: $autoExtractText)
                Toggle("Auto-create search embeddings", isOn: $autoCreateEmbeddings)
            }
        }
        .padding()
    }
}

// MARK: - Backend Settings

/// Backend connection settings
struct BackendSettingsView: View {
    @EnvironmentObject var appState: AppState
    @AppStorage("backendPort") private var backendPort: Int = 8765
    @AppStorage("backendHost") private var backendHost: String = "127.0.0.1"

    var body: some View {
        Form {
            Section("Connection") {
                TextField("Host", text: $backendHost)
                TextField("Port", value: $backendPort, format: .number)

                HStack {
                    Circle()
                        .fill(appState.isBackendRunning ? Color.green : Color.red)
                        .frame(width: 10, height: 10)

                    Text(appState.isBackendRunning ? "Connected" : "Disconnected")

                    Spacer()
                }
            }

            Section("Statistics") {
                LabeledContent("Documents") {
                    Text("\(appState.documentCount)")
                }
                LabeledContent("Indexed") {
                    Text("\(appState.indexedCount)")
                }
            }
        }
        .padding()
    }
}

// MARK: - Local Models Settings

/// Local model management (Whisper, Embeddings)
struct LocalModelsSettingsView: View {
    @EnvironmentObject var appState: AppState

    @State private var whisperModels: [LocalModelStatus] = []
    @State private var embeddingsModels: [LocalModelStatus] = []
    @State private var diskUsage: DiskUsageInfo?
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        Form {
            if !appState.isBackendRunning {
                Section {
                    Label("Backend not connected", systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.secondary)
                }
            } else if isLoading {
                Section {
                    ProgressView("Loading models...")
                }
            } else {
                Section("Whisper (Audio Transcription)") {
                    ForEach(whisperModels) { model in
                        localModelRow(model: model, type: "whisper")
                    }
                }

                Section("Embeddings (Search)") {
                    ForEach(embeddingsModels) { model in
                        localModelRow(model: model, type: "embeddings")
                    }
                }

                if let usage = diskUsage {
                    Section("Disk Usage") {
                        LabeledContent("Whisper") {
                            Text(formatBytes(usage.whisper))
                        }
                        LabeledContent("Embeddings") {
                            Text(formatBytes(usage.embeddings))
                        }
                        LabeledContent("Total") {
                            Text(formatBytes(usage.total))
                                .bold()
                        }
                    }
                }
            }

            if let error = errorMessage {
                Section {
                    Text(error)
                        .foregroundStyle(.red)
                        .font(.caption)
                }
            }
        }
        .padding()
        .task {
            guard !Task.isCancelled else { return }
            await loadModels()
        }
    }

    @ViewBuilder
    private func localModelRow(model: LocalModelStatus, type: String) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(model.displayName)
                    .font(.body)
                if model.isDownloaded {
                    Text(formatBytes(model.sizeBytes))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text("~\(model.expectedSizeMb) MB")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            if model.isDownloaded {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                Button("Delete") {
                    Task { await deleteModel(type: type, modelId: model.modelId) }
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.red)
            } else {
                Button("Download") {
                    Task { await downloadModel(type: type, modelId: model.modelId) }
                }
                .buttonStyle(.borderless)
            }
        }
    }

    private func loadModels() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let modelsData = try await fetchLocalModels()
            whisperModels = modelsData.filter { $0.modelType == "whisper" }
            embeddingsModels = modelsData.filter { $0.modelType == "embeddings" }
            diskUsage = try await fetchDiskUsage()
        } catch {
            logger.error("Failed to load local models: \(error.localizedDescription)")
            errorMessage = "Failed to load: \(error.localizedDescription)"
        }
    }

    private func downloadModel(type: String, modelId: String) async {
        do {
            let url = URL(string: "http://127.0.0.1:8765/api/local-models/download/\(type)/\(modelId)")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else { return }
            await loadModels()
        } catch {
            errorMessage = "Download failed: \(error.localizedDescription)"
        }
    }

    private func deleteModel(type: String, modelId: String) async {
        do {
            let url = URL(string: "http://127.0.0.1:8765/api/local-models/\(type)/\(modelId)")!
            var request = URLRequest(url: url)
            request.httpMethod = "DELETE"
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else { return }
            await loadModels()
        } catch {
            errorMessage = "Delete failed: \(error.localizedDescription)"
        }
    }

    private func fetchLocalModels() async throws -> [LocalModelStatus] {
        let url = URL(string: "http://127.0.0.1:8765/api/local-models")!
        let (data, _) = try await URLSession.shared.data(from: url)
        let response = try JSONDecoder().decode(LocalModelsResponse.self, from: data)
        return response.models
    }

    private func fetchDiskUsage() async throws -> DiskUsageInfo {
        let url = URL(string: "http://127.0.0.1:8765/api/local-models/disk-usage")!
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(DiskUsageInfo.self, from: data)
    }

    private func formatBytes(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(bytes))
    }
}

// MARK: - Local Models Response Types

struct LocalModelsResponse: Codable {
    let models: [LocalModelStatus]
}

struct LocalModelStatus: Codable, Identifiable {
    let modelId: String
    let modelType: String
    let displayName: String
    let sizeBytes: Int
    let isDownloaded: Bool
    let expectedSizeMb: Int
    let path: String?

    var id: String { "\(modelType)/\(modelId)" }

    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
        case modelType = "model_type"
        case displayName = "display_name"
        case sizeBytes = "size_bytes"
        case isDownloaded = "is_downloaded"
        case expectedSizeMb = "expected_size_mb"
        case path
    }
}

struct DiskUsageInfo: Codable {
    let whisper: Int
    let embeddings: Int
    let total: Int
}
