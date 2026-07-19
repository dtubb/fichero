import FicheroAPIClient
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "Settings")

// MARK: - Local Models Settings

/// Local model management (Whisper, Embeddings)
struct LocalModelsSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(LibraryManager.self) var libraryManager

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
        .formStyle(.grouped)
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

    /// The generated API client (injects auth + library header via middleware).
    /// Local-models endpoints are app-wide (not library-scoped), but routing
    /// through the generated client still supplies the bearer token the backend
    /// requires and removes the hardcoded localhost URLs.
    private var client: FicheroClient {
        libraryManager.globalLibrary?.ficheroClient ?? FicheroClient(baseURL: EngineConfig.host)
    }

    private func downloadModel(type: String, modelId: String) async {
        do {
            let response = try await client.api.downloadModelApiLocalModelsDownloadModelTypeModelIdPost(
                path: .init(modelType: type, modelId: modelId)
            )
            switch response {
            case .ok:
                await loadModels()
            case .unprocessableContent, .undocumented:
                errorMessage = "Download failed"
            }
        } catch {
            errorMessage = "Download failed: \(error.localizedDescription)"
        }
    }

    private func deleteModel(type: String, modelId: String) async {
        do {
            let response = try await client.api.deleteModelApiLocalModelsModelTypeModelIdDelete(
                path: .init(modelType: type, modelId: modelId)
            )
            switch response {
            case .ok:
                await loadModels()
            case .unprocessableContent, .undocumented:
                errorMessage = "Delete failed"
            }
        } catch {
            errorMessage = "Delete failed: \(error.localizedDescription)"
        }
    }

    private func fetchLocalModels() async throws -> [LocalModelStatus] {
        let response = try await client.api.listLocalModelsApiLocalModelsGet(query: .init())
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.models.map { model in
                LocalModelStatus(
                    modelId: model.modelId,
                    modelType: model.modelType,
                    displayName: model.displayName,
                    sizeBytes: model.sizeBytes,
                    isDownloaded: model.isDownloaded,
                    expectedSizeMb: model.expectedSizeMb,
                    path: model.path
                )
            }
        case .unprocessableContent:
            throw LocalModelsError.requestFailed
        case .undocumented(let statusCode, _):
            throw LocalModelsError.unexpectedStatus(statusCode)
        }
    }

    private func fetchDiskUsage() async throws -> DiskUsageInfo {
        let response = try await client.api.diskUsageApiLocalModelsDiskUsageGet()
        switch response {
        case .ok(let okResponse):
            let usage = try okResponse.body.json
            return DiskUsageInfo(
                whisper: usage.whisper,
                embeddings: usage.embeddings,
                total: usage.total
            )
        case .undocumented(let statusCode, _):
            throw LocalModelsError.unexpectedStatus(statusCode)
        }
    }

    private func formatBytes(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(bytes))
    }
}

// MARK: - Local Models Response Types

enum LocalModelsError: LocalizedError {
    case requestFailed
    case unexpectedStatus(Int)

    var errorDescription: String? {
        switch self {
        case .requestFailed:
            return "Request failed"
        case .unexpectedStatus(let statusCode):
            return "Unexpected response: HTTP \(statusCode)"
        }
    }
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
