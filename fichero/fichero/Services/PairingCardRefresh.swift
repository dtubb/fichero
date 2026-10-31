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

    /// When the engine's readiness changes: mint if it came back and the card holds no code, or holds a code minted by
    /// ANOTHER engine process. Pairing codes live in the engine's memory (`_PAIRING_CODES`), so a real restart loses them
    /// (review 2026-10-31, M1): a code kept across a restart would be dead for up to ten minutes. The engine process is
    /// told by health's `engine_pid`, which a health check leaves unchanged and a restart changes. Never while away.
    static func mintsWhenEngineChanges(isRunning: Bool, hasCode: Bool, blocked: Bool, sameEngine: Bool) -> Bool {
        isRunning && !blocked && (!hasCode || !sameEngine)
    }

    /// A health check in flight shows the engine as "not running" for a moment: a code already on the card stays
    /// (`keepsCode`) while it is the SAME engine process, so a momentary `.engineNotRunning` blocker never blanks the
    /// card; a code from another process is not kept. Sharing off or a lost address does clear it.
    static func keepsCode(whenBlockedBy blockerIsEngineNotRunning: Bool, hasCode: Bool, sameEngine: Bool) -> Bool {
        hasCode && blockerIsEngineNotRunning && sameEngine
    }

    /// Whether the code on the card was minted by the engine process now running: both pids known and equal. An
    /// unknown pid (an external engine, or none yet) never counts as the same, so the card re-mints rather than keep a
    /// code it cannot vouch for.
    static func sameEngine(codePID: Int?, currentPID: Int?) -> Bool {
        guard let codePID, let currentPID else { return false }
        return codePID == currentPID
    }
}
