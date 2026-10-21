import Foundation

/// What the Add Device sheet shows (`sharing.settings.add-device-sheet`, #5928): the words and the one state it is in, apart from
/// the view, so they are tested without a window. No word about pins, certificates, HTTPS or restarting.
enum AddDeviceSheetModel {
    enum Phase: Equatable {
        /// The app prepares the address and certificate: a spinner and "Finishing setup…", nothing else.
        case finishing
        /// QR and code up, the link copyable.
        case ready
        /// A code but no link yet: Copy Link is disabled and the sheet says "Not ready yet".
        case notReady
        /// Setup needs a press: the one button "Finish Setup".
        case finishSetup
        /// The engine is not running: "Start".
        case start
        /// The one short line.
        case failed(String)
    }

    static func phase(blocker: PairingBlocker?, hasCode: Bool, hasLink: Bool, isWorking: Bool) -> Phase {
        if isWorking { return .finishing }
        switch blocker {
        case .engineNotRunning: return .start
        case .sharingNotStarted, .pinNotDerived: return .finishSetup
        case .engineIsRemote: return .failed("Sharing is set on the Mac that runs this project")
        case .addressMissing, .addressInsecure, .addressInvalid: return .failed("The address needs fixing under Advanced")
        case .pinNotDerivedOnExternalEngine: return .failed("This engine was started outside Fichero")
        case nil:
            guard hasCode else { return .finishing }
            return hasLink ? .ready : .notReady
        }
    }

    /// "482 913": the code in two groups so it reads aloud.
    static func codeText(_ code: String) -> String {
        let digits = code.filter { !$0.isWhitespace }
        guard digits.count > 3 else { return "Code \(digits)" }
        let mid = digits.index(digits.startIndex, offsetBy: digits.count / 2)
        return "Code \(digits[..<mid]) \(digits[mid...])"
    }

    /// "Expires in 10 min"; under a minute says so; past the time it says it is being renewed (never an expired time).
    static func expiresText(expiresAt: Date?, now: Date = Date()) -> String {
        guard let expiresAt else { return "Never expires" }
        let seconds = expiresAt.timeIntervalSince(now)
        if seconds <= 0 { return "Renewing…" }
        if seconds < 60 { return "Expires in under a minute" }
        return "Expires in \(Int((seconds / 60).rounded(.up))) min"
    }
}
