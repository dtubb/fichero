import FicheroAPIClient
import SwiftUI

// MARK: - Local Runtime Models (shared)

/// The installable-model catalog for an on-device runtime, plus (for MLX) the
/// runtime-provisioning block — rendered as `Section`s meant to sit inside a
/// `Form`. One view drives BOTH the standalone Local-inference pane and each
/// local PROVIDER ROW on Models & Providers (Daniel's ruling, 2026-09-05: every
/// local runtime is a provider row with its downloads inside it).
///
/// The catalog is `/api/local-inference/catalog` — a single multi-runtime source
/// keyed by `provider_type` (MLX, spaCy, Kraken, Whisper). Pass `providerType`
/// to show only one runtime's models inside its own row; pass `nil` to show the
/// whole catalog. `showRuntime` adds the MLX runtime block (only meaningful for
/// the `omlx` provider, whose models need the mlx-lm / mlx-vlm / mlx-whisper
/// sidecar provisioned first).
///
/// All actions reuse `LocalInferenceStore` (the sole endpoint accessor) — this
/// view owns no networking, only presentation, so the install/progress/delete
/// state machine stays in one tested place.
struct LocalRuntimeModelsView: View {
    let store: LocalInferenceStore
    /// Show only this runtime's catalog entries (`ProviderType` rawValue, e.g.
    /// "omlx"/"spacy"/"kraken"/"whisper"). `nil` shows every runtime's models.
    var providerType: String?
    /// Include the MLX runtime provisioning/version/disk block above the models.
    var showRuntime: Bool = false
    /// Section header for the models list.
    var modelsTitle: String = "Models"
    /// When true, an empty catalog renders nothing instead of a placeholder row
    /// (used where the surrounding view supplies its own empty state).
    var hidesEmptyCatalog: Bool = false

    private var entries: [Components.Schemas.LocalModelCatalogEntry] {
        guard let providerType else { return store.catalog }
        return store.catalog.filter { $0.providerType.rawValue == providerType }
    }

    var body: some View {
        if showRuntime {
            runtimeSection
        }
        catalogSection
    }

    // MARK: Runtime (MLX)

    @ViewBuilder
    private var runtimeSection: some View {
        Section("Runtime") {
            let runtime = store.runtime
            HStack {
                Label {
                    Text(runtime?.provisioned == true ? "Provisioned" : "Not provisioned")
                } icon: {
                    Image(systemName: runtime?.provisioned == true ? "checkmark.seal.fill" : "seal")
                        .foregroundStyle(runtime?.provisioned == true ? .green : .secondary)
                }
                LocalPrivateBadge()
                Spacer()
                if store.isRuntimeBusy {
                    runtimeProgress
                } else if runtime?.provisioned == true {
                    Button("Remove", role: .destructive) {
                        Task { await store.removeRuntime() }
                    }
                    .buttonStyle(.borderless)
                } else {
                    Button("Provision") {
                        Task { await store.provisionRuntime() }
                    }
                    .buttonStyle(.borderless)
                }
            }

            if let version = runtime?.mlxLmVersion, !version.isEmpty {
                LabeledContent("mlx-lm (text)", value: version)
            }
            if let version = runtime?.mlxVlmVersion, !version.isEmpty {
                LabeledContent("mlx-vlm (vision)", value: version)
            }
            // Audio is its own capability: a runtime can serve every text and
            // vision model in the catalog with no transcriber installed, so it
            // is not "unprovisioned" — it just cannot transcribe, and says so
            // here rather than failing when someone runs a Whisper workflow.
            if let version = runtime?.mlxWhisperVersion, !version.isEmpty {
                LabeledContent("mlx-whisper (audio)", value: version)
            } else if runtime?.provisioned == true {
                LabeledContent("mlx-whisper (audio)") {
                    Text("Not installed — Provision again to add transcription")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            if let bytes = runtime?.diskUsageBytes, bytes > 0 {
                LabeledContent("Disk usage", value: Self.formatBytes(bytes))
            }
        }
    }

    @ViewBuilder
    private var runtimeProgress: some View {
        if let job = store.runtime?.job,
           let fraction = LocalInferenceDisplay.progressFraction(current: job.current, total: job.total, percent: job.percent) {
            ProgressView(value: fraction) {
                if !job.message.isEmpty {
                    Text(job.message).font(.caption).foregroundStyle(.secondary)
                }
            }
            .frame(width: 160)
        } else {
            ProgressView().controlSize(.small)
        }
    }

    // MARK: Catalog

    @ViewBuilder
    private var catalogSection: some View {
        if entries.isEmpty {
            if !hidesEmptyCatalog {
                Section(modelsTitle) {
                    Text("No models available.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        } else {
            Section(modelsTitle) {
                ForEach(entries, id: \.modelId) { entry in
                    catalogRow(entry)
                }
            }
        }
    }

    @ViewBuilder
    private func catalogRow(_ entry: Components.Schemas.LocalModelCatalogEntry) -> some View {
        let row = LocalInferenceDisplay.row(
            supported: entry.supported,
            unsupportedReason: entry.unsupportedReason,
            installed: entry.installed
        )
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(entry.displayName)
                        .font(.body)
                    ForEach(entry.capabilities ?? [], id: \.self) { capability in
                        CapabilityChip(capability: capability)
                    }
                    if entry.testedStatus == "untested" {
                        // Never claim a model works here on its reputation.
                        Text("untested")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .help("Nobody has run this model inside Fichero yet.")
                    }
                }
                // Size and memory floor together: the two numbers that decide
                // whether a download is worth starting on THIS Mac.
                Text(Self.subtitle(for: entry))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if row.disabled, let reason = row.unsupportedReason {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if let note = entry.note, !note.isEmpty {
                    Text(note)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer()
            catalogAction(entry, row: row)
        }
        .opacity(row.disabled ? 0.5 : 1)
    }

    @ViewBuilder
    private func catalogAction(_ entry: Components.Schemas.LocalModelCatalogEntry, row: LocalInferenceDisplay.CatalogRow) -> some View {
        if row.disabled {
            Image(systemName: "nosign").foregroundStyle(.secondary)
        } else if let job = store.downloads[entry.modelId],
                  !LocalInferenceDisplay.isTerminal(state: job.state, error: job.error, percent: job.percent) {
            HStack(spacing: 8) {
                if let fraction = LocalInferenceDisplay.progressFraction(current: job.current, total: job.total, percent: job.percent) {
                    ProgressView(value: fraction).frame(width: 100)
                } else {
                    ProgressView().controlSize(.small)
                }
                Button("Cancel") {
                    Task { await store.cancelDownload(modelId: entry.modelId) }
                }
                .buttonStyle(.borderless)
            }
        } else if row.installed {
            Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
            Button("Delete", role: .destructive) {
                Task { await store.deleteModel(modelId: entry.modelId) }
            }
            .buttonStyle(.borderless)
        } else {
            Button("Download") {
                Task { await store.downloadModel(modelId: entry.modelId) }
            }
            .buttonStyle(.borderless)
        }
    }

    // MARK: Formatting

    /// "5.8 GB · needs 16 GB unified memory" — the mapping itself lives in
    /// `LocalInferenceDisplay` so it can be tested without the generated type.
    static func subtitle(for entry: Components.Schemas.LocalModelCatalogEntry) -> String {
        LocalInferenceDisplay.subtitle(
            downloadSizeBytes: entry.downloadSizeBytes,
            diskUsageBytes: entry.diskUsageBytes,
            memoryClass: entry.memoryClass,
            format: formatBytes
        )
    }

    static func formatBytes(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(bytes))
    }
}
