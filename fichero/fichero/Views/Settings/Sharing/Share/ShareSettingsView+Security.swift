#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

extension ShareSettingsView {
    // MARK: - Security summary

    @ViewBuilder
    var securitySection: some View {
        Section("Accounts") {
            LabeledContent("Accounts") {
                Text(accountsStatus)
                    .foregroundStyle(.secondary)
            }

            if let authzSnapshot, authzSnapshot.multiuserEnabled {
                LabeledContent("Project Role") {
                    Text(authzSnapshot.currentUserRole?.capitalized ?? "No role")
                        .foregroundStyle(.secondary)
                }
                LabeledContent("Access") {
                    Text(authzAccessSummary(authzSnapshot))
                        .foregroundStyle(.secondary)
                }
            } else if let authzError {
                Label(authzError, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
            }
        }
    }

    /// The engine's real multi-user state — the single source of truth (#3331),
    /// shared with the Users + Engine tabs so all three agree. Reads
    /// `GET /api/auth/identity` via IdentityStore, never the local desired flag.
    var backendMultiuser: Bool { appState.identityStore.multiuserEnabled }

    var accountsStatus: String {
        if !appState.isBackendRunning {
            return "Engine not running"
        }
        return backendMultiuser ? "On" : "Off"
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
