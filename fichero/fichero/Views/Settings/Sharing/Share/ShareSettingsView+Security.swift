#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

extension ShareSettingsView {
    // MARK: - Security summary

    @ViewBuilder
    var securitySection: some View {
        Section("Security") {
            LabeledContent("Backend authz") {
                Text(backendAuthzStatus)
                    .foregroundStyle(backendAuthzStatus == "Enabled" ? .primary : .secondary)
            }

            if isLoadingAuthz {
                LabeledContent("Project Role") {
                    ProgressView().controlSize(.small)
                }
            } else if let authzSnapshot, !authzSnapshot.multiuserEnabled {
                // Multi-user off is a normal state, not a fault (#3335).
                LabeledContent("Project Role") {
                    Text("Not enforcing per-library access")
                        .foregroundStyle(.secondary)
                }
            } else if let authzSnapshot {
                LabeledContent("Project Role") {
                    Text(authzSnapshot.currentUserRole?.capitalized ?? "No role")
                        .foregroundStyle(.secondary)
                }
                LabeledContent("Access") {
                    Text(authzAccessSummary(authzSnapshot))
                        .foregroundStyle(.secondary)
                }
            } else if let authzError {
                LabeledContent("Project Role") {
                    Text(authzError)
                        .foregroundStyle(.red)
                }
            } else {
                LabeledContent("Project Role") {
                    Text("Not loaded")
                        .foregroundStyle(.secondary)
                }
            }

            LabeledContent("Pairing") {
                Text(hostingEnabled ? "\(activePairedDevices(from: pairedDevices).count) devices" : "Off")
                    .foregroundStyle(.secondary)
            }
        }
    }

    /// The engine's real multi-user state — the single source of truth (#3331),
    /// shared with the Users + Engine tabs so all three agree. Reads
    /// `GET /api/auth/identity` via IdentityStore, never the local desired flag.
    var backendMultiuser: Bool { appState.identityStore.multiuserEnabled }

    var backendAuthzStatus: String {
        if !appState.isBackendRunning {
            return "Unavailable"
        }
        return backendMultiuser ? "Enabled" : "Disabled"
    }

    var securityRefreshKey: String {
        [
            appState.isBackendRunning.description,
            backendMultiuser.description,
            hostingEnabled.description,
            libraryManager.globalLibrary?.id.uuidString ?? "none"
        ].joined(separator: "|")
    }
}
#endif
