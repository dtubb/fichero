import FicheroAPIClient
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "LocalModelsCatalogView")

// MARK: - Local Models Catalog (per model_type)

/// The installable-model list for ONE no-prompt local runtime — spaCy (grammar),
/// Kraken (OCR), Whisper (ASR) — rendered as a `Section` for a `Form` so it can
/// live INSIDE that provider's row (Daniel, 2026-09-05: downloads in the row).
///
/// These runtimes are served by the `/api/local-models` spine (their models are
/// `LocalModelInfoResponse`, keyed by `model_type`) — a different system from the
/// MLX `/api/local-inference/catalog` that `LocalRuntimeModelsView` drives. This
/// view owns that spine for a single `model_type`, showing each model's size,
/// availability, and a Download / Delete action with a live download state.
///
/// ponytail: mirrors the proven fetch/download/delete/poll flow of the Downloads
/// tab (`LocalModelsSettingsView`) rather than sharing a store — the two lay
/// their rows out differently, and the calls are a handful of lines. Fold both
/// onto one @Observable store if a third caller appears.
struct LocalModelsCatalogView: View {
    /// The runtime whose models to list — a `model_type` on the wire
    /// ("spacy" / "kraken" / "whisper"), which equals the provider_type for
    /// these no-prompt runtimes.
    let modelType: String
    var title: String = "On-Device Models"

    @Environment(AppState.self) private var appState
    @Environment(LibraryManager.self) private var libraryManager

    @State private var models: [Components.Schemas.LocalModelInfoResponse] = []
    @State private var isLoading = true
    @State private var errorMessage: String?

    /// The generated API client (injects auth + library header via middleware),
    /// same accessor the Downloads tab uses. Local-models endpoints are app-wide.
    private var client: FicheroClient {
        libraryManager.globalLibrary?.ficheroClient
            ?? FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)
    }

    var body: some View {
        Section(title) {
            if isLoading {
                ProgressView("Loading models…")
            } else if let errorMessage {
                VStack(alignment: .leading, spacing: 6) {
                    Label("Couldn't load models", systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button("Retry") { Task { await loadModels() } }
                }
            } else if models.isEmpty {
                Text("No models available.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                // One header line for a whole-runtime fact: if the runtime is
                // missing every Download below is inert, so say why once here
                // rather than letting each row fail silently.
                if let reason = models.compactMap(\.unavailableReason).first {
                    Label(reason, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                ForEach(models, id: \.modelId) { model in
                    modelRow(model)
                }
            }
        }
        .task(id: modelType) {
            guard !Task.isCancelled else { return }
            await loadModels()
        }
    }

    @ViewBuilder
    private func modelRow(_ model: Components.Schemas.LocalModelInfoResponse) -> some View {
        let unavailable = model.available == false
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 3) {
                Text(model.displayName)
                    .font(.body)
                Text(sizeText(model))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if unavailable, let reason = model.unavailableReason, !reason.isEmpty {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if let note = model.note, !note.isEmpty {
                    Text(note)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                // A background download that failed must say so on the row —
                // an invisible failure is how the old Whisper downloads "worked"
                // and then weren't there.
                if model.downloadState == "failed", let failure = model.downloadError, !failure.isEmpty {
                    Text(failure)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer()
            action(for: model)
        }
        .opacity(unavailable ? 0.5 : 1)
    }

    @ViewBuilder
    private func action(for model: Components.Schemas.LocalModelInfoResponse) -> some View {
        if model.available == false {
            Image(systemName: "nosign").foregroundStyle(.secondary)
        } else if model.downloadState == "downloading" {
            ProgressView().controlSize(.small)
        } else if model.isDownloaded {
            Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
            Button("Delete", role: .destructive) {
                Task { await deleteModel(model.modelId) }
            }
            .buttonStyle(.borderless)
        } else {
            Button("Download") {
                Task { await downloadModel(model.modelId) }
            }
            .buttonStyle(.borderless)
        }
    }

    /// Size to expect: the on-disk bytes once installed, else the catalog's
    /// expected download size. Whichever the backend could state.
    private func sizeText(_ model: Components.Schemas.LocalModelInfoResponse) -> String {
        if model.isDownloaded, model.sizeBytes > 0 {
            return Self.formatBytes(model.sizeBytes)
        }
        if model.expectedSizeMb > 0 {
            return "~\(model.expectedSizeMb) MB"
        }
        return "Size unknown"
    }

    // MARK: - Endpoints

    private func loadModels() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response = try await client.api.listLocalModelsApiLocalModelsGet(
                query: .init(modelType: modelType)
            )
            switch response {
            case .ok(let ok):
                models = try ok.body.json.models
            case .unprocessableContent, .undocumented:
                errorMessage = "Request failed"
            }
        } catch {
            logger.error("Load \(modelType) models failed: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
        }
    }

    private func downloadModel(_ modelId: String) async {
        do {
            let response = try await client.api.downloadModelApiLocalModelsDownloadModelTypeModelIdPost(
                path: .init(modelType: modelType, modelId: modelId)
            )
            switch response {
            case .ok:
                await loadModels()
                await followDownload(modelId)
            case .unprocessableContent, .undocumented:
                errorMessage = "Download failed"
            }
        } catch {
            logger.error("Download \(modelId) failed: \(error.localizedDescription)")
            errorMessage = "Download failed: \(error.localizedDescription)"
        }
    }

    /// The download endpoint returns the moment work is QUEUED, so poll the list
    /// until this model leaves the downloading state — otherwise the row would
    /// sit on a spinner forever, exactly how the old Whisper downloads stayed
    /// invisible. ponytail: naive 2s poll; these are minute-scale downloads.
    private func followDownload(_ modelId: String) async {
        for _ in 0..<600 {  // ~20 min ceiling, then stop polling
            let state = models.first { $0.modelId == modelId }?.downloadState
            guard state == "downloading" || state == "idle" else { return }
            try? await Task.sleep(for: .seconds(2))
            if Task.isCancelled { return }
            await loadModels()
        }
    }

    private func deleteModel(_ modelId: String) async {
        do {
            let response = try await client.api.deleteModelApiLocalModelsModelTypeModelIdDelete(
                path: .init(modelType: modelType, modelId: modelId)
            )
            switch response {
            case .ok:
                await loadModels()
            case .unprocessableContent, .undocumented:
                errorMessage = "Delete failed"
            }
        } catch {
            logger.error("Delete \(modelId) failed: \(error.localizedDescription)")
            errorMessage = "Delete failed: \(error.localizedDescription)"
        }
    }

    static func formatBytes(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(bytes))
    }
}
