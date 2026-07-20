#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

extension ShareSettingsView {
    // MARK: - Security summary

    @ViewBuilder
    var securitySection: some View {
        Section("Security") {
            // The authoritative multi-user toggle lives in Engine settings
            // (owns fichero.multiuser.enabled, restart-applied). Show it here
            // read-only so the sharing surface reflects the current mode.
            LabeledContent("Multi-user mode") {
                Text(backendMultiuser ? "Enabled" : "Disabled")
                    .foregroundStyle(backendMultiuser ? .primary : .secondary)
            }

            LabeledContent("Backend authz") {
                Text(backendAuthzStatus)
                    .foregroundStyle(backendAuthzStatus == "Enabled" ? .primary : .secondary)
            }

            if isLoadingAuthz {
                LabeledContent("Library ACL") {
                    ProgressView().controlSize(.small)
                }
            } else if let authzSnapshot {
                LabeledContent("Library ACL") {
                    Text(authzSnapshot.currentUserRole?.capitalized ?? "No role")
                        .foregroundStyle(.secondary)
                }
                LabeledContent("Access") {
                    Text(authzAccessSummary(authzSnapshot))
                        .foregroundStyle(.secondary)
                }
            } else if let authzError {
                LabeledContent("Library ACL") {
                    Text(authzError)
                        .foregroundStyle(.red)
                }
            } else {
                LabeledContent("Library ACL") {
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
