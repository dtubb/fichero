import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "Settings")

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
