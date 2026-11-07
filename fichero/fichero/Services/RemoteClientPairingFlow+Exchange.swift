import FicheroAPIClient
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "RemoteClientPairing")

/// Exchanging a pairing code for a device and keeping what it gives (split from RemoteClientPairingFlow.swift to keep each file
/// under the size cap): the pair call, the credentials and host persisted, the remote health probe, the sequence that runs them
/// in order, and the Keychain save that revokes on a refusal.
extension RemoteClientPairing {
    static func pairDevice(
        remoteURL: String,
        pairCode: String,
        deviceName: String,
        expectedSPKIPin: String?,
        person: PairingPerson? = nil
    ) async throws -> PairingExchangeResult {
        let code = pairCode.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let name = deviceName.trimmingCharacters(in: .whitespacesAndNewlines)

        // A link with no code is for a person (Step 8.9): they sign in; until they have, the host asks who they are.
        if code.isEmpty, person == nil { throw RemoteClientPairingError.personRequired }
        guard !name.isEmpty else {
            throw RemoteClientPairingError.missingDeviceName
        }

        let url = try validatedRemoteURL(
            from: remoteURL,
            allowLocalhost: false,
            requireSecureTransportForRemote: true
        )
        let normalizedSPKIPin = try expectedSPKIPin.map(RemoteCertificatePinning.validatedSPKIPin)
        let service = PairingService(apiRoot: url, expectedSPKIPin: normalizedSPKIPin)
        let response: PairingExchangeResponse
        if code.isEmpty, let person {
            response = try await service.signInDeviceUnauthenticated(deviceName: name, person: person)
        } else {
            response = try await service.pairDeviceUnauthenticated(code: code, deviceName: name, person: person)
        }
        return PairingExchangeResult(
            apiRoot: url,
            deviceToken: response.deviceToken,
            expiresAt: response.expiresAt
        )
    }

    /// The host's credentials only: token, pin (or none for a public CA) and the expiry renewal reads. A synced
    /// project's ask (#5898) stores just these; it does not move this Mac's engine to the host.
    @MainActor
    static func persistHostCredentials(_ result: PairingExchangeResult, expectedSPKIPin: String?) throws {
        try PairingService.persistAuthToken(result.deviceToken, for: result.apiRoot)
        // No pin for a publicly-trusted host. Storing one would be worse than
        // useless: `shouldEnforcePinning` only grants the public-CA exemption
        // while NO pin is recorded, so writing one here re-arms enforcement
        // against a key we do not hold (#5041).
        if let expectedSPKIPin {
            try RemoteCertificatePinning.persistSPKIPin(expectedSPKIPin, hostString: result.apiRoot.absoluteString)
        } else {
            RemoteCertificatePinning.clearPersistedSPKIPin(hostString: result.apiRoot.absoluteString)
        }
        // Record the token's expiry so renewal can fire before it lapses (#3096).
        DeviceTokenRenewal.storeExpiry(result.expiresAt, host: result.apiRoot.absoluteString)
    }

