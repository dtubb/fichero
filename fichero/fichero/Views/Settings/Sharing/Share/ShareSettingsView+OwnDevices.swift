#if canImport(AppKit)
import SwiftUI

extension ShareSettingsView {
    var ownDevicesBinding: Binding<Bool> {
        Binding(
            get: { ownDevicesOn },
            set: { newValue in
                guard newValue != ownDevicesOn else { return }
                Task { await publishOwnDevices(newValue) }
            }
        )
    }

    /// On: the engine mints a new secret and the Mac writes the iCloud Keychain item (rewritten when an address changes).
    /// Off: the engine retires the secret and the item is deleted. A failure leaves the switch as it was, with the reason.
    func publishOwnDevices(_ enabled: Bool) async {
        isApplyingChange = true
        defer { isApplyingChange = false }
        do {
            let result = try await PairingService(apiRoot: EngineConfig.host).setOwnDevices(enabled: enabled)
            let keychain = OwnDevicesKeychain()
            if enabled, let secret = result.secret {
                let item = OwnDevicesItem.make(
                    engineID: result.engineID, macName: Host.current().localizedName ?? ProcessInfo.processInfo.hostName,
                    secret: secret, tailnetURL: sharingState?.tailnetURL ?? detectedTailnetURL,
                    own: .init(url: publicBaseURL, spki: spkiPin))
                try keychain.write(item)
            } else {
                try keychain.delete(engineID: result.engineID)
            }
            OwnDevicesSwitch.remember(enabled)
            ownDevicesOn = enabled
        } catch {
            showFailure(error, "Couldn't change sign-in for your own devices")
        }
    }
}
#endif
