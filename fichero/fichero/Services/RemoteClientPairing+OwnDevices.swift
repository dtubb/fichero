import FicheroAPIClient
import Foundation

extension RemoteClientPairing {
    /// `signin.own.ios-finds-it-and-connects` (#6568) and `multiuser.remote-flow-no-pairing-code` (#2403): with the synced
    /// key, signs in by key at the item's addresses and keeps the session; without it, or when the Mac refuses the key,
    /// redeems the Mac's synced enrollment secret for this device's OWN token. Then keeps the host the way a pairing does.
    /// Nothing is typed.
    @MainActor
    static func enrollOwnMac(_ item: OwnDevicesItem, deviceName: String) async throws -> URL {
        let keySignIn: (nonisolated(nonsending) (OwnDevicesItem.Address) async throws -> String)?
            = try OwnerKeyStore().loadExisting().map { key in
            { (address: OwnDevicesItem.Address) async throws -> String in
                let url = try validatedRemoteURL(from: address.url, allowLocalhost: false, requireSecureTransportForRemote: true)
                let pin = try address.spki.map(RemoteCertificatePinning.validatedSPKIPin)
                let transport = GeneratedKeySignInTransport(client: try FicheroClient(baseURL: url, expectedSPKIPin: pin))
                return try await SyncedKeySignIn(transport: transport, key: key)
                    .signIn(deviceName: deviceName, host: ProcessInfo.processInfo.hostName)
            }
        }
        let outcome = try await OwnDevicesKeyDial.connect(item, deviceName: deviceName, keySignIn: keySignIn) { address, secret, name in
            let url = try validatedRemoteURL(from: address.url, allowLocalhost: false, requireSecureTransportForRemote: true)
            let pin = try address.spki.map(RemoteCertificatePinning.validatedSPKIPin)
            let service = try PairingService(apiRoot: url, expectedSPKIPin: pin)
            let response = try await service.enrollDeviceUnauthenticated(enrollmentSecret: secret, deviceName: name)
            return (response.deviceToken, response.expiresAt)
        }
        switch outcome {
        case .session(let address, let token):
            let url = try validatedRemoteURL(from: address.url, allowLocalhost: false, requireSecureTransportForRemote: true)
            let pin = try resolvedSPKIPin(address.spki.map(RemoteCertificatePinning.validatedSPKIPin), for: url)
            // ponytail: the session lasts the engine's SESSION_TTL (30 days) and nothing signs in again when it lapses;
            // tapping the Mac under "Your Macs" signs in by key again. Upgrade: re-run this dial on a 401, as
            // `DeviceTokenRenewal` renews a device token.
            try AuthTokenMiddleware.persistSessionToken(token, hostString: url.absoluteString)
            try persistPin(pin, for: url)
            persistAppHost(url, libraryPath: nil)
            return url
        case .enrolled(let enrolled):
            let url = try validatedRemoteURL(from: enrolled.address.url, allowLocalhost: false, requireSecureTransportForRemote: true)
            let pin = try resolvedSPKIPin(enrolled.address.spki.map(RemoteCertificatePinning.validatedSPKIPin), for: url)
            let result = PairingExchangeResult(apiRoot: url, deviceToken: enrolled.deviceToken, expiresAt: enrolled.expiresAt)
            try await storeTokenOrRevoke(result, expectedSPKIPin: pin)
            try persistPairedHost(result, expectedSPKIPin: pin, libraryPath: nil)
            return url
        }
    }
}
