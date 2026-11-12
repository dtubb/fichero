#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

extension ShareSettingsView {
    // MARK: - State management

    /// What a NEW code is minted for; the engine's phase is not in it (`sharing.card-keeps-its-code`, `PairingCardRefresh`).
    var refreshKey: String {
        PairingCardRefresh.key(hostingEnabled: hostingEnabled, publicBaseURL: publicBaseURL, spkiPin: spkiPin,
                               engineHost: engineHost, didBootstrap: didBootstrap)
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
            showFailure(error, "Couldn't change Multi-user")
        }
        await appState.checkBackendHealth()
        multiuserEnabled = backendMultiuser  // the local copy other views read follows the engine, never the other way round
    }

    /// A failure while sharing, as the one alert (`sharing.host.dialog-errors-are-alerts`): never raw text on the grey line. Its
    /// fix, where the engine is not listening, re-applies Sharing, which restarts the engine and its listener; where only the
    /// owner may share, it signs this app in as the owner by key.
    func showFailure(_ error: Error, _ title: String) {
        failurePrompt = SharingFailurePrompt.make(
            sharing: error, title: title, offers: hostingEnabled ? [.turnSharingOffAndOn, .signInAsOwner] : [.signInAsOwner],
            perform: { fix in
                Task { if fix == .signInAsOwner { await appState.ownerSignIn.run() } else { await applySharing() } }
            }, copy: { PlatformPasteboard.writeString($0) })
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
            await refreshSharingState()  // the forward follows Sharing: re-read it (review N1)
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
            showFailure(error, hostingEnabled ? "Couldn't turn Sharing on" : "Couldn't turn Sharing off")
        }
        // The engine answers `none` until Sharing is on and makes the forward after readiness: re-read, or the row stays stale (review N1).
        await refreshSharingState()
        // Sharing on with nothing shared asks which projects (#6366).
        if hostingEnabled, ShareWhichProjectsModel.opens(sharedCount: sharingState?.sharedLibraryCount) {
            activeSheet = .whichProjects
        }
    }

    /// The engine process now running, by health's `engine_pid`; nil until health has answered once. Not
    /// `backendService.backendPID`, which is nil for an adopted engine (Dev Local, an external one): that re-minted on every
    /// health check (review N3).
    var currentEnginePID: Int? { healthEnginePID }

    /// Asks health who is running. A failed read keeps the last pid: a health check in flight must not make the card forget
    /// which engine its code came from.
    func refreshEnginePID() async {
        guard let response = try? await appState.ficheroClient.api.healthCheckApiHealthGet(headers: .init()),
              case .ok(let okResponse) = response, let pid = (try? okResponse.body.json)?.enginePid else { return }
        healthEnginePID = pid
    }

    /// Whether the code on the card came from the engine process now running (`PairingCardRefresh.sameEngine`).
    var codeIsFromThisEngine: Bool {
        PairingCardRefresh.sameEngine(codePID: codeEnginePID, currentPID: currentEnginePID)
    }

    func refreshPairingCode() async {
        await refreshEnginePID()
        // A health check in flight is not a reason to blank the card: the code it holds is still good until it expires,
        // as long as the SAME engine process holds it (a restart loses the engine's codes).
        if PairingCardRefresh.keepsCode(whenBlockedBy: pairingBlocker == .engineNotRunning, hasCode: pairingCode != nil,
                                        sameEngine: codeIsFromThisEngine) { return }
        pairingCode = nil
        codeEnginePID = nil
        shareError = nil
        guard pairingBlocker == nil else { return }
        isGeneratingCode = true
        defer { isGeneratingCode = false }
        do {
            try await Task.sleep(for: .milliseconds(200))
            try Task.checkCancellation()
            pairingCode = try await PairingService(apiRoot: EngineConfig.host).createPairingCode()
            codeEnginePID = currentEnginePID
        } catch {
            if !error.isCancellationError { showFailure(error, "Couldn't make a pairing code") }
        }
    }

    func refreshSharingState() async {
        guard EngineConfig.engineIsLocal else { return }
        let pairing = PairingService(apiRoot: EngineConfig.host)
        // A failed read keeps the last good state: nil would end the re-read and could read as "ours" (review P2).
        if let state = try? await pairing.sharingState() { sharingState = state }
        detectedTailnetURL = try? await pairing.detectedTailnetURL()
        firewallVerdict = await FirewallReader.read()
    }

    func refreshDevices() async {
        isLoadingDevices = true
        defer { isLoadingDevices = false }
        guard EngineConfig.engineIsLocal else { return }
        do {
            pairedDevices = try await PairingService(apiRoot: EngineConfig.host).listDevices()
        } catch {
            showFailure(error, "Couldn't list the paired devices")
        }
    }

    func revoke(deviceID: String) async {
        shareError = nil
        guard EngineConfig.engineIsLocal else { return }
        do {
            try await PairingService(apiRoot: EngineConfig.host).revokeDevice(id: deviceID)
            await refreshDevices()
        } catch {
            showFailure(error, "Couldn't remove the device")
        }
    }

    func revokeSelected() async {
        shareError = nil
        guard EngineConfig.engineIsLocal else { return }
        let service = PairingService(apiRoot: EngineConfig.host)
        do {
            for id in selectedDevices { try await service.revokeDevice(id: id) }
        } catch {
            showFailure(error, "Couldn't remove the device")
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
