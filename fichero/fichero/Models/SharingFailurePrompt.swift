import Foundation

/// A pairing or sharing failure as the generic failure alert (`sharing.alerts.one-alert-per-failure`, Step 8.8, #6361): the
/// table's title, the step's sentence (why, then the fix), the fix as a button where there is one, then Copy Details and OK.
/// No raw error text (`localizedDescription` of a client error, an OSStatus, an HTTP code) reaches the message: it goes to
/// Copy Details only. Pure: the views say which fixes they can do and do them.
enum SharingFailurePrompt {
    /// The fix buttons of the table. A view offers only the ones it can do.
    enum Fix: Hashable, CaseIterable {
        case pasteLinkAgain, openTailscale, tryAgain, openNetworkSettings, openAppSettings, signIn, checkForUpdates
        case turnSharingOffAndOn, signInAsOwner

        var label: String {
            switch self {
            case .pasteLinkAgain: "Paste Link Again"
            case .openTailscale: "Open Tailscale"
            case .tryAgain: "Try Again"
            case .openNetworkSettings: "Open Network Settings"
            case .openAppSettings: LocalNetworkPolicy.buttonTitle
            case .signIn: "Sign In…"
            case .checkForUpdates: "Check for Updates…"
            case .turnSharingOffAndOn: "Turn Sharing Off and On"
            case .signInAsOwner: "Sign In as Owner"
            }
        }
    }

    /// The fixes a phone or iPad sheet can do: a URL to open, a second go, or the link field again.
    static let phoneOffers: Set<Fix> = [.pasteLinkAgain, .openTailscale, .tryAgain, .openNetworkSettings, .openAppSettings]

    /// The page a fix opens, where the fix is opening one: the Tailscale app, or this app's page in iOS Settings.
    static func url(for fix: Fix) -> URL? {
        switch fix {
        case .openTailscale: URL(string: PairingFailureActions.tailscaleURL)
        case .openNetworkSettings, .openAppSettings: URL(string: PairingFailureActions.settingsURL)
        default: nil
        }
    }

    static let copyDetailsLabel = "Copy Details"
    static let dismissLabel = "OK"

    /// What happened, as the alert's title (the table's first column): the link and reach steps, then the rest.
    static func title(_ failure: PairingFailure, _ context: PairingFailure.Context) -> String {
        reachTitle(failure, context) ?? accountTitle(failure, context)
    }

    private static func reachTitle(_ failure: PairingFailure, _ context: PairingFailure.Context) -> String? {
        let host = context.host
        switch failure {
        case .invalidLink: return "This isn't a pairing link"
        case .olderLink: return "This link is for an older Fichero"
        case .nameNotFound, .tailnetNameNotFound: return "Can't find \(host)"
        case .noAnswer: return "\(host) didn't answer"
        case .refused: return "\(host) isn't listening"
        case .offline: return "No network"
        case .certificatePin: return "A different Mac answered"
        case .certificateName: return "\(host)'s certificate doesn't match"
        case .tailnetByNumber: return "Tailscale needs the name"
        default: return nil
        }
    }

    private static func accountTitle(_ failure: PairingFailure, _ context: PairingFailure.Context) -> String {
        let host = context.host
        switch failure {
        case .codeUsedOrExpired: return "That code has expired"
        case .tooManyTries: return "Too many tries"
        case .personRequired: return "Sign in to \(host)"
        case .versionMismatch: return "Fichero versions don't match"
        case .libraryNotGiven: return "\(host) didn't share that project with you"
        case .hostSharesNothing: return "\(host) hasn't shared any project yet"
        case .hostStopped: return "\(host) stopped sharing"
        case .deviceForgotten: return "\(host) no longer knows this \(context.noun)"
        default: return "Couldn't connect to \(host)"  // the reach steps have their titles above
        }
    }

    /// The fix button of the table, or nil where the fix is something only a person elsewhere can do.
    static func fix(_ failure: PairingFailure, host: String) -> Fix? {
        if LocalNetworkPolicy.explains(failure, host: host) { return .openAppSettings }
        switch failure {
        case .invalidLink, .certificatePin, .codeUsedOrExpired, .deviceForgotten: return .pasteLinkAgain
        case .nameNotFound, .tailnetNameNotFound: return .openTailscale
        case .noAnswer, .refused, .certificateName, .tooManyTries: return .tryAgain
        case .offline: return .openNetworkSettings
        case .personRequired: return .signIn
        case .versionMismatch: return .checkForUpdates
        case .olderLink, .tailnetByNumber, .libraryNotGiven, .hostSharesNothing, .hostStopped: return nil
        }
    }

    /// The alert for a step that failed.
    static func make(
        _ failure: PairingFailure, context: PairingFailure.Context, offers: Set<Fix>,
        perform: @escaping (Fix) -> Void, copy: @escaping (String) -> Void
    ) -> FailureAlertPrompt {
        prompt(
            title: title(failure, context),
            why: LocalNetworkPolicy.sentence(for: failure, context: context),
            fix: fix(failure, host: context.host).flatMap { offers.contains($0) ? $0 : nil },
            details: PairingFailureActions.details(failure, context: context), acts: (perform, copy))
    }

    /// The host asked who this device is (step 7, person): the phone answers with its sign-in alert, not a failure alert.
    static func asksForPerson(_ error: Error) -> Bool {
        if case .personRequired? = error as? RemoteClientPairingError { return true }
        if case .personRequired? = (error as? PairingFailureError)?.failure { return true }
        return false
    }

