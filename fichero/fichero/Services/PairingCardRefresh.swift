import Foundation

/// When the Sharing card mints a NEW pairing code, and when it keeps the one it has (`sharing.card-keeps-its-code`).
///
/// The card used to re-mint whenever `isBackendRunning` changed, and every `checkBackendHealth()` flips it twice
/// (`markStarting` → `markReady`): a Multi-user flip, the project Share sheet, Engine settings and a host switch all
/// cleared the card and minted again, which the owner saw as the code "resetting" (2026-10-31; the Air's log shows a mint
/// after each health check). The engine's phase is not in the key any more; a code is replaced only when it expires
/// (`PairingCodeRenewal`), when sharing, the address or the pin changes, or when the engine comes back and the card has
/// no code to show.
enum PairingCardRefresh {
    /// The inputs whose change means "mint a new code"; the engine's running state is deliberately NOT one of them.
    static func key(hostingEnabled: Bool, publicBaseURL: String, spkiPin: String, engineHost: String, didBootstrap: Bool) -> String {
        [hostingEnabled.description, publicBaseURL, spkiPin, engineHost, didBootstrap.description].joined(separator: "|")
    }

    /// When the engine's readiness changes: mint only if it came back and the card holds no code (a mint that failed
    /// while it was away, or nothing minted yet); never while it is away, never when a code is already up.
    static func mintsWhenEngineChanges(isRunning: Bool, hasCode: Bool, blocked: Bool) -> Bool {
        isRunning && !hasCode && !blocked
    }

    /// A health check in flight shows the engine as "not running" for a moment: a code already on the card stays
    /// (`keepsCode`), so a momentary `.engineNotRunning` blocker never blanks the card. Sharing off or a lost address
    /// does clear it.
    static func keepsCode(whenBlockedBy blockerIsEngineNotRunning: Bool, hasCode: Bool) -> Bool {
        hasCode && blockerIsEngineNotRunning
    }
}
