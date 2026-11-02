import Foundation

/// Every way pairing or connecting to another Mac can fail, in the order the steps run, and the one sentence for each
/// (`sharing.failure-names-the-step`, sharing-two-macs.md §4). The person never sees a code or an enum: the sheets show
/// `sentence(...)`, and the raw `NSError` code goes to the log and to Copy details. One table, so a test can walk it.
enum PairingFailure: CaseIterable, Equatable {
    case invalidLink
    case olderLink
    case nameNotFound
    case tailnetNameNotFound
    case noAnswer
    case refused
    case offline
    case certificatePin
    case certificateName
    case tailnetByNumber
    case codeUsedOrExpired
    case tooManyTries
    case personRequired
    case versionMismatch
    case libraryNotGiven
    case hostStopped
    case deviceForgotten

    /// What the failure is about, filled in by the sheet: the host's name, the two versions, "Mac" or "device".
    struct Context: Equatable {
        var host = "the host"
        var hostVersion: String?
        var thisVersion: String?
        var noun = "Mac"
    }

    /// The step's number in the order they run: link 1, name 2, reach 3, certificate 5, code 6, person 7, version 8, library 9, stopped 10.
    var step: Int {
        switch self {
        case .invalidLink, .olderLink: return 1
        case .nameNotFound, .tailnetNameNotFound: return 2
        case .noAnswer, .refused, .offline: return 3
        case .certificatePin, .certificateName, .tailnetByNumber: return 5
        case .codeUsedOrExpired, .tooManyTries: return 6
        case .personRequired: return 7
        case .versionMismatch: return 8
        case .libraryNotGiven: return 9
        case .hostStopped, .deviceForgotten: return 10
        }
    }

    // swiftlint:disable:next cyclomatic_complexity
    func sentence(_ context: Context = Context()) -> String {
        let host = context.host
        switch self {
        case .invalidLink:
            return "This isn't a Fichero pairing link."
        case .olderLink:
            return "This link is for an older Fichero. Ask for a new one."
        case .nameNotFound:
            return "This \(context.noun) can't find \(host) on this network. Try the Tailscale address, "
                + "or put both Macs on the same Wi-Fi."
        case .tailnetNameNotFound:
            return "This \(context.noun) can't find \(host): Tailscale isn't running on this \(context.noun)."
        case .noAnswer:
            return "\(host) didn't answer in 5 seconds. Is Fichero open on \(host), and is Sharing on? "
                + "(If you are on a campus or hotel network, it may keep devices apart: use Tailscale.)"
        case .refused:
            return "\(host) is on, but Fichero isn't listening there: turn Sharing off and on."
        case .offline:
            return "This \(context.noun) isn't connected to a network."
        case .certificatePin:
            return "\(host) showed a different security key than the link. This may be a different Mac with the same name. "
                + "Scan or paste a new link from \(host)."
        case .certificateName:
            return "\(host)'s security certificate doesn't name the address in the link. "
                + "Turn Sharing off and on on \(host) so it makes a new one."
        case .tailnetByNumber:
            return "Tailscale addresses work by name, not by number. Ask for a new link."
        case .codeUsedOrExpired:
            return "That code was used or has expired (codes last 10 minutes). Make a new one on \(host)."
        case .tooManyTries:
            return "Too many tries. Wait a minute."
        case .personRequired:
            return "This library uses accounts. Enter your username and password."
        case .versionMismatch:
            return Self.versionSentence(context)
        case .libraryNotGiven:
            return "\(host) didn't give this device that project. Ask for a new link."
        case .hostStopped:
            return "\(host) stopped sharing. Ask them to turn Sharing on again."
        case .deviceForgotten:
            return "\(host) no longer knows this \(context.noun). Ask for a new link."
        }
    }

    /// Both versions named, and which Mac is older (`sharing.version-mismatch-says-which-side`): versions are
    /// `YYYY.MM.DD...`, so the older one sorts first.
    static func versionSentence(_ context: Context) -> String {
        guard let hostVersion = context.hostVersion, let thisVersion = context.thisVersion else {
            return "\(context.host) and this \(context.noun) run different versions of Fichero. Update the older one."
        }
        let which: String
        if hostVersion == thisVersion {
            which = "Update the older one."
        } else {
            which = hostVersion < thisVersion ? "Update \(context.host)." : "Update this \(context.noun)."
        }
        return "\(context.host) runs Fichero \(hostVersion) and this \(context.noun) \(thisVersion). \(which)"
    }

    /// The step a transport failure is, from its `URLError` code number (the raw code stays in the log). `host` decides the
    /// Tailscale wording and the by-number case: a `100.x` host fails TLS because Tailscale's certificate names the
    /// MagicDNS name only.
    static func from(urlErrorCode code: Int, host: String) -> PairingFailure {
        let lowered = host.lowercased()
        let tailnet = lowered.hasSuffix(".ts.net")
        let byNumber = lowered.hasPrefix("100.")
        switch code {
        case -1003: return tailnet ? .tailnetNameNotFound : .nameNotFound
        case -1001: return .noAnswer
        case -1004: return .refused
        case -1009: return .offline
        case -1005: return .noAnswer
        case -1200, -1201, -1202, -1203, -1204, -1205, -1206:
            // `.certificateName` is chosen by the caller that checked the certificate's names; a bare TLS code is the pin.
            return byNumber ? .tailnetByNumber : .certificatePin
        default: return .noAnswer
        }
    }

    /// The step an engine answer is: status code and its `detail`.
    static func from(status: Int, detail: String) -> PairingFailure? {
        let lowered = detail.lowercased()
        switch status {
        case 401 where lowered.contains("person required"): return .personRequired
        case 401 where lowered.contains("pairing code"): return .codeUsedOrExpired
        case 401: return .deviceForgotten
        case 429: return .tooManyTries
        default: return nil
        }
    }
}
