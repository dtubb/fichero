import Foundation

#if canImport(UIKit) && !os(macOS)
import UIKit
#endif

struct RemoteClientPairingFields: Equatable {
    let remoteURL: String
    let pairCode: String
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
    static func defaultDeviceName() -> String {
        #if canImport(UIKit) && !os(macOS)
        return UIDevice.current.name
        #else
        return Host.current().localizedName ?? ProcessInfo.processInfo.hostName
        #endif
    }

    static func pairingFields(from message: String) throws -> RemoteClientPairingFields {
        let payload = try PairingQRCodePayloadDecoder.decode(message: message)
        let validatedURL = try validatedRemoteURL(from: payload.apiURL, allowLocalhost: false)
        return RemoteClientPairingFields(
            remoteURL: validatedURL.absoluteString,
            pairCode: payload.pairCode
        )
    }

    @MainActor
    static func pairAndPersistHost(remoteURL: String, pairCode: String, deviceName: String) async throws -> URL {
        let code = pairCode.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let name = deviceName.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !code.isEmpty else {
            throw RemoteClientPairingError.missingPairCode
        }
        guard !name.isEmpty else {
            throw RemoteClientPairingError.missingDeviceName
        }

        let url = try validatedRemoteURL(from: remoteURL, allowLocalhost: false)
        let response = try await PairingService(apiRoot: url).pairDevice(code: code, deviceName: name)
        try PairingService.persistAuthToken(response.deviceToken, for: url)
        UserDefaults.standard.set(url.absoluteString, forKey: EngineConfig.userDefaultsKey)
        return url
    }
}
