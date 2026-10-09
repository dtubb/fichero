import SwiftUI

// MARK: - Local Models Settings

/// Embeddings (search) model management. Whisper/spaCy/Kraken downloads moved
/// INTO their provider rows on Models & Providers (Daniel, 2026-09-05: downloads
/// live in the row); this tab is the slim home for embeddings, which are a
/// search concept with no provider row of their own (yet).
///
/// All endpoint access happens through `LocalModelsStore` (#5098: the
/// observable-data-layer guard — this view used to call the generated client
/// directly, the same offence `KnowledgeSettingsView` had and was fixed the
/// same way).
struct LocalModelsSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(LibraryManager.self) var libraryManager

    @State private var store = LocalModelsStore()

    var body: some View {
        Form {
            if !appState.isBackendRunning {
                Section {
                    Label("Backend not connected", systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.secondary)
                }
            } else if store.isLoading {
                Section {
                    ProgressView("Loading models...")
                }
            } else {
                Section("Embeddings (Search)") {
                    ForEach(store.embeddingsModels) { model in
                        localModelRow(model: model, type: "embeddings")
                    }
                }

                if let usage = store.diskUsage {
                    Section("Disk Usage") {
                        LabeledContent("Embeddings") {
                            Text(formatBytes(usage.embeddings))
                        }
                    }
                }
            }

            if let error = store.errorMessage {
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
            store.configure(libraryManager: libraryManager)
            await store.loadModels()
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
                SettingsModelDownloadLine(key: .init(runtime: type, model: model.modelId))
            }

            Spacer()

            if model.isDownloaded {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                Button("Delete") {
                    Task { await store.deleteModel(type: type, modelId: model.modelId) }
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.red)
            } else if model.downloadState == "downloading" {
                ProgressView().controlSize(.small)
            } else {
                // The one download path (#5620): a job Activity lists. Disabled rather than failing
                // silently: the section header above says what to do about it.
                SettingsModelDownloadButton(key: .init(runtime: type, model: model.modelId), name: model.displayName,
                                            enabled: model.available ?? true,
                                            help: model.unavailableReason ?? "Download it to this Mac") {
                    Task { await store.modelDownloaded(type: type, modelId: model.modelId) }
                }
            }
        }
        .opacity((model.available ?? true) ? 1 : 0.5)
    }

    private func formatBytes(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(bytes))
    }
}
