import FicheroAPIClient
import Foundation
#if canImport(UIKit)
import UIKit
#endif

struct RemoteClientPairingFields: Equatable {
    let remoteURL: String
    let pairCode: String
    let spkiPin: String
    let libraryPath: String
}

private struct PairingInviteLink {
    static let scheme = "fichero"
    static let host = "pair"
    static let payloadQueryItem = "payload"

    static let queryValueAllowedCharacters: CharacterSet = {
        var allowed = CharacterSet.urlQueryAllowed
        allowed.remove(charactersIn: "+/=")
        return allowed
    }()
}

/// The universal-link form of a pairing invite (#3791): `https://fichero.app/pair?payload=…`.
/// Same `payload` query as the custom-scheme link — the domain is only a name
/// the app claims via Associated Domains so a tapped link resolves even where the
/// `fichero://` scheme isn't registered (e.g. Mail on a colleague's device). The
/// token is still redeemed peer-to-peer against the host in the payload, never
/// against the domain.
private struct PairingUniversalLink {
    static let scheme = "https"
    static let host = "fichero.app"
    static let path = "/pair"
}

enum RemoteClientPairingError: LocalizedError, Equatable {
    case missingPairCode
    case missingDeviceName
    case missingLibraryPath
    case invalidInviteLink
    case libraryPathNotConfirmed

    var errorDescription: String? {
        switch self {
        case .missingPairCode:
            return "Scan the pairing QR code or enter a pairing code."
        case .missingDeviceName:
            return "Enter a device name."
        case .missingLibraryPath:
            return "This QR code does not include a shared library. Show a new QR code on the Mac."
        case .invalidInviteLink:
            return "The invite link is incomplete or invalid."
        case .libraryPathNotConfirmed:
            return "The Mac did not confirm access to the library named in this QR code. "
                + "Show a fresh QR code on the Mac and scan it again."
        }
    }
}

enum RemoteClientPairing {
    static func isAcceptableHealthStatus(_ status: String) -> Bool {
        let normalized = status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "healthy" || normalized == "ok"
    }

    @MainActor
    static func defaultDeviceName() -> String {
        #if canImport(UIKit)
        return UIDevice.current.name
        #else
        return Host.current().localizedName ?? ProcessInfo.processInfo.hostName
        #endif
    }

    static func pairingFields(from message: String) throws -> RemoteClientPairingFields {
        let payload = try PairingQRCodePayloadDecoder.decode(message: message)
        return try pairingFields(from: payload)
    }

    static func pairingFields(fromInviteOrPayload message: String) throws -> RemoteClientPairingFields {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        if looksLikeInviteLink(trimmed) {
            guard let payload = payloadFromInviteLink(trimmed) else {
                throw RemoteClientPairingError.invalidInviteLink
            }
            return try pairingFields(from: payload)
        }
        return try pairingFields(from: trimmed)
    }

    static func inviteLinkString(from payload: PairingQRCodePayload) throws -> String {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(payload)
        let encodedPayload = data.base64EncodedString().addingPercentEncoding(
            withAllowedCharacters: PairingInviteLink.queryValueAllowedCharacters
        ) ?? data.base64EncodedString()
        let prefix = "\(PairingInviteLink.scheme)://\(PairingInviteLink.host)"
        return "\(prefix)?\(PairingInviteLink.payloadQueryItem)=\(encodedPayload)"
    }

    static func pairingFields(from payload: PairingQRCodePayload) throws -> RemoteClientPairingFields {
        let validatedURL = try validatedRemoteURL(
            from: payload.apiURL,
            allowLocalhost: false,
            requireSecureTransportForRemote: true
        )
        let validatedSPKIPin = try RemoteCertificatePinning.validatedSPKIPin(payload.spki)
        guard let libraryPath = normalizedLibraryPath(payload.libraryPath) else {
            throw RemoteClientPairingError.missingLibraryPath
        }
        return RemoteClientPairingFields(
            remoteURL: validatedURL.absoluteString,
            pairCode: payload.pairCode,
            spkiPin: validatedSPKIPin,
            libraryPath: libraryPath
        )
    }

    private static func payloadFromInviteLink(_ message: String) -> PairingQRCodePayload? {
        guard let url = URL(string: message),
              isPairingInviteLink(url),
              let encodedPayload = queryValue(named: PairingInviteLink.payloadQueryItem, in: url),
              let data = Data(base64Encoded: encodedPayload),
              let payload = try? JSONDecoder.withISO8601Dates.decode(PairingQRCodePayload.self, from: data) else {
            return nil
        }
        return payload
    }