    @MainActor
    static func persistPairedHost(
        _ result: PairingExchangeResult,
        expectedSPKIPin: String?,
        libraryPath: String?
    ) throws {
        try persistHostCredentials(result, expectedSPKIPin: expectedSPKIPin)
        EngineConfig.storeHost(result.apiRoot.absoluteString)
        // Reset the failover endpoint set to just this newly paired endpoint
        // (#3098): a fresh pairing establishes THE paired host, so a previous
        // Mac's endpoints must not linger and be walked during a later failover.
        PairedHostEndpointStore.clear()
        PairedHostEndpointStore.record(result.apiRoot)
        if let libraryPath = normalizedLibraryPath(libraryPath) {
            EngineConfig.defaults.set(libraryPath, forKey: RemoteAccessConfig.pairedLibraryPathKey)
        } else {
            EngineConfig.defaults.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey)
        }
    }

    @MainActor
    static func probeRemoteHealth(at apiRoot: URL, expectedSPKIPin: String? = nil) async throws {
        let client = try FicheroClient(baseURL: apiRoot, expectedSPKIPin: expectedSPKIPin)

        let response = try await client.api.healthCheckApiHealthGet(.init())
        switch response {
        case .ok(let okResponse):
            let health = try okResponse.body.json
            guard isAcceptableHealthStatus(health.status) else {
                throw APIError.badRequest("Remote host health check failed.")
            }
            // #5047: a healthy engine we cannot speak to is still unusable. This
            // probe is remote by definition, so the check always applies here —
            // unlike the app's own health check, where an embedded engine always
            // matches its app by construction.
            if let mismatch = ContractCompatibility.mismatch(engine: health.contract) {
                throw RemoteClientPairingError.contractMismatch(
                    headline: mismatch.headline,
                    detail: mismatch.detail
                )
            }
        default:
            throw APIError.httpError(statusCode: -1, message: "API returned error status")
        }
    }

    /// Pairs and persists through the ONE sequence (`PairingSequence`): the Mac and the phone both come here, so their checks are
    /// the same, in the same order: try the link's addresses, refuse a contract this app cannot read before any code is sent,
    /// redeem the code, keep the token (or revoke), confirm the project against the host's own list, then persist.
    /// A link with no project asks the host which it shares (`sharing.ios-bad-library-path`).
    @MainActor
    static func pairAndPersistHost(
        remoteURL: String,
        pairCode: String,
        deviceName: String,
        expectedSPKIPin: String?,
        libraryPath: String? = nil,
        person: PairingPerson? = nil,
        altURLs: [String] = []
    ) async throws -> URL {
        let code = pairCode.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let name = deviceName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !code.isEmpty || person != nil else { throw RemoteClientPairingError.personRequired }
        guard !name.isEmpty else { throw RemoteClientPairingError.missingDeviceName }
        let normalizedSPKIPin = try expectedSPKIPin.map(RemoteCertificatePinning.validatedSPKIPin)
        let host = LivePairingHost(spkiPin: normalizedSPKIPin, deviceName: name, person: person)
        let link = PairingSequence.Link(
            addresses: [remoteURL] + altURLs, code: code, libraryPath: normalizedLibraryPath(libraryPath))
        let outcome = await PairingSequence.run(
            link: link, host: host, ownContract: LivePairingHost.contractMatches,
            ownVersion: ContractCompatibility.appIdentity.version)
        switch outcome {
        case .paired(_, let confirmedLibrary):
            guard let exchange = host.exchange else { throw PairingStoppedError(message: PairingFailure.noAnswer.sentence()) }
            let pin = try resolvedSPKIPin(normalizedSPKIPin, for: exchange.apiRoot)
            try persistPairedHost(exchange, expectedSPKIPin: pin, libraryPath: confirmedLibrary)
            PairedMachineStore.record(apiRoot: exchange.apiRoot, library: confirmedLibrary)
            return exchange.apiRoot
        case .choose:
            // ponytail: no picker yet; the person asks for a link from the project they want.
            throw PairingStoppedError(message: "That Mac shares more than one project and the link did not say which. "
                                      + "Ask for a new link from the project you want.")
        case .failed(.personRequired, _):
            throw RemoteClientPairingError.personRequired
        case .failed(let failure, var context):
            context.noun = RemoteClientPairingError.deviceNoun
            throw PairingFailureError(failure: failure, context: context)
        case .stopped(let message):
            throw PairingStoppedError(message: message)
        }
    }

    /// Keeps the device token, or undoes the pairing it belongs to (`sharing.failed-save-spends-nothing`).
    ///
    /// The host spends the code and makes the device row BEFORE it answers, so a token the Keychain refuses would
    /// leave a device on the host that nobody holds a key for, and a code the person cannot use again. When the save
    /// fails, the token is used once more, in memory only, to ask the host to revoke this very device
    /// (`POST /api/pair/devices/revoke-self`, #6133), then dropped; the person reads `tokenNotSaved`, the OSStatus goes
    /// to the log. `persist` and `revoke` are injectable so a test can refuse the save without a Keychain.
    @MainActor
    static func storeTokenOrRevoke(
        _ result: PairingExchangeResult,
        expectedSPKIPin: String?,
        persist: (String, URL) throws -> Void = { try PairingService.persistAuthToken($0, for: $1) },
        revoke: ((FicheroClient) async -> Bool)? = nil
    ) async throws {
        do {
            try persist(result.deviceToken, result.apiRoot)
        } catch {
            // One literal: OSLogMessage cannot be concatenated with `+` (a Mac compile error).
            logger.error("""
                Pairing: the device token could not be saved (\(String(describing: error), privacy: .public)); \
                revoking the device on the host
                """)
            let host = result.apiRoot.absoluteString
            AuthTokenMiddleware.holdTransientRemoteToken(result.deviceToken, hostString: host)
            defer { AuthTokenMiddleware.dropTransientRemoteToken(hostString: host) }
            if let client = try? FicheroClient(baseURL: result.apiRoot, expectedSPKIPin: expectedSPKIPin) {
                let revoked: Bool
                if let revoke { revoked = await revoke(client) } else { revoked = await revokeOwnPairing(client: client) }
                if !revoked { logger.warning("Pairing: the host did not revoke the unsaved device") }
            }
            throw RemoteClientPairingError.tokenNotSaved
        }
    }
}
