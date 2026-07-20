#if canImport(AppKit)
import CoreImage
import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import SwiftUI

// The ONE host-side sharing and pairing surface (#3777).
//
// Turning sharing on is a SINGLE ACTION that does all of its own setup: it derives
// this Mac's address, advertises it on the local network, restarts the engine with
// TLS, mints the certificate pin and the invite. The user never types a URL, never
// sees an SPKI pin, never presses "Apply and Restart Engine". The old second copy
// of this pane (Engine → Backend → "Share This Mac") is gone; its only genuinely
// useful escape hatches — a manual address override and "Reset Invite" — live in
// the single Advanced disclosure at the bottom of this pane.
//
// What the toggle is and isn't: it is a CONVENIENCE ("don't listen"), never a
// safety story. The secret protects the user, not the switch — the engine denies
// any bearer token with no matching device row whatever this flag says. So sharing
// being on is not a risk to explain away; it is a door with a lock on it.

struct ShareSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(EmbeddedBackendService.self) var backendService
    @Environment(LibraryManager.self) var libraryManager
    @AppStorage(EngineConfig.userDefaultsKey) var engineHost = EngineConfig.defaultHostString
    // Multi-user status is read from the backend (IdentityStore) via
    // `backendMultiuser`, not a local flag, so this tab agrees with Users +
    // Engine (#3331).
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) var hostingEnabled = false
    @AppStorage(RemoteAccessConfig.bonjourEnabledKey) var bonjourEnabled = false
    @AppStorage(RemoteAccessConfig.publicBaseURLKey) var publicBaseURL = ""

    @State var pairingCode: PairingCodeRecord?
    @State var pairedDevices: [PairedDeviceRecord] = []
    @State var authzSnapshot: Components.Schemas.LibraryAuthzSnapshot?
    @State var authzError: String?
    @State var isLoadingAuthz = false
    @State var spkiPin = ""
    @State var shareError: String?
    @State var isApplyingChange = false
    @State var isGeneratingCode = false
    @State var isLoadingDevices = false
    @State var didBootstrap = false
    @State var copiedInvite = false
    @State var addressDraft = ""
    @State var confirmRemoveAllDevices = false

    let qrContext = CIContext()

    // Derives https://<hostname>.local:<port> from the system Bonjour name.
    // Port mirrors EngineConfig.defaultHostString so both stay in sync.
    static var autoLocalBaseURL: String {
        var host = ProcessInfo.processInfo.hostName.lowercased()
        if !host.hasSuffix(".local") {
            host = (host.components(separatedBy: ".").first ?? host) + ".local"
        }
        let port = URL(string: EngineConfig.defaultHostString)?.port ?? 8765
        return "https://\(host):\(port)"
    }

    var body: some View {
        Form {
            securitySection

            Section {
                Toggle(isOn: sharingBinding) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(hostingEnabled ? "On" : "Off")
                            .font(.headline)
                        Text("Share Fichero on this Mac with other devices.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .disabled(isApplyingChange || !EngineConfig.engineIsLocal)
                .padding(.vertical, 4)

                if hostingEnabled || pairingBlocker == .engineIsRemote {
                    PairingCardView(
                        pairingCode: pairingCode,
                        qrCodeImage: qrCodeImage,
                        publicURL: validatedPublicURL?.absoluteString,
                        inviteLink: inviteLinkString,
                        isGeneratingPairingCode: isGeneratingCode,
                        blocker: pairingBlocker,
                        errorMessage: shareError,
                        isResolving: isApplyingChange,
                        onResolve: { blocker in Task { await resolve(blocker) } },
                        copiedInvite: copiedInvite,
                        onCopyInvite: copyInvite
                    )
                }
            }

            if hostingEnabled {
                Section {
                    PairedDevicesSectionView(
                        devices: activePairedDevices(from: pairedDevices),
                        isLoading: isLoadingDevices,
                        canHostRemoteAccess: EngineConfig.engineIsLocal,
                        onRefresh: { Task { await refreshDevices() } },
                        onRevoke: { deviceID in Task { await revoke(deviceID: deviceID) } }
                    )
                }
            }

            advancedSection

            #if canImport(AppKit)
            // Client side of pairing — connect THIS Mac to another Fichero library
            // (consolidated here so all connection/pairing lives in Library Access).
            MacRemoteClientPairingSection(
                appState: appState,
                backendService: backendService,
                libraryManager: libraryManager
            )
            #endif
        }
        .formStyle(.grouped)
        .task {
            loadSPKIPin()
            addressDraft = publicBaseURL
            // Refresh the backend's real multi-user state so this tab's status
            // matches Users + Engine (#3331).
            await appState.identityStore.load()
            if hostingEnabled && publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                publicBaseURL = Self.autoLocalBaseURL
                await applySharing()
            } else if hostingEnabled, appState.isBackendRunning {
                await refreshDevices()
            }
            await loadAuthzSnapshot()
            didBootstrap = true
        }
        .task(id: securityRefreshKey) {
            guard didBootstrap else { return }
            await loadAuthzSnapshot()
        }
        .task(id: refreshKey) {
            guard didBootstrap else { return }
            await refreshPairingCode()
        }
        .onChange(of: publicBaseURL) { _, newValue in
            loadSPKIPin()
            addressDraft = newValue
        }
    }
}
#endif
