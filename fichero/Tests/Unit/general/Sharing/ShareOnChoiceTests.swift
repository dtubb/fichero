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