    private static func looksLikeInviteLink(_ message: String) -> Bool {
        guard let url = URL(string: message) else { return false }
        return isPairingInviteLink(url)
    }

    /// Whether `url` is a pairing invite in EITHER form — the custom
    /// `fichero://pair` scheme or the `https://fichero.app/pair` universal link
    /// (#3791). The app's `onOpenURL` handlers route on this so both forms reach
    /// the same pairing flow. Public within the target so `FicheroApp` can call it.
    static func isPairingInviteLink(_ url: URL) -> Bool {
        isCustomSchemeInvite(url) || isUniversalLinkInvite(url)
    }

    private static func isCustomSchemeInvite(_ url: URL) -> Bool {
        url.scheme?.lowercased() == PairingInviteLink.scheme
            && url.host?.lowercased() == PairingInviteLink.host
    }

    private static func isUniversalLinkInvite(_ url: URL) -> Bool {
        url.scheme?.lowercased() == PairingUniversalLink.scheme
            && url.host?.lowercased() == PairingUniversalLink.host
            && url.path.lowercased() == PairingUniversalLink.path
    }

    private static func queryValue(named name: String, in url: URL) -> String? {
        guard let query = url.query else { return nil }
        for pair in query.split(separator: "&") {
            let parts = pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            guard parts.count == 2, parts[0] == name else { continue }
            let rawValue = String(parts[1])
            return rawValue.removingPercentEncoding ?? rawValue
        }
        return nil
    }

    static func pairDevice(
        remoteURL: String,
        pairCode: String,
        deviceName: String,
        expectedSPKIPin: String
    ) async throws -> PairingExchangeResult {
        let code = pairCode.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let name = deviceName.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !code.isEmpty else {
            throw RemoteClientPairingError.missingPairCode
        }
        guard !name.isEmpty else {
            throw RemoteClientPairingError.missingDeviceName
        }

        let url = try validatedRemoteURL(
            from: remoteURL,
            allowLocalhost: false,
            requireSecureTransportForRemote: true
        )
        let normalizedSPKIPin = try RemoteCertificatePinning.validatedSPKIPin(expectedSPKIPin)
        let response = try await PairingService(apiRoot: url, expectedSPKIPin: normalizedSPKIPin)
            .pairDeviceUnauthenticated(code: code, deviceName: name)
        return PairingExchangeResult(
            apiRoot: url,
            deviceToken: response.deviceToken,
            expiresAt: response.expiresAt
        )
    }

