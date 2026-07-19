import SwiftUI

extension ShareLibrarySheet {
    @MainActor
    func share() async {
        guard canShare else { return }
        isSharing = true
        shareError = nil
        didShare = false
        pairingCode = nil
        defer { isSharing = false }
        do {
            // Grant the role — the sheet's actual purpose. We deliberately IGNORE
            // the returned share_url: it is a loopback API URL that 401s and is
            // dead to anyone but this Mac (#3813). The link the recipient opens is
            // the pairing payload built in `pairingLink`.
            _ = try await library.actionsService.shareLibrary(user: personChoice, role: role)
            didShare = true
            // Share by sharing it: if this Mac can host but sharing isn't on yet,
            // turn it on as PART of this one action — mint the cert, start hosting —
            // so the recipient gets a working link without a separate trip to Settings
            // (#3811/#3776). No-op when hosting is already on or this Mac can't host
            // (remote engine / iOS), where the honest fallback card renders instead.
            if !hostingEnabled && canHostFromHere {
                await enableHostingForShare()
            }
            loadSPKIPin()
            await mintPairingCodeIfPossible()
            await loadMembers()
        } catch {
            shareError = error.localizedDescription
        }
    }

    /// Whether this Mac can prepare its own hosting for the share link: the host
    /// services are in scope AND this is the machine that runs the library's engine.
    var canHostFromHere: Bool {
        backendService != nil && appState != nil && libraryManager != nil && EngineConfig.engineIsLocal
    }

    /// Turn on hosting as part of "Share", mirroring `ShareSettingsView.applySharing`
    /// (the ONE pairing surface) so there is a single behaviour, not a divergent one:
    /// derive the address, restart the engine with TLS to mint the certificate, then
    /// load the pin AFTER the health handshake (the #3811 ordering fix).
    /// ponytail: this mirrors applySharing; the durable home is a shared
    /// enable-hosting primitive both call — extract when the engine lane exposes one.
    @MainActor
    func enableHostingForShare() async {
        guard let backendService, let appState, let libraryManager else { return }
        hostingEnabled = true
        bonjourEnabled = true
        if publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            publicBaseURL = Self.autoLocalBaseURL
        }

        if backendService.isUsingExternalBackend {
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            return
        }

        backendService.stop()
        do {
            try await backendService.start()
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
        } catch {
            shareError = error.localizedDescription
        }
    }

    /// Derives https://<hostname>.local:<port> from the system Bonjour name — the
    /// same automatic address `ShareSettingsView` derives, so both agree.
    static var autoLocalBaseURL: String {
        var host = ProcessInfo.processInfo.hostName.lowercased()
        if !host.hasSuffix(".local") {
            host = (host.components(separatedBy: ".").first ?? host) + ".local"
        }
        let port = URL(string: EngineConfig.defaultHostString)?.port ?? 8765
        return "https://\(host):\(port)"
    }

    func loadSPKIPin() {
        spkiPin = RemoteAccessConfig.hostedBackendSPKIPin(hostString: publicBaseURL) ?? ""
    }

    /// Mint the short-lived, single-use pair code — same code semantics as the QR.
    /// Skipped when there is no reachable address to bind it to; the honest
    /// unavailable state renders instead of a dead link.
    @MainActor
    func mintPairingCodeIfPossible() async {
        guard shareLinkUnavailableReason == nil else { return }
        do {
            pairingCode = try await PairingService(apiRoot: EngineConfig.host).createPairingCode()
        } catch {
            shareError = error.localizedDescription
        }
    }

    /// The one link format (#3774/#3813): reachable host + SPKI pin + pair code,
    /// as the `fichero://` payload iOS's `PairingQRCodePayloadDecoder` already
    /// parses. Identical to the QR and the copyable pairing link — not a second
    /// format, and never the loopback share_url.
    var pairingLink: String? {
        guard let pairingCode,
              let reachableURL = try? validatedHostedRemoteURL(from: publicBaseURL),
              let normalizedPin = try? RemoteCertificatePinning.validatedSPKIPin(spkiPin) else { return nil }
        let payload = PairingService(apiRoot: reachableURL).buildQRCodePayload(
            from: pairingCode,
            spki: normalizedPin,
            libraryPath: library.url.path
        )
        return try? RemoteClientPairing.inviteLinkString(from: payload)
    }

    /// Why there is no working share link yet — honest, named, and pointing at the
    /// fix. Mirrors the pairing surface's `PairingBlocker` vocabulary without
    /// coupling this cross-platform sheet to that AppKit-only type.
    var shareLinkUnavailableReason: (headline: String, detail: String)? {
        guard EngineConfig.engineIsLocal else {
            return ("This library is hosted on another machine",
                    "Sharing happens on the Mac that hosts the library, not on this one.")
        }
        guard hostingEnabled else {
            return ("Sharing is off",
                    "Turn sharing on so Fichero can prepare a reachable address and a security code for the link.")
        }
        do {
            _ = try validatedHostedRemoteURL(from: publicBaseURL)
        } catch {
            return ("No reachable address yet",
                    "This Mac only has a loopback address that other devices can't open. "
                    + "Turning sharing on derives a shareable address.")
        }
        guard (try? RemoteCertificatePinning.validatedSPKIPin(spkiPin)) != nil else {
            return ("Preparing the security certificate",
                    "Fichero is still minting the certificate for this address — try again in a moment.")
        }
        return nil
    }

    var sharedPersonName: String {
        usersStore.users.first(where: { $0.id == personChoice }).map { displayName($0) } ?? "this person"
    }

    func copyPairingLink() {
        guard let pairingLink else { return }
        PlatformPasteboard.writeString(pairingLink)
        copied = true
        Task {
            try? await Task.sleep(for: .seconds(2))
            copied = false
        }
    }
}
