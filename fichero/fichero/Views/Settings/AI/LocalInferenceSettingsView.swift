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
                // Runtime block + full multi-runtime catalog now live in the
                // shared `LocalRuntimeModelsView` so a local PROVIDER ROW can
                // render exactly the same rows filtered to one runtime.
                LocalRuntimeModelsView(
                    store: store,
                    providerType: nil,
                    showRuntime: true,
                    modelsTitle: "Model Catalog"
                )
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
}

// MARK: - Capability Chip

/// What a model can actually DO, said on the row instead of left to the name.
/// A catalog of five OCR-looking names with no capability marks makes the user
/// guess which one reads an image and which one only takes text.
struct CapabilityChip: View {
    let capability: String

    var body: some View {
        Label(label, systemImage: symbol)
            .font(.caption2)
            .labelStyle(.titleAndIcon)
            .foregroundStyle(.secondary)
            .help(help)
    }

    private var label: String { LocalInferenceDisplay.capabilityLabel(capability) }

    private var symbol: String {
        switch capability {
        case "vision": return "eye"
        case "audio": return "waveform"
        default: return "text.alignleft"
        }
    }

    private var help: String {
        switch capability {
        case "vision": return "Reads images and page scans."
        case "audio": return "Transcribes audio."
        default: return "Reads and writes text."
        }
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
