//
//  HostChoicesTests.swift
//  FicheroTests
//
//  sharing.mac-finds-host (#5734): the pure rules behind the host picker.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct HostChoicesTests {
    private func host(_ name: String, _ url: String?) -> HostChoices.Found { .init(name: name, publicURL: url) }

    @Test func offersOnlyReachableSecureHostsOtherThanThisMac() {
        let found = [
            host("Studio", "https://studio.local:8443"),
            host("This Mac", "https://this.local:8443"),
            host("Plain", "http://plain.local:8000"),
            host("Unresolved", nil),
        ]
        #expect(HostChoices.offered(found, ownName: "this mac").map(\.name) == ["Studio"])
    }

    @Test func oneRowPerAddressSortedByName() {
        let found = [host("b", "https://x.local:1"), host("a", "https://x.local:1"), host("c", "https://c.local:1")]
        #expect(HostChoices.offered(found, ownName: "me").map(\.name) == ["b", "c"])
    }

    @Test func typedNamesBecomeHttpsAddresses() {
        #expect(HostChoices.typedURL("studio")?.absoluteString == "https://studio.local")
        #expect(HostChoices.typedURL(" studio.local:8443 ")?.absoluteString == "https://studio.local:8443")
        #expect(HostChoices.typedURL("https://studio.local:8443")?.host == "studio.local")
        #expect(HostChoices.typedURL("studio:8443")?.absoluteString == "https://studio.local:8443")
    }

    @Test func typedNonsenseIsRefused() {
        #expect(HostChoices.typedURL("") == nil)
        #expect(HostChoices.typedURL("localhost") == nil)
        #expect(HostChoices.typedURL("http://studio.local") == nil)
        #expect(HostChoices.typedURL("https://studio.local/path") == nil)
    }

    @Test func aMacLeavesItselfOutByItsServiceName() {
        let own = HostChoices.ownServiceName(hostName: "Daniels-Mac.local")
        #expect(own == "Fichero Server on Daniels-Mac-local")
        let found = [host(own, "https://me.local:8443"), host("Fichero Server on Studio", "https://studio.local:8443")]
        #expect(HostChoices.offered(found, ownName: own).map(\.name) == ["Fichero Server on Studio"])
    }

    @Test func aLocalHostNeedsItsInviteAndAPickedInviteMustBeForThatHost() {
        let studio = host("Studio", "https://studio.local:8443")
        #expect(HostChoices.needsInvite(studio, ownTailnetURL: "https://mine.tail1234.ts.net"))
        #expect(HostChoices.invite("https://studio.local:8443", isFor: studio))
        #expect(!HostChoices.invite("https://other.local:8443", isFor: studio))
        #expect(!HostChoices.invite("not a url", isFor: studio))
    }

    /// Manager's ruling 2026-10-20: a public-CA (.ts.net) host is paired with under normal TLS validation (no pin
    /// recorded, so `resolveServerTrustChallenge` performs default handling: system trust and hostname match); http is
    /// refused, and a look-alike name is not a public-CA host.
    @Test func aTailnetHostIsHttpsOnlyAndALookAlikeNeedsItsInvite() async {
        let tailnet = host("Studio", "https://studio.tail1234.ts.net")
        #expect(!HostChoices.needsInvite(tailnet, ownTailnetURL: "https://mine.tail1234.ts.net"))
        #expect(HostChoices.offered([host("Studio", "http://studio.tail1234.ts.net")], ownName: "me",
                                    ownTailnetURL: "https://mine.tail1234.ts.net").isEmpty)
        #expect(HostChoices.needsInvite(host("Evil", "https://studio.ts.net.evil.example"), ownTailnetURL: "https://mine.tail1234.ts.net"))
        await #expect(throws: (any Error).self) {
            _ = try await RemoteClientPairing.pairDevice(
                remoteURL: "http://studio.tail1234.ts.net", pairCode: "ABC123", deviceName: "Guest", expectedSPKIPin: nil)
        }
    }

    /// Review 474 HIGH: the code alone is enough only inside this Mac's own tailnet.
    @Test func theCodeAloneIsEnoughOnlyInThisMacsOwnTailnet() {
        let mine = "https://mine.tail1234.ts.net"
        #expect(!HostChoices.needsInvite(host("Same", "https://studio.tail1234.ts.net"), ownTailnetURL: mine))
        #expect(HostChoices.needsInvite(host("Other tailnet", "https://studio.tail9999.ts.net"), ownTailnetURL: mine))
        #expect(HostChoices.needsInvite(host("Look-alike", "https://studio.tail1234.ts.net.evil.example"), ownTailnetURL: mine))
        #expect(HostChoices.needsInvite(host("Bare", "https://tail1234.ts.net"), ownTailnetURL: "https://tail1234.ts.net"))
        #expect(HostChoices.needsInvite(host("Same", "https://studio.tail1234.ts.net"), ownTailnetURL: nil))
        #expect(HostChoices.tailnet(of: "https://studio.tail1234.ts.net") == "tail1234.ts.net")
        #expect(HostChoices.tailnet(of: "https://tail1234.ts.net") == nil)  // a bare tailnet name is no machine in it
        #expect(HostChoices.tailnet(of: "https://a.b.tail1234.ts.net") == "tail1234.ts.net")
    }

    /// Review 474 HIGH (manager's rule): a `.ts.net` host is listed only in this Mac's own tailnet.
    @Test func aTailnetHostIsListedOnlyInThisMacsOwnTailnet() {
        let found = [host("Same", "https://a.tail1234.ts.net"), host("Foreign", "https://b.tail9999.ts.net"),
                     host("Local", "https://c.local:8443")]
        let mine = "https://mine.tail1234.ts.net"
        #expect(HostChoices.offered(found, ownName: "me", ownTailnetURL: mine).map(\.name) == ["Local", "Same"])
        // this Mac's tailnet unknown: no .ts.net host at all, the .local one still needs its invite
        #expect(HostChoices.offered(found, ownName: "me", ownTailnetURL: nil).map(\.name) == ["Local"])
        #expect(HostChoices.offered(found, ownName: "me", ownTailnetURL: "https://studio.local").map(\.name) == ["Local"])
    }

    /// Manager's ruling 2026-10-20, TLS: .ts.net = default trust (no pin recorded, so the system's trust and hostname
    /// match decide); .local = a pin is required (an invite without one is refused); http is refused.
    @Test func tailnetHostsUseDefaultTrustAndLocalHostsNeedAPin() throws {
        let tailnet = URL(string: "https://studio.tail1234.ts.net")!
        #expect(RemoteCertificatePinning.usesPublicCertificateAuthority(url: tailnet))
        #expect(try RemoteClientPairing.resolvedSPKIPin(nil, for: tailnet) == nil)
        let local = URL(string: "https://studio.local:8443")!
        #expect(!RemoteCertificatePinning.usesPublicCertificateAuthority(url: local))
        #expect(throws: (any Error).self) { try RemoteClientPairing.resolvedSPKIPin(nil, for: local) }
    }

    // sharing.ios.nearby-tap-pairs-with-that-mac (#5918)
    @Test func aCodeForTheMacThatWasPickedIsNotRefused() {
        let picked = host("Studio", "https://studio.local:8443")
        #expect(HostChoices.refusal(forInviteAt: "https://studio.local:8443", picked: picked) == nil)
    }

    @Test func aCodeForAnotherMacIsRefusedNamingThePickedOne() {
        let picked = host("Studio", "https://studio.local:8443")
        let sentence = HostChoices.refusal(forInviteAt: "https://other.local:8443", picked: picked)
        #expect(sentence == "That code is for another Mac than Studio. Scan the one shown on Studio.")
    }

    @Test func aPickedMacWithNoAddressCannotBeCrossCheckedAndIsNotRefused() {
        #expect(HostChoices.refusal(forInviteAt: "https://anything.local", picked: host("Studio", nil)) == nil)
    }
}
