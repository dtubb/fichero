import FicheroAPIClient
import SwiftUI

// MARK: - Local Inference (MLX) Settings

/// Settings pane for the MLX local-inference sidecar (#3120): runtime
/// provisioning, the on-device model catalog, and per-profile service status.
/// Observes `LocalInferenceStore` — the only endpoint accessor — and never
/// touches the generated client directly.
struct LocalInferenceSettingsView: View {
    @Environment(AppState.self) var appState
    let store: LocalInferenceStore

    var body: some View {
        Form {
            if !appState.isBackendRunning {
                Section {
                    Label("Backend not connected", systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.secondary)
                }
            } else {
                runtimeSection
                catalogSection
                servicesSection
            }

            if let error = store.loadError {
                Section {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .textSelection(.enabled)
                }
            }
        }
        .formStyle(.grouped)
        .task {
            guard !Task.isCancelled else { return }
            await store.load()
        }
    }

    // MARK: Runtime

    @ViewBuilder
    private var runtimeSection: some View {
        Section("MLX Runtime") {
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
                LabeledContent("mlx-lm", value: version)
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
        Section("Model Catalog") {
            if store.catalog.isEmpty {
                Text("No models available.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(store.catalog, id: \.modelId) { entry in
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
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.displayName)
                    .font(.body)
                if row.disabled, let reason = row.unsupportedReason {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if let size = entry.downloadSizeBytes ?? entry.diskUsageBytes, size > 0 {
                    Text(Self.formatBytes(size))
                        .font(.caption)
                        .foregroundStyle(.secondary)
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

    // MARK: Services

    @ViewBuilder
    private var servicesSection: some View {
        let managed = store.profiles.filter { $0.managedByApp == true }
        if !managed.isEmpty {
            Section("Local Services") {
                ForEach(managed, id: \.id) { profile in
                    serviceRow(profile)
                }
            }
        }
    }

    @ViewBuilder
    private func serviceRow(_ profile: Components.Schemas.LocalProviderProfile) -> some View {
        let status = store.serviceStatuses[profile.id]
        let badge = LocalInferenceDisplay.badge(
            state: status?.state.rawValue ?? "stopped",
            lastError: status?.lastError
        )
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(profile.name)
                    .font(.body)
                Label(badge.text, systemImage: badge.symbol)
                    .font(.caption)
                    .foregroundStyle(tintColor(badge.tint))
                    .textSelection(.enabled)
            }
            Spacer()
            if status?.state.rawValue == "healthy" || status?.state.rawValue == "starting" || status?.state.rawValue == "degraded" {
                Button("Stop") {
                    Task { await store.stopProfile(id: profile.id) }
                }
                .buttonStyle(.borderless)
            } else {
                Button("Start") {
                    Task { await store.startProfile(id: profile.id) }
                }
                .buttonStyle(.borderless)
            }
        }
    }

    private func tintColor(_ tint: LocalInferenceDisplay.Tint) -> Color {
        switch tint {
        case .neutral: return .secondary
        case .active: return .accentColor
        case .warning: return .orange
        case .error: return .red
        case .success: return .green
        }
    }

    static func formatBytes(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(bytes))
    }
}

// MARK: - Local / Private Badge

/// The on-device/private marker shown next to local providers and the MLX
/// runtime — ties the AI-integrity local-instrument stance (#3120). Reusable
/// across the provider list and model pickers.
struct LocalPrivateBadge: View {
    var body: some View {
        Label("On-device", systemImage: "lock.laptopcomputer")
            .font(.caption2)
            .foregroundStyle(.secondary)
            .labelStyle(.titleAndIcon)
            .help("Runs locally on this Mac — nothing leaves the device.")
    }
}
