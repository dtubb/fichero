@testable import Fichero
import Testing

/// `sharing.card-keeps-its-code` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.2): the Sharing card's code
/// outlives a health check. Written 2026-10-31, not yet built (no Xcode run on this Mac).
struct ShareSettingsRefreshKeyTests {
    private func key(running: Bool = true, address: String = "https://m.local:8765", pin: String = "pin", host: String = "uds") -> String {
        // `running` is NOT an input any more; it is here to show the key cannot see it
        _ = running
        return PairingCardRefresh.key(hostingEnabled: true, publicBaseURL: address, spkiPin: pin, engineHost: host, didBootstrap: true)
    }

    @Test("the engine's phase passing through starting and back leaves the key unchanged")
    func healthCheckDoesNotChangeTheKey() {
        #expect(key(running: true) == key(running: false))
    }

    @Test("sharing, the address, the pin and the engine host each change the key")
    func realChangesChangeTheKey() {
        let base = key()
        #expect(key(address: "https://m.tail.ts.net") != base)
        #expect(key(pin: "another") != base)
        #expect(key(host: "https://other:8765") != base)
        #expect(PairingCardRefresh.key(hostingEnabled: false, publicBaseURL: "https://m.local:8765", spkiPin: "pin",
                                       engineHost: "uds", didBootstrap: true) != base)
    }

    @Test("the engine coming back mints only when the card is empty and unblocked")
    func engineReturnMintsOnlyIntoAnEmptyCard() {
        #expect(PairingCardRefresh.mintsWhenEngineChanges(isRunning: true, hasCode: false, blocked: false))
        #expect(!PairingCardRefresh.mintsWhenEngineChanges(isRunning: true, hasCode: true, blocked: false), "a code is up: keep it")
        #expect(!PairingCardRefresh.mintsWhenEngineChanges(isRunning: false, hasCode: false, blocked: true), "away: nothing to mint from")
        #expect(!PairingCardRefresh.mintsWhenEngineChanges(isRunning: true, hasCode: false, blocked: true), "sharing off: no code")
    }

    @Test("a momentary engine-not-running blocker keeps the code; anything else clears it")
    func momentaryBlockerKeepsTheCode() {
        #expect(PairingCardRefresh.keepsCode(whenBlockedBy: true, hasCode: true))
        #expect(!PairingCardRefresh.keepsCode(whenBlockedBy: false, hasCode: true), "sharing off or address lost: the card clears")
        #expect(!PairingCardRefresh.keepsCode(whenBlockedBy: true, hasCode: false), "nothing to keep")
    }
}
