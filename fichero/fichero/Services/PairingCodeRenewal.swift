import Foundation

/// When the Sharing card replaces a pairing code that is about to expire (sharing.pairing-code-renews-at-expiry, #5915).
enum PairingCodeRenewal {
    /// Never wait less than this: a clock that disagrees with the engine's must not make the card re-mint in a loop.
    static let shortestWait: TimeInterval = 5

    /// How long to wait before minting a fresh code for one that expires at `expiresAt`.
    static func wait(until expiresAt: Date, now: Date = Date()) -> Duration {
        .seconds(max(expiresAt.timeIntervalSince(now), shortestWait))
    }
}
