import FicheroAPIClient
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "Settings")

// MARK: - Local Models Settings

/// Embeddings (search) model management. Whisper/spaCy/Kraken downloads moved
/// INTO their provider rows on Models & Providers (Daniel, 2026-09-05: downloads
/// live in the row); this tab is the slim home for embeddings, which are a
/// search concept with no provider row of their own (yet).
struct LocalModelsSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(LibraryManager.self) var libraryManager

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
                Section("Embeddings (Search)") {
                    ForEach(embeddingsModels) { model in
                        localModelRow(model: model, type: "embeddings")
                    }
                }

                if let usage = diskUsage {
                    Section("Disk Usage") {
                        LabeledContent("Embeddings") {
                            Text(formatBytes(usage.embeddings))
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
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 3) {
                Text(model.displayName)
                    .font(.body)
                Text(model.isDownloaded ? formatBytes(model.sizeBytes) : "~\(model.expectedSizeMb) MB")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let note = model.note, !note.isEmpty {
                    Text(note)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                // A background download that failed used to leave the row
                // unchanged forever. Now it says what happened.
                if model.downloadState == "failed", let failure = model.downloadError {
                    Text(failure)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .textSelection(.enabled)
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
            } else if model.downloadState == "downloading" {
                ProgressView().controlSize(.small)
            } else {
                Button("Download") {
                    Task { await downloadModel(type: type, modelId: model.modelId) }
                }
                .buttonStyle(.borderless)
                // Disabled rather than failing silently: the section header
                // above says what to do about it.
                .disabled(!(model.available ?? true))
                .help(model.unavailableReason ?? "")
            }
        }
        .opacity((model.available ?? true) ? 1 : 0.5)
    }

    private func loadModels() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let modelsData = try await fetchLocalModels()
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
        libraryManager.globalLibrary?.ficheroClient ?? FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)
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
                    path: model.path,
                    note: model.note,
                    available: model.available,
                    unavailableReason: model.unavailableReason,
                    downloadState: model.downloadState,
                    downloadError: model.downloadError
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
    /// What the model is for, in one line.
    var note: String?
    /// Whether this row's buttons can actually do anything right now.
    /// Optional, not defaulted: Swift's synthesized decoder throws on a
    /// missing non-optional key, and an older engine sends none of these.
    var available: Bool?
    var unavailableReason: String?
    /// idle | downloading | failed | installed.
    var downloadState: String?
    var downloadError: String?

    var id: String { "\(modelType)/\(modelId)" }

    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
        case modelType = "model_type"
        case displayName = "display_name"
        case sizeBytes = "size_bytes"
        case isDownloaded = "is_downloaded"
        case expectedSizeMb = "expected_size_mb"
        case path
        case note
        case available
        case unavailableReason = "unavailable_reason"
        case downloadState = "download_state"
        case downloadError = "download_error"
    }
}

struct DiskUsageInfo: Codable {
    let whisper: Int
    let embeddings: Int
    let total: Int
}
