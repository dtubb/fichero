import FicheroAPIClient
import Foundation
import Observation
import OSLog

private let localModelsStoreLogger = Logger(subsystem: "app.fichero.fichero", category: "LocalModelsStore")

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

/// Observable domain store for the Local Models settings pane (#5098's
/// observable-data-layer guard: `LocalModelsSettingsView` used to call
/// `client.api.*` directly, the same offence `KnowledgeSettingsStore` fixed for
/// the Knowledge settings pane — same template followed here).
///
/// Embeddings model management is **app-wide** (not library-scoped), but routes
/// through the generated client anyway for the bearer token + middleware
/// (`source: the view's own prior comment`). `configure(libraryManager:)` is
/// called once from the view's `.task` — the store cannot read `@Environment`
/// itself, so the view hands over the ONE thing it is allowed to decide (which
/// client to prefer), and every actual model call happens here.
@MainActor
@Observable
final class LocalModelsStore {
    private(set) var embeddingsModels: [LocalModelStatus] = []
    private(set) var diskUsage: DiskUsageInfo?
    private(set) var isLoading = true
    private(set) var errorMessage: String?

    private weak var libraryManager: LibraryManager?

    func configure(libraryManager: LibraryManager) {
        self.libraryManager = libraryManager
    }

    private var client: FicheroClient {
        libraryManager?.globalLibrary?.ficheroClient
            ?? FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)
    }

    func loadModels() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let modelsData = try await fetchLocalModels()
            embeddingsModels = modelsData.filter { $0.modelType == "embeddings" }
            diskUsage = try await fetchDiskUsage()
        } catch {
            localModelsStoreLogger.error("Failed to load local models: \(error.localizedDescription)")
            errorMessage = "Failed to load: \(error.localizedDescription)"
        }
    }

    func downloadModel(type: String, modelId: String) async {
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

    func deleteModel(type: String, modelId: String) async {
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
            return DiskUsageInfo(whisper: usage.whisper, embeddings: usage.embeddings, total: usage.total)
        case .undocumented(let statusCode, _):
            throw LocalModelsError.unexpectedStatus(statusCode)
        }
    }
}
