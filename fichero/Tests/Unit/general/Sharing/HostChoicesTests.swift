//
//  HostChoicesTests.swift
//  FicheroTests
//
//  sharing.mac-finds-host (#5734): the pure rules behind the host picker.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
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
        #expect(HostChoices.needsInvite(studio))
        #expect(HostChoices.invite("https://studio.local:8443", isFor: studio))
        #expect(!HostChoices.invite("https://other.local:8443", isFor: studio))
        #expect(!HostChoices.invite("not a url", isFor: studio))
    }

    /// Manager's ruling 2026-10-20: a public-CA (.ts.net) host is paired with under normal TLS validation (no pin
    /// recorded, so `resolveServerTrustChallenge` performs default handling: system trust and hostname match); http is
    /// refused, and a look-alike name is not a public-CA host.
    @Test func aTailnetHostIsHttpsOnlyAndALookAlikeNeedsItsInvite() async {
        let tailnet = host("Studio", "https://studio.tail1234.ts.net")
        #expect(!HostChoices.needsInvite(tailnet))
        #expect(HostChoices.offered([host("Studio", "http://studio.tail1234.ts.net")], ownName: "me").isEmpty)
        #expect(HostChoices.needsInvite(host("Evil", "https://studio.ts.net.evil.example")))
        await #expect(throws: (any Error).self) {
            _ = try await RemoteClientPairing.pairDevice(
                remoteURL: "http://studio.tail1234.ts.net", pairCode: "ABC123", deviceName: "Guest", expectedSPKIPin: nil)
        }
    }
}
