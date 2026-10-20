#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

extension ShareSettingsView {
    // MARK: - State management

    var refreshKey: String {
        [hostingEnabled.description, publicBaseURL, spkiPin, engineHost,
         appState.isBackendRunning.description, didBootstrap.description]
            .joined(separator: "|")
    }

    /// ONE ACTION. Flipping this on derives the address, advertises the Mac, restarts
    /// the engine with TLS and mints the invite — the user does not do our setup.
    var sharingBinding: Binding<Bool> {
        Binding(
            get: { hostingEnabled },
            set: { newValue in
                hostingEnabled = newValue
                if newValue {
                    bonjourEnabled = true
                    if publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        publicBaseURL = Self.autoLocalBaseURL
                    }
                }
                Task { await applySharing() }
            }
        )
    }

    /// One truth (#5914): the switch shows what the ENGINE says (`backendMultiuser`, the same value the Accounts row reads) and
    /// a flip goes to the engine through the audited route, which refuses in words (the owner has no password yet) and takes
    /// effect at once; nothing restarts the engine, so there is no restart that can fail and leave the two disagreeing.
    var multiuserBinding: Binding<Bool> {
        Binding(
            get: { backendMultiuser },
            set: { newValue in
                guard newValue != backendMultiuser else { return }
                Task { await setMultiuserOnEngine(newValue) }
            }
        )
    }

    /// The switch goes through `PUT /api/pair/multiuser` for every engine, ours included (the app no longer hands the embedded
    /// engine `FICHERO_MULTIUSER`, which made the route refuse and bypassed its owner-password rule); the Settings window has
    /// no project steps, so ⌘Z is the audit row's, reachable from the CLI and MCP (#5751). On a refusal or a failure the switch
    /// is left as the engine really is, with the engine's reason in words.
    func setMultiuserOnEngine(_ enabled: Bool) async {
        isApplyingChange = true
        shareError = nil
        defer { isApplyingChange = false }
        do {
            try await MultiuserSwitch.set(
                enabled, pairing: PairingService(apiRoot: EngineConfig.host), service: nil, steps: nil)
        } catch {
            shareError = error.localizedDescription
        }
        await appState.checkBackendHealth()
        multiuserEnabled = backendMultiuser  // the local copy other views read follows the engine, never the other way round
    }

    func applySharing() async {
        isApplyingChange = true
        shareError = nil
        defer { isApplyingChange = false }
        if !hostingEnabled {
            RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: publicBaseURL)
            RemoteCertificatePinning.clearPersistedSPKIPin(hostString: publicBaseURL)
            loadSPKIPin()
        }

        if backendService.isUsingExternalBackend {
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            // The external engine already serves TLS; the health handshake bootstraps
            // its pin. Load it as part of THIS action so the QR appears without a
            // separate "Prepare Certificate" step (#3811).
            loadSPKIPin()
            if hostingEnabled {
                await refreshDevices()
            }
            return
        }

        backendService.stop()
        do {
            try await backendService.start()
            // A start that was already in flight is waited for, and a stop() of ours may have killed its engine: end with one (#5909).
            if EmbeddedBackendService.needsAnotherStart(status: backendService.status) { try await backendService.start() }
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            // Load the SPKI pin AFTER the health handshake. Turning sharing on mints
            // and persists the certificate as part of THIS action, so by the time the
            // pairing card evaluates its blocker the pin is ready and the QR appears —
            // no separate "Prepare Certificate" step (#3811). Reading it here covers
            // both the pin the restart pre-persists and one the live TLS handshake
            // bootstraps.
            loadSPKIPin()
            if hostingEnabled { await refreshDevices() }
        } catch {
            shareError = error.localizedDescription
        }
    }

    func refreshPairingCode() async {
        pairingCode = nil
        shareError = nil
        guard pairingBlocker == nil else { return }
        isGeneratingCode = true
        defer { isGeneratingCode = false }
        do {
            try await Task.sleep(for: .milliseconds(200))
            try Task.checkCancellation()
            pairingCode = try await PairingService(apiRoot: EngineConfig.host).createPairingCode()
        } catch {
            if !error.isCancellationError { shareError = error.localizedDescription }
        }
    }

    func refreshSharingState() async {
        guard EngineConfig.engineIsLocal else { return }
        let pairing = PairingService(apiRoot: EngineConfig.host)
        sharingState = try? await pairing.sharingState()
        detectedTailnetURL = try? await pairing.detectedTailnetURL()
    }

    func refreshDevices() async {
        isLoadingDevices = true
        defer { isLoadingDevices = false }
        guard EngineConfig.engineIsLocal else { return }
        do {
            pairedDevices = try await PairingService(apiRoot: EngineConfig.host).listDevices()
        } catch {
            shareError = error.localizedDescription
        }
    }

    func revoke(deviceID: String) async {
        shareError = nil
        guard EngineConfig.engineIsLocal else { return }
        do {
            try await PairingService(apiRoot: EngineConfig.host).revokeDevice(id: deviceID)
            await refreshDevices()
        } catch {
            shareError = error.localizedDescription
        }
    }

    func revokeSelected() async {
        shareError = nil
        guard EngineConfig.engineIsLocal else { return }
        let service = PairingService(apiRoot: EngineConfig.host)
        do {
            for id in selectedDevices { try await service.revokeDevice(id: id) }
        } catch {
            shareError = error.localizedDescription
        }
        selectedDevices.removeAll()
        await refreshDevices()
    }

    func loadSPKIPin() {
        spkiPin = RemoteAccessConfig.hostedBackendSPKIPin(hostString: publicBaseURL) ?? ""
    }

    var sharedLibraryPath: String? {
        if let currentLibraryId = libraryManager.currentLibraryId,
           let library = libraryManager.getLibrary(id: currentLibraryId) {
            return library.url.path
        }
        return libraryManager.globalLibrary?.url.path
    }
}
#endif
