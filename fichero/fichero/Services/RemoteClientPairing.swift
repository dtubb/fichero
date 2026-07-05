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

enum RemoteClientPairingError: LocalizedError, Equatable {
    case missingPairCode
    case missingDeviceName
    case missingLibraryPath
    case invalidInviteLink

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
              url.scheme?.lowercased() == PairingInviteLink.scheme,
              url.host?.lowercased() == PairingInviteLink.host,
              let encodedPayload = queryValue(named: PairingInviteLink.payloadQueryItem, in: url),
              let data = Data(base64Encoded: encodedPayload),
              let payload = try? JSONDecoder.withISO8601Dates.decode(PairingQRCodePayload.self, from: data) else {
            return nil
        }
        return payload
    }

    private static func looksLikeInviteLink(_ message: String) -> Bool {
        guard let url = URL(string: message) else { return false }
        return url.scheme?.lowercased() == PairingInviteLink.scheme
            && url.host?.lowercased() == PairingInviteLink.host
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
        try persistPairedHost(result, expectedSPKIPin: expectedSPKIPin, libraryPath: libraryPath)
        return result.apiRoot
    }

    @MainActor
    static func rollbackFailedHostSwitch(previousHost: String, attemptedHost: URL) {
        AuthTokenMiddleware.clearRemoteToken(hostString: attemptedHost.absoluteString)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: attemptedHost.absoluteString)
        DeviceTokenRenewal.clearExpiry(host: attemptedHost.absoluteString)
        UserDefaults.standard.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey)
        UserDefaults.standard.set(previousHost, forKey: EngineConfig.userDefaultsKey)
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
