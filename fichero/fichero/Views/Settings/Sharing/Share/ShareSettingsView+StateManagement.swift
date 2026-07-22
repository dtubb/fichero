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

    func revokeAllDevices() async {
        shareError = nil
        guard EngineConfig.engineIsLocal else { return }
        let service = PairingService(apiRoot: EngineConfig.host)
        do {
            for device in activePairedDevices(from: pairedDevices) {
                try await service.revokeDevice(id: device.id)
            }
        } catch {
            shareError = error.localizedDescription
        }
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
