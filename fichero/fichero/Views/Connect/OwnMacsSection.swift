#if os(iOS) || os(visionOS)
import SwiftUI

/// "Your Macs" (`signin.own.ios-finds-it-and-connects`, #6568): the Macs whose own-devices item this Apple ID holds. One tap
/// signs this device in by itself; nothing is typed. Absent when no item is found, so the other methods show alone.
struct OwnMacsSection: View {
    let macs: [OwnDevicesItem]
    let isConnecting: Bool
    let onSelect: (OwnDevicesItem) -> Void

    var body: some View {
        if !macs.isEmpty {
            Section {
                ForEach(macs, id: \.engineID) { mac in
                    Button { onSelect(mac) } label: {
                        Label {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(mac.macName)
                                Text(OwnDevicesItem.ordered(mac.addresses).first?.url ?? "")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "desktopcomputer").foregroundStyle(Color.accentColor)
                        }
                    }
                    .disabled(isConnecting)
                }
            } header: {
                Text("Your Macs")
            }
        }
    }
}
#endif

#if os(iOS) || os(visionOS)
/// Reads the Keychain items on launch and each time the app comes to the front.
private struct OwnMacsLoading: ViewModifier {
    @Binding var macs: [OwnDevicesItem]
    @Binding var error: String?
    @Environment(\.scenePhase) private var scenePhase

    func body(content: Content) -> some View {
        content.task(id: scenePhase) {
            guard scenePhase == .active else { return }
            do { macs = try OwnDevicesKeychain().readAll() } catch {
                self.error = "Could not read your Macs from iCloud Keychain (\(error))."
            }
        }
    }
}

extension View {
    func ownMacsLoading(into macs: Binding<[OwnDevicesItem]>, error: Binding<String?>) -> some View {
        modifier(OwnMacsLoading(macs: macs, error: error))
    }
}

extension RemoteConnectionSetupView {
    /// One tap on a row: enrol this device with that Mac and open the library, as a pairing does.
    func connectOwnMac(_ mac: OwnDevicesItem) {
        Task {
            isPairing = true
            errorMessage = nil
            defer { isPairing = false }
            do {
                _ = try await RemoteClientPairing.enrollOwnMac(mac, deviceName: RemoteClientPairing.defaultDeviceName())
                appState.reconfigureGeneratedClientsForCurrentHost()
                await onConnected()
                if !appState.isBackendRunning { errorMessage = "Connected — Fichero on your Mac is not responding yet." }
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}
#endif
