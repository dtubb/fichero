import FicheroAPIClient
import Foundation

#if canImport(UIKit) && !os(macOS)
import UIKit
#endif

struct RemoteClientPairingFields: Equatable {
    let remoteURL: String
    let pairCode: String
    let spkiPin: String
}

enum RemoteClientPairingError: LocalizedError, Equatable {
    case missingPairCode
    case missingDeviceName

    var errorDescription: String? {
        switch self {
        case .missingPairCode:
            return "Scan the pairing QR code or enter a pairing code."
        case .missingDeviceName:
            return "Enter a device name."
        }
    }
}

enum RemoteClientPairing {
    static func isAcceptableHealthStatus(_ status: String) -> Bool {
        let normalized = status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "healthy" || normalized == "ok"
    }

    static func defaultDeviceName() -> String {
        #if canImport(UIKit) && !os(macOS)
        return UIDevice.current.name
        #else
        return Host.current().localizedName ?? ProcessInfo.processInfo.hostName
        #endif
    }

    static func pairingFields(from message: String) throws -> RemoteClientPairingFields {
        let payload = try PairingQRCodePayloadDecoder.decode(message: message)
        let validatedURL = try validatedRemoteURL(
            from: payload.apiURL,
            allowLocalhost: false,
            requireSecureTransportForRemote: true
        )
        let validatedSPKIPin = try RemoteCertificatePinning.validatedSPKIPin(payload.spki)
        return RemoteClientPairingFields(
            remoteURL: validatedURL.absoluteString,
            pairCode: payload.pairCode,
            spkiPin: validatedSPKIPin
        )
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
        return PairingExchangeResult(apiRoot: url, deviceToken: response.deviceToken)
    }

    @MainActor
    static func persistPairedHost(_ result: PairingExchangeResult, expectedSPKIPin: String) throws {
        try PairingService.persistAuthToken(result.deviceToken, for: result.apiRoot)
        try RemoteCertificatePinning.persistSPKIPin(expectedSPKIPin)
        UserDefaults.standard.set(result.apiRoot.absoluteString, forKey: EngineConfig.userDefaultsKey)
    }

    static func probeRemoteHealth(at apiRoot: URL, expectedSPKIPin: String? = nil) async throws {
        let requestURL = apiRoot.appendingPathComponent("api/health")
        let session: URLSession
        if let expectedSPKIPin {
            session = try RemoteCertificatePinning.pinnedSession(expectedSPKIPin: expectedSPKIPin)
        } else {
            session = URLSession.shared
        }

        let (data, response) = try await session.data(from: requestURL)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? -1, message: "API returned error status")
        }

        struct HealthResponse: Decodable {
            let status: String
        }

        let health = try JSONDecoder().decode(HealthResponse.self, from: data)
        guard isAcceptableHealthStatus(health.status) else {
            throw APIError.badRequest("Remote host health check failed.")
        }
    }

    @MainActor
    static func pairAndPersistHost(
        remoteURL: String,
        pairCode: String,
        deviceName: String,
        expectedSPKIPin: String
    ) async throws -> URL {
        let result = try await pairDevice(
            remoteURL: remoteURL,
            pairCode: pairCode,
            deviceName: deviceName,
            expectedSPKIPin: expectedSPKIPin
        )
        try persistPairedHost(result, expectedSPKIPin: expectedSPKIPin)
        return result.apiRoot
    }
}
