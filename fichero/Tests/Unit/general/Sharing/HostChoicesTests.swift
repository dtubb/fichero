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
}
