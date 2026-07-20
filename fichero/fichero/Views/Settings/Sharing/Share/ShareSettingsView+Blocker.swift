#if canImport(AppKit)
import SwiftUI

extension ShareSettingsView {
    // MARK: - Blocker

    /// Why the pairing card cannot show a QR right now — each precondition named
    /// honestly, in the order it must hold (#3776/#3769).
    var pairingBlocker: PairingBlocker? {
        guard EngineConfig.engineIsLocal else { return .engineIsRemote }
        guard appState.isBackendRunning else { return .engineNotRunning }
        guard hostingEnabled else { return .sharingNotStarted }

        do {
            _ = try validatedHostedRemoteURL(from: publicBaseURL)
        } catch let error as RemoteURLValidationError {
            switch error {
            case .blank: return .addressMissing
            case .insecureRemoteTransport: return .addressInsecure
            default: return .addressInvalid(error.localizedDescription)
            }
        } catch {
            return .addressInvalid(error.localizedDescription)
        }

        // The pin is derived, not typed — and the derivation is optional. If it comes
        // back nil the card used to go blank, which is the very disease #3769 is
        // about. The app CAN fix this itself: restarting the engine mints the TLS
        // material and re-derives the pin.
        guard hasValidSPKIPin else { return .pinNotDerived }
        return nil
    }

    /// Perform the blocker's own cure. Only offered where the app can genuinely do
    /// the setup itself — the whole point of the design is that it does, rather than
    /// telling the user to go and do it.
    func resolve(_ blocker: PairingBlocker) async {
        switch blocker {
        case .engineNotRunning:
            isApplyingChange = true
            shareError = nil
            defer { isApplyingChange = false }
            do {
                try await backendService.start()
            } catch {
                shareError = error.localizedDescription
            }
            loadSPKIPin()
        case .sharingNotStarted:
            hostingEnabled = true
            bonjourEnabled = true
            if publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                publicBaseURL = Self.autoLocalBaseURL
            }
            await applySharing()
        case .engineIsRemote, .addressMissing, .addressInsecure, .addressInvalid, .pinNotDerived:
            break  // no button offered — see PairingBlocker.actionTitle
        }
    }
}
#endif
