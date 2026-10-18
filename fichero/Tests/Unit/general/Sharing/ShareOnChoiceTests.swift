//
//  ShareOnChoiceTests.swift
//  FicheroTests
//
//  sharing.share-on-choice (#5736): the `.local` listener follows the "This network" checkbox.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Testing

struct ShareOnChoiceTests {
    @Test func thisNetworkUncheckedOpensNoLocalListenerEvenWithALocalAddress() {
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "studio.local", thisNetwork: false) == nil)
    }

    @Test func thisNetworkCheckedListensOnTheLocalAddress() {
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "studio.local", thisNetwork: true) == "studio.local")
    }

    @Test func aTailnetAddressNeverOpensTheLocalListener() {
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "mac.tail1234.ts.net", thisNetwork: true) == nil)
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: nil, thisNetwork: true) == nil)
    }
}

extension ShareOnChoiceTests {
    @Test func anUpdatedSetupAlreadySharingOverLocalKeepsThisNetworkOn() {
        #expect(RemoteAccessConfig.thisNetworkOn(stored: nil, hostingEnabled: true, publicHost: "studio.local"))
    }

    @Test func aFreshSetupDefaultsThisNetworkOff() {
        #expect(!RemoteAccessConfig.thisNetworkOn(stored: nil, hostingEnabled: false, publicHost: nil))
        #expect(!RemoteAccessConfig.thisNetworkOn(stored: nil, hostingEnabled: true, publicHost: "mac.t.ts.net"))
    }

    @Test func aStoredChoiceAlwaysWins() {
        #expect(!RemoteAccessConfig.thisNetworkOn(stored: false, hostingEnabled: true, publicHost: "studio.local"))
        #expect(RemoteAccessConfig.thisNetworkOn(stored: true, hostingEnabled: false, publicHost: nil))
    }

    @Test func turningItOffExplainsWhyAPairedDeviceCannotConnect() {
        #expect(RemoteAccessConfig.thisNetworkOffNote(thisNetwork: false, publicHost: "studio.local")?
            .contains("This network is off") == true)
        #expect(RemoteAccessConfig.thisNetworkOffNote(thisNetwork: true, publicHost: "studio.local") == nil)
    }
}
