import Foundation

/// Why the pairing card cannot show a QR, as a value rather than a lone string
/// (#3776/#3769). Each case carries its OWN headline — the card no longer prints
/// "Secure sharing needs HTTPS" over a stopped engine — and its own cure, so a
/// blocker is never a dead end. Non-negotiable: never a blank space, never a
/// dead control; if we cannot proceed, say why and offer the fix.
enum PairingBlocker: Equatable {
    /// The library is served by an engine on ANOTHER machine, so this Mac has
    /// nothing to share. Nothing the app can do here — that is honest, not a dead end.
    case engineIsRemote
    /// The engine on this Mac is not running. The app can start it.
    case engineNotRunning
    /// Sharing has not been started yet. The app can start it — the user does not
    /// "enable a subsystem" first, they just share.
    case sharingNotStarted
    /// No reachable address for this Mac yet. Sharing derives one automatically
    /// (`https://<hostname>.local:<port>`), so this should be unreachable in
    /// practice — it only appears if someone cleared the address under Advanced.
    case addressMissing
    case addressInsecure
    case addressInvalid(String)
    /// The SPKI pin could not be derived. This is the trap: the pin is computed,
    /// not typed, and the derivation is optional — a nil used to blank the card.
    /// Restarting the engine mints the TLS material and derives it.
    case pinNotDerived
    /// The same, on an engine this app did not start (Dev Local): restarting sharing cannot mint a pin there (#5891).
    case pinNotDerivedOnExternalEngine

    /// The headline. Each cause names ITSELF.
    var headline: String {
        switch self {
        case .engineIsRemote: return "This project is hosted on another machine"
        case .engineNotRunning: return "Fichero's engine isn't running"
        case .sharingNotStarted: return "Sharing hasn't started yet"
        case .addressMissing: return "Fichero needs this Mac's address"
        case .addressInsecure: return "Sharing needs HTTPS"
        case .addressInvalid: return "That address doesn't work"
        case .pinNotDerived: return "Preparing the security certificate"
        case .pinNotDerivedOnExternalEngine: return "No security certificate for this address"
        }
    }

    var detail: String {
        switch self {
        case .engineIsRemote:
            return "Sharing happens on the Mac that hosts the project. This one is connected to an engine elsewhere."
        case .engineNotRunning:
            return "The QR code needs a running engine to pair against."
        case .sharingNotStarted:
            return "Turn sharing on and Fichero will prepare the address, the certificate and the invite for you."
        case .addressMissing:
            return "Fichero normally works this out itself. Restore the automatic address under Advanced."
        case .addressInsecure:
            return "Devices pair over HTTPS so the connection can be pinned. Restore the automatic address under Advanced."
        case .addressInvalid(let reason):
            return reason
        case .pinNotDerivedOnExternalEngine:
            return "This engine was started outside Fichero, so Fichero can't make its certificate pin; "
                + "restarting sharing here would change nothing. Start the engine from Fichero, or give it the pin."
        case .pinNotDerived:
            return "Fichero has no certificate pin filed for this address yet. Making the link restarts "
                + "sharing, which mints it; any work running in the engine is stopped, so do it when nothing is running."
        }
    }

    /// The button — present ONLY where the app can genuinely perform the cure
    /// itself. nil where it honestly cannot (a remote engine; an address only the
    /// user knows), and then the detail says exactly what to do instead.
    var actionTitle: String? {
        switch self {
        case .engineNotRunning: return "Start Server"
        case .sharingNotStarted: return "Turn On Sharing"
        // The pin is normally minted when sharing turns on; when it is missing anyway the cure restarts the
        // engine, which stops work in flight, so it is a button the person presses, never automatic (#5891).
        case .pinNotDerived: return "Make a Pairing Link"
        case .engineIsRemote, .addressMissing, .addressInsecure, .addressInvalid, .pinNotDerivedOnExternalEngine:
            return nil
        }
    }
}
