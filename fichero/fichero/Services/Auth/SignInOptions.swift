import Foundation

/// `multiuser.password-comes-last` / `signin.password-comes-last` (#2403, #6568): what a sign-in screen offers, in order.
enum SignInOptions {
    enum Option: Equatable { case silentKey, ownMacs, approval, nearbyMacs, passkey, qrCode, password }

    /// The key signs in silently with nothing shown; the rest are rows, and the password is always last.
    static func order(hasSyncedKey: Bool, hasOwnMacs: Bool, canApprove: Bool, nearbyMacs: Bool, hasPasskey: Bool) -> [Option] {
        var options: [Option] = []
        if hasSyncedKey { options.append(.silentKey) }
        if hasOwnMacs { options.append(.ownMacs) }
        if canApprove { options.append(.approval) }
        if nearbyMacs { options.append(.nearbyMacs) }
        if hasPasskey { options.append(.passkey) }
        return options + [.qrCode, .password]
    }

    /// The iPhone and iPad Connect screen's sections, in `order`. The silent key shows nothing, and the password is the
    /// host's alert after a typed address (`personSignInAlert`), so neither is a section. The nearby list always shows,
    /// with "Searching…" while it is empty.
    /// ponytail: approval and passkey rows join here when those methods are built.
    static func connectScreenRows(hasOwnMacs: Bool) -> [Option] {
        order(hasSyncedKey: false, hasOwnMacs: hasOwnMacs, canApprove: false, nearbyMacs: true, hasPasskey: false)
            .filter { $0 != .password }
    }
}
