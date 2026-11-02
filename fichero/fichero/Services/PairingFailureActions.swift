import Foundation

/// What the phone's pairing sheet offers beside a failure's sentence (`sharing.ios-says-which-step`,
/// `sharing.ios-tailscale-not-on-the-phone`, Step 5.2): Try again, Copy details, and Open Tailscale where the name is the tailnet's.
/// Pure: the sheet only draws these, so the rules are tested without a window.
enum PairingFailureActions {
    enum Action: Hashable { case tryAgain, copyDetails, openTailscale, openSettings }

    /// The Tailscale app's own scheme, then the App Store page when it is not installed.
    static let tailscaleURL = "tailscale://"
    static let tailscaleStoreURL = "https://apps.apple.com/app/tailscale/id1470499037"

    /// A failure a second go can mend (a name, an answer, a network); not one that needs a new link or a person's change.
    static func canTryAgain(_ failure: PairingFailure) -> Bool {
        switch failure {
        case .invalidLink, .olderLink, .codeUsedOrExpired, .personRequired, .versionMismatch, .deviceForgotten, .certificatePin:
            return false
        case .nameNotFound, .tailnetNameNotFound, .noAnswer, .refused, .offline, .certificateName, .tailnetByNumber,
             .tooManyTries, .libraryNotGiven, .hostStopped:
            return true
        }
    }

    /// Copy details is always there; Open Tailscale only where Tailscale is the cure.
    static func actions(for failure: PairingFailure?, host: String = "") -> [Action] {
        guard let failure else { return [.copyDetails] }
        var out: [Action] = canTryAgain(failure) ? [.tryAgain] : []
        if failure == .tailnetNameNotFound { out.append(.openTailscale) }
        // A local address that does not answer reads as the missing Local Network permission (`LocalNetworkPolicy`).
        if LocalNetworkPolicy.explains(failure, host: host) { out.append(.openSettings) }
        out.append(.copyDetails)
        return out
    }

    static func title(_ action: Action) -> String {
        switch action {
        case .tryAgain: "Try again"
        case .copyDetails: "Copy details"
        case .openTailscale: "Open Tailscale"
        case .openSettings: LocalNetworkPolicy.buttonTitle
        }
    }

    /// The text Copy details puts on the pasteboard: the step, the sentence and the host, for a message to the person
    /// helping. Never the pairing code, a token or a pin.
    static func details(_ failure: PairingFailure, context: PairingFailure.Context) -> String {
        var lines = ["Fichero could not connect to \(context.host).", "Step \(failure.step): \(failure.sentence(context))"]
        if let theirs = context.hostVersion { lines.append("\(context.host) runs Fichero \(theirs).") }
        if let ours = context.thisVersion { lines.append("This device runs Fichero \(ours).") }
        return lines.joined(separator: "\n")
    }
}
