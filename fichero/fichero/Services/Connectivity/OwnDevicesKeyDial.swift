import Foundation

/// `multiuser.remote-flow-no-pairing-code` (#2403): the dial by the synced key. Pure, with the network calls passed in.
/// With the key, each address of the own-devices item is tried in turn; a 401 is the same Mac refusing the key everywhere,
/// so the key dial stops and the enrollment secret is redeemed instead (`OwnDevicesConnect.connect`).
enum OwnDevicesKeyDial {
    enum Outcome: Equatable {
        case session(address: OwnDevicesItem.Address, token: String)
        case enrolled(OwnDevicesConnect.Enrolled)
    }

    /// `keySignIn` is nil when this device holds no synced key. Any error other than a 401 moves to the next address;
    /// when no address signs in by key, the enrolment runs and its own error is the one thrown.
    /// Runs on the caller's actor (`nonisolated(nonsending)`), so the caller's main-actor closures are never sent.
    nonisolated(nonsending) static func connect(
        _ item: OwnDevicesItem,
        deviceName: String,
        keySignIn: (nonisolated(nonsending) (OwnDevicesItem.Address) async throws -> String)?,
        enroll: nonisolated(nonsending) (OwnDevicesItem.Address, String, String) async throws -> (token: String, expiresAt: Date)
    ) async throws -> Outcome {
        if let keySignIn {
            dial: for address in OwnDevicesItem.ordered(item.addresses) {
                do {
                    return .session(address: address, token: try await keySignIn(address))
                } catch SignInRefusal.refused(statusCode: 401) {
                    break dial
                } catch {
                    continue
                }
            }
        }
        return .enrolled(try await OwnDevicesConnect.connect(item, deviceName: deviceName, enroll: enroll))
    }
}
