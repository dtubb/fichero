import Foundation

/// When the Sharing card replaces a pairing code that is about to expire (sharing.pairing-code-renews-at-expiry, #5915).
enum PairingCodeRenewal {
    /// Never wait less than this: a clock that disagrees with the engine's must not make the card re-mint in a loop.
    static let shortestWait: TimeInterval = 5

    /// How long to wait before minting a fresh code for one that expires at `expiresAt`.
    static func wait(until expiresAt: Date, now: Date = Date()) -> Duration {
        .seconds(max(expiresAt.timeIntervalSince(now), shortestWait))
    }

    /// What happened when the card asked for a fresh code in place of an expiring one.
    enum Outcome {
        /// The new code: it replaces the old one in a single step, so there is never a blank card in between.
        case fresh(PairingCodeRecord)
        /// The mint failed: the expired code goes and this is the sentence to show.
        case failed(String)
        /// The wait or the mint was cancelled (the card went away): nothing is shown or changed.
        case cancelled
    }

    /// Mints the replacement WITHOUT clearing the code on screen first: clearing it changes the key the waiting task
    /// is running under and cancels the very task doing the renewal (review 597, #5915).
    static func renew(mint: () async throws -> PairingCodeRecord) async -> Outcome {
        do {
            let fresh = try await mint()
            try Task.checkCancellation()
            return .fresh(fresh)
        } catch is CancellationError {
            return .cancelled
        } catch let error as URLError where error.code == .cancelled {
            return .cancelled
        } catch {
            return .failed(error.localizedDescription)
        }
    }
}
