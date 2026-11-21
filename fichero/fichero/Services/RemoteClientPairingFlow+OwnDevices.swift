import FicheroAPIClient
import Foundation

extension RemoteClientPairing {
    /// `signin.own.ios-finds-it-and-connects` (#6568): redeems the Mac's synced enrollment secret for this device's OWN token,
    /// dialling the item's addresses in turn, then keeps the token and the host the way a pairing does. Nothing is typed.
    @MainActor
    static func enrollOwnMac(_ item: OwnDevicesItem, deviceName: String) async throws -> URL {
        let enrolled = try await OwnDevicesConnect.connect(item, deviceName: deviceName) { address, secret, name in
            let url = try validatedRemoteURL(from: address.url, allowLocalhost: false, requireSecureTransportForRemote: true)
            let pin = try address.spki.map(RemoteCertificatePinning.validatedSPKIPin)
            let service = try PairingService(apiRoot: url, expectedSPKIPin: pin)
            let response = try await service.enrollDeviceUnauthenticated(enrollmentSecret: secret, deviceName: name)
            return (response.deviceToken, response.expiresAt)
        }
        let url = try validatedRemoteURL(from: enrolled.address.url, allowLocalhost: false, requireSecureTransportForRemote: true)
        let pin = try resolvedSPKIPin(enrolled.address.spki.map(RemoteCertificatePinning.validatedSPKIPin), for: url)
        let result = PairingExchangeResult(apiRoot: url, deviceToken: enrolled.deviceToken, expiresAt: enrolled.expiresAt)
        try await storeTokenOrRevoke(result, expectedSPKIPin: pin)
        try persistPairedHost(result, expectedSPKIPin: pin, libraryPath: nil)
        return url
    }
}
