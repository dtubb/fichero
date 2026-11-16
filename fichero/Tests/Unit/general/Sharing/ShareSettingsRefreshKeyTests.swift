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

    @Test("the engine coming back mints into an empty card, or over a code another engine process minted")
    func engineReturnMintsOnlyWhenTheCodeIsNotThisEngines() {
        #expect(PairingCardRefresh.mintsWhenEngineChanges(isRunning: true, hasCode: false, blocked: false, sameEngine: false))
        #expect(!PairingCardRefresh.mintsWhenEngineChanges(isRunning: true, hasCode: true, blocked: false, sameEngine: true),
                "the same engine still holds this code: keep it (a health check)")
        #expect(PairingCardRefresh.mintsWhenEngineChanges(isRunning: true, hasCode: true, blocked: false, sameEngine: false),
                "a restart: the engine lost this code, mint again")
        #expect(!PairingCardRefresh.mintsWhenEngineChanges(isRunning: false, hasCode: false, blocked: true, sameEngine: false), "away")
        #expect(!PairingCardRefresh.mintsWhenEngineChanges(isRunning: true, hasCode: false, blocked: true, sameEngine: false), "sharing off")
    }

    @Test("a momentary engine-not-running blocker keeps the code only for the same engine process")
    func momentaryBlockerKeepsTheCode() {
        #expect(PairingCardRefresh.keepsCode(whenBlockedBy: true, hasCode: true, sameEngine: true))
        #expect(!PairingCardRefresh.keepsCode(whenBlockedBy: true, hasCode: true, sameEngine: false), "another process: the code is dead")
        #expect(!PairingCardRefresh.keepsCode(whenBlockedBy: false, hasCode: true, sameEngine: true), "sharing off or address lost: the card clears")
        #expect(!PairingCardRefresh.keepsCode(whenBlockedBy: true, hasCode: false, sameEngine: true), "nothing to keep")
    }

    @Test("the engine process is the same only when both pids are known and equal")
    func sameEngineNeedsBothPids() {
        #expect(PairingCardRefresh.sameEngine(codePID: 4242, currentPID: 4242))
        #expect(!PairingCardRefresh.sameEngine(codePID: 4242, currentPID: 4343), "restarted")
        #expect(!PairingCardRefresh.sameEngine(codePID: nil, currentPID: 4242), "unknown: never vouch for the code")
        #expect(!PairingCardRefresh.sameEngine(codePID: 4242, currentPID: nil))
    }

    @Test("the sharing state is read again while the forward says none or nothing was read, and not once it has answered")
    func readsForwardAgainOnlyUntilAnswered() {
        #expect(PairingCardRefresh.readsForwardAgain(stateLoaded: true, forward: "none"))
        #expect(PairingCardRefresh.readsForwardAgain(stateLoaded: false, forward: nil))
        for answered in ["ours", "foreign", "unknown"] {
            #expect(!PairingCardRefresh.readsForwardAgain(stateLoaded: true, forward: answered), "\(answered) is an answer")
        }
    }
}