    /// The alert for whatever a pairing threw: a step of the table where the error is one (or a transport failure that
    /// maps to one), our own sentence where it is ours, and a plain line with the raw text in Copy Details otherwise.
    static func make(
        pairing error: Error, host: String, offers: Set<Fix>,
        perform: @escaping (Fix) -> Void, copy: @escaping (String) -> Void
    ) -> FailureAlertPrompt {
        let context = PairingFailure.Context(host: host, noun: RemoteClientPairingError.deviceNoun)
        if let step = error as? PairingFailureError {
            return make(step.failure, context: step.context, offers: offers, perform: perform, copy: copy)
        }
        switch error as? RemoteClientPairingError {
        case .personRequired?:
            return make(.personRequired, context: context, offers: offers, perform: perform, copy: copy)
        case .tokenNotSaved?:
            return prompt(title: "This \(context.noun) couldn't keep its key", why: error.localizedDescription,
                          fix: offers.contains(.tryAgain) ? .tryAgain : nil, details: error.localizedDescription,
                          acts: (perform, copy))
        case let own?:
            return prompt(title: "Couldn't connect to \(host)", why: own.errorDescription ?? "", fix: nil,
                          details: own.errorDescription ?? "", acts: (perform, copy))
        case nil: break
        }
        if let stopped = error as? PairingStoppedError {
            return prompt(title: "Couldn't connect to \(host)", why: stopped.message, fix: nil, details: stopped.message,
                          acts: (perform, copy))
        }
        if case APIError.badRequest(let words)? = error as? APIError {
            return prompt(title: "Couldn't connect to \(host)", why: words, fix: nil, details: words, acts: (perform, copy))
        }
        if transportCode(error) != nil {
            return make(LivePairingHost.failure(from: error, host: host), context: context, offers: offers, perform: perform, copy: copy)
        }
        return prompt(title: "Couldn't connect to \(host)", why: unknownSentence, fix: nil,
                      details: "Fichero could not connect to \(host).\n\(String(describing: error))", acts: (perform, copy))
    }

    /// The alert for a sharing step on this Mac that failed (turning Sharing on, the devices list, a share, a code):
    /// `title` says what was being done. The engine not listening offers Turn Sharing Off and On
    /// (`sharing.host.dialog-errors-are-alerts`); a 403 says only the owner can share; the engine's own words are shown as they are.
    static func make(
        sharing error: Error, title: String, offers: Set<Fix>,
        perform: @escaping (Fix) -> Void, copy: @escaping (String) -> Void
    ) -> FailureAlertPrompt {
        let details = "\(title).\n\(String(describing: error))"
        if transportCode(error) != nil {
            return prompt(
                title: title,
                why: "The engine on this Mac isn't accepting connections on the sharing port. Turn Sharing off and on to start it again.",
                fix: offers.contains(.turnSharingOffAndOn) ? .turnSharingOffAndOn : nil, details: details, acts: (perform, copy))
        }
        switch error as? APIError {
        case .httpError(403, _)?:
            // Sign In as Owner signs this app in again by the owner key (`OwnerSignInCoordinator.run`), no password asked.
            return prompt(title: title, why: "Only this Mac's owner can share its projects. Sign in as the owner, then share again.",
                          fix: offers.contains(.signInAsOwner) ? .signInAsOwner : nil, details: details, acts: (perform, copy))
        default:
            return prompt(title: title, why: engineWords(error) ?? unknownSentence, fix: nil, details: details, acts: (perform, copy))
        }
    }

    /// The engine's own words in a refusal, or nil where the error is the client's (its text is for Copy Details only).
    static func engineWords(_ error: Error) -> String? {
        switch error as? APIError {
        case .httpError(_, let words)?, .badRequest(let words)?, .notFound(let words)?, .serverError(let words)?: words
        default: nil
        }
    }

    /// A failure already in words (a shared library that would not open): Try Again where `retry` is given.
    static func make(
        title: String, sentence: String, retry: (() -> Void)? = nil, copy: @escaping (String) -> Void
    ) -> FailureAlertPrompt {
        prompt(title: title, why: sentence, fix: retry == nil ? nil : .tryAgain, details: "\(title).\n\(sentence)",
               acts: ({ _ in retry?() }, copy))
    }

    static let unknownSentence = "Something went wrong. Copy Details and send them to whoever helps you with Fichero."

    /// The `URLError` code anywhere in the error's chain, or a refused socket: the engine or the host did not answer.
    static func transportCode(_ error: Error) -> Int? {
        var current: NSError? = error as NSError
        while let next = current {
            if next.domain == NSURLErrorDomain { return next.code }
            if next.domain == NSPOSIXErrorDomain, next.code == Int(ECONNREFUSED) { return URLError.cannotConnectToHost.rawValue }
            current = next.userInfo[NSUnderlyingErrorKey] as? NSError
        }
        return nil
    }

    /// What the buttons do: the fix, and Copy Details with the text it copies.
    private typealias Acts = (perform: (Fix) -> Void, copy: (String) -> Void)

    private static func prompt(title: String, why: String, fix: Fix?, details: String, acts: Acts) -> FailureAlertPrompt {
        var fixes: [FailureAlertPrompt.Fix] = []
        if let fix { fixes.append(.init(id: 0, label: fix.label, action: { acts.perform(fix) })) }
        fixes.append(.init(id: 1, label: copyDetailsLabel, action: { acts.copy(details) }))
        return FailureAlertPrompt(title: title, message: FailureAlertPrompt.message(why: why, fix: nil), fixes: fixes,
                                  dismissLabel: dismissLabel)
    }
}
