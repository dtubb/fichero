import FicheroAPIClient
import Foundation

/// The real host behind `PairingSequence`: the existing steps (health with the contract check, the unauthenticated pair, the
/// Keychain save that revokes on a refusal, the accessible-library list), one call each, in the order the sequence asks. A Mac and a
/// phone both pair through `RemoteClientPairing.pairAndPersistHost`, which runs the sequence on this host, so their checks cannot
/// differ (`sharing.both-clients-run-the-same-checks`).
@MainActor
final class LivePairingHost: PairingSequence.Host {
    /// What `health` reports as the contract when the engine's matches this app's; the sequence compares it with `contractMatches`.
    static let contractMatches = "matches this app"

    private let spkiPin: String?
    private let deviceName: String
    private let person: PairingPerson?
    /// The exchange the pair step made, kept for the caller to persist once the sequence says paired.
    private(set) var exchange: PairingExchangeResult?

    init(spkiPin: String?, deviceName: String, person: PairingPerson?) {
        self.spkiPin = spkiPin
        self.deviceName = deviceName
        self.person = person
    }

    func health(at url: String) async -> (failure: PairingFailure?, health: PairingSequence.HostHealth?) {
        let name = PairingAddressTry.host(url)
        do {
            let root = try validatedRemoteURL(from: url, allowLocalhost: false, requireSecureTransportForRemote: true)
            let pin = try RemoteClientPairing.resolvedSPKIPin(spkiPin, for: root)
            let client = try FicheroClient(baseURL: root, expectedSPKIPin: pin)
            let response = try await client.api.healthCheckApiHealthGet(.init())
            guard case .ok(let okResponse) = response else { return (.refused, nil) }
            let health = try okResponse.body.json
            guard RemoteClientPairing.isAcceptableHealthStatus(health.status) else { return (.refused, nil) }
            let mismatch = ContractCompatibility.mismatch(engine: health.contract)
            return (nil, PairingSequence.HostHealth(
                contract: mismatch == nil ? Self.contractMatches : "differs",
                version: health.contract?.version ?? health.backendVersion))
        } catch is RemoteCertificatePinningError {
            return (.certificatePin, nil)
        } catch {
            return (Self.failure(from: error, host: name), nil)
        }
    }

    func pair(at url: String, code: String) async throws {
        let root = try validatedRemoteURL(from: url, allowLocalhost: false, requireSecureTransportForRemote: true)
        let pin = try RemoteClientPairing.resolvedSPKIPin(spkiPin, for: root)
        let result: PairingExchangeResult
        do {
            result = try await RemoteClientPairing.pairDevice(
                remoteURL: url, pairCode: code, deviceName: deviceName, expectedSPKIPin: pin, person: person)
        } catch RemoteClientPairingError.personRequired {
            throw PairingFailure.personRequired
        } catch let APIError.httpError(statusCode, message) {
            if let failure = PairingFailure.from(status: statusCode, detail: message) { throw failure }
            throw APIError.httpError(statusCode: statusCode, message: message)
        }
        // The token is saved now (or the device revoked and the person told, `sharing.failed-save-spends-nothing`): the library
        // call that follows needs it in the Keychain.
        try await RemoteClientPairing.storeTokenOrRevoke(result, expectedSPKIPin: pin)
        exchange = result
    }

    func libraries(at url: String) async throws -> [String] {
        guard let exchange else { return [] }
        let pin = try RemoteClientPairing.resolvedSPKIPin(spkiPin, for: exchange.apiRoot)
        return try await PairingService(apiRoot: exchange.apiRoot, expectedSPKIPin: pin).accessibleLibraryPaths()
    }

    func discardPairing(at url: String) async {
        if let exchange { AuthTokenMiddleware.clearRemoteToken(hostString: exchange.apiRoot.absoluteString) }
        exchange = nil
    }

    /// A transport failure as its step: the `URLError` code is found wherever the generated client wrapped it.
    nonisolated static func failure(from error: Error, host: String) -> PairingFailure {
        var current: NSError? = error as NSError
        while let next = current {
            if next.domain == NSURLErrorDomain { return PairingFailure.from(urlErrorCode: next.code, host: host) }
            current = next.userInfo[NSUnderlyingErrorKey] as? NSError
        }
        return .noAnswer
    }
}

/// A pairing step refused: the sentence is the failure table's (`PairingFailure`), never a code.
struct PairingFailureError: LocalizedError {
    let failure: PairingFailure
    let context: PairingFailure.Context
    var errorDescription: String? { failure.sentence(context) }
}

/// A pairing stopped by something that already said why in words (the Keychain refusal, the host shares several projects).
struct PairingStoppedError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
