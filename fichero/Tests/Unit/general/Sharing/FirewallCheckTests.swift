@testable import Fichero
import Foundation
import Testing

/// `sharing.firewall-prompt-says-what-to-click` (Step 3.2): the firewall's own words become a verdict.
struct FirewallCheckTests {
    private let enabled = "Firewall is enabled. (State = 1)"
    private let disabled = "Firewall is disabled. (State = 0)"
    private func apps(_ status: String) -> String {
        "Total number of apps = 2\n\n1 :  /Applications/Other.app\n     ( Allow incoming connections )\n\n"
            + "2 :  /Applications/Fichero.app/Contents/Fichero Server.app\n     ( \(status) incoming connections )\n"
    }

    @Test func aBlockedEngineBehindAnEnabledFirewallIsBlocking() {
        #expect(FirewallCheck.verdict(globalState: enabled, listApps: apps("Block")) == .blocking)
    }

    @Test func anAllowedEngineOrAFirewallThatIsOffIsNotBlocking() {
        #expect(FirewallCheck.verdict(globalState: enabled, listApps: apps("Allow")) == .notBlocking)
        #expect(FirewallCheck.verdict(globalState: disabled, listApps: apps("Block")) == .notBlocking)
    }

    @Test func noEntryOrAnUnreadableToolIsUnknownNeverBlocking() {
        #expect(FirewallCheck.verdict(globalState: enabled, listApps: "Total number of apps = 0") == .unknown)
        #expect(FirewallCheck.read { _ in nil } == .unknown)
    }

    @Test func theNeighbouringAppsStatusIsNotTheEngines() {
        let text = "1 :  /Applications/Fichero Server.app\n\n2 :  /Applications/Other.app\n     ( Block incoming connections )\n"
        #expect(FirewallCheck.verdict(globalState: enabled, listApps: text) == .unknown)
    }

    @Test func theSentenceNamesTheClicks() {
        #expect(FirewallCheck.blockedSentence.contains("System Settings › Network › Firewall › Options"))
        #expect(FirewallCheck.blockedSentence.contains("allow Fichero Server"))
    }

    @Test func aBlockingFirewallStopsTheLinkAndOffersNoButton() {
        #expect(PairingBlocker.firewallBlocking.detail == FirewallCheck.blockedSentence)
        #expect(PairingBlocker.firewallBlocking.actionTitle == nil)
        #expect(AddDeviceSheetModel.phase(blocker: .firewallBlocking, hasCode: true, hasLink: true, isWorking: false)
            == .failed(FirewallCheck.blockedSentence))
    }
}