    @MainActor
    static func persistPairedHost(
        _ result: PairingExchangeResult,
        expectedSPKIPin: String,
        libraryPath: String?
    ) throws {
        try PairingService.persistAuthToken(result.deviceToken, for: result.apiRoot)
        try RemoteCertificatePinning.persistSPKIPin(expectedSPKIPin, hostString: result.apiRoot.absoluteString)
        // Record the token's expiry so renewal can fire before it lapses (#3096).
        DeviceTokenRenewal.storeExpiry(result.expiresAt, host: result.apiRoot.absoluteString)
        UserDefaults.standard.set(result.apiRoot.absoluteString, forKey: EngineConfig.userDefaultsKey)
        // Reset the failover endpoint set to just this newly paired endpoint
        // (#3098): a fresh pairing establishes THE paired host, so a previous
        // Mac's endpoints must not linger and be walked during a later failover.
        PairedHostEndpointStore.clear()
        PairedHostEndpointStore.record(result.apiRoot)
        if let libraryPath = normalizedLibraryPath(libraryPath) {
            UserDefaults.standard.set(libraryPath, forKey: RemoteAccessConfig.pairedLibraryPathKey)
        } else {
            UserDefaults.standard.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey)
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
        default:
            throw APIError.httpError(statusCode: -1, message: "API returned error status")
        }
    }

    @MainActor
    static func pairAndPersistHost(
        remoteURL: String,
        pairCode: String,
        deviceName: String,
        expectedSPKIPin: String,
        libraryPath: String? = nil
    ) async throws -> URL {
        let result = try await pairDevice(
            remoteURL: remoteURL,
            pairCode: pairCode,
            deviceName: deviceName,
            expectedSPKIPin: expectedSPKIPin
        )
        let normalizedSPKIPin = try RemoteCertificatePinning.validatedSPKIPin(expectedSPKIPin)
        // #3372: the QR/deep-link carries `libraryPath`, but that value is
        // attacker-supplied — nothing in the exchange so far proves the Mac
        // actually shares it with this device. Confirm it against the server's
        // own accessible-library set (GET /api/authz/libraries) BEFORE persisting
        // it, so a forged path can never be written to disk. The authenticated
        // confirm call needs the device token in the Keychain, so persist the
        // token first; if confirmation fails, clear it — never leave a
        // half-persisted pairing behind.
        try PairingService.persistAuthToken(result.deviceToken, for: result.apiRoot)
        do {
            try await confirmLibraryAccess(
                libraryPath: libraryPath,
                apiRoot: result.apiRoot,
                expectedSPKIPin: normalizedSPKIPin
            )
        } catch {
            AuthTokenMiddleware.clearRemoteToken(hostString: result.apiRoot.absoluteString)
            throw error
        }
        try persistPairedHost(result, expectedSPKIPin: expectedSPKIPin, libraryPath: libraryPath)
        return result.apiRoot
    }

    /// #3372: verify the paired credential can actually access `libraryPath`
    /// before it is persisted. A `nil`/empty advertised path (manual host entry,
    /// no library on the QR) has nothing to confirm — the library picker, which
    /// hits the same endpoint, gates access later. When a path IS advertised it
    /// must appear in the server's accessible-library set or pairing is rejected.
    @MainActor
    static func confirmLibraryAccess(
        libraryPath: String?,
        apiRoot: URL,
        expectedSPKIPin: String
    ) async throws {
        guard normalizedLibraryPath(libraryPath) != nil else { return }
        let accessible = try await PairingService(apiRoot: apiRoot, expectedSPKIPin: expectedSPKIPin)
            .accessibleLibraryPaths()
        guard isLibraryConfirmed(advertised: libraryPath, in: accessible) else {
            throw RemoteClientPairingError.libraryPathNotConfirmed
        }
    }

    /// Pure decision: is the QR-advertised `advertised` library among the paths
    /// the server says this credential may access? A `nil`/empty advertised path
    /// is treated as "nothing to confirm" (true). Kept separate so the security
    /// decision is unit-testable without a live server (#3372).
    static func isLibraryConfirmed(advertised: String?, in accessible: [String]) -> Bool {
        guard let advertised = normalizedLibraryPath(advertised) else { return true }
        return accessible.contains { libraryPathsMatch($0, advertised) }
    }

    private static func libraryPathsMatch(_ lhs: String, _ rhs: String) -> Bool {
        func canonical(_ path: String) -> String {
            path.trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        }
        return canonical(lhs) == canonical(rhs)
    }

    @MainActor
    static func rollbackFailedHostSwitch(previousHost: String, attemptedHost: URL) {
        AuthTokenMiddleware.clearRemoteToken(hostString: attemptedHost.absoluteString)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: attemptedHost.absoluteString)
        DeviceTokenRenewal.clearExpiry(host: attemptedHost.absoluteString)
        UserDefaults.standard.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey)
        UserDefaults.standard.set(previousHost, forKey: EngineConfig.userDefaultsKey)
    }

    /// Forgets the current pairing so a broken connection is no longer a dead
    /// end (#3971): undoes each value `persistPairedHost` wrote — the device
    /// token, the pinned certificate, the token expiry, the failover endpoint
    /// set, the configured host, and the paired library path. Clearing the
    /// paired-library-path key is what lets `EngineConfig.iosLaunchPhase` return
    /// `.setupNeeded` again, so the caller can drive the app back to the QR /
    /// pairing screen without a delete-and-reinstall.
    @MainActor
    static func forgetPairing() {
        let hostString = EngineConfig.hostString
        AuthTokenMiddleware.clearRemoteToken(hostString: hostString)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostString)
        DeviceTokenRenewal.clearExpiry(host: hostString)
        PairedHostEndpointStore.clear()
        UserDefaults.standard.removeObject(forKey: EngineConfig.userDefaultsKey)
        UserDefaults.standard.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey)
    }

    private static func normalizedLibraryPath(_ path: String?) -> String? {
        let trimmed = path?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmed.isEmpty else { return nil }
        return trimmed
    }
}

private extension JSONDecoder {
    static var withISO8601Dates: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            guard let date = parseEngineDate(raw) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Cannot decode QR payload date: \(raw)"
                )
            }
            return date
        }
        return decoder
    }
}
