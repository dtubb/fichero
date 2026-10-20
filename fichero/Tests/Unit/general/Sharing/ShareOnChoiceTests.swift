//
//  ShareOnChoiceTests.swift
//  FicheroTests
//
//  sharing.listener (#5897): Sharing on listens on this network; the app names only a `.local` address for it.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Testing

struct ShareOnChoiceTests {
    @Test func aLocalAddressIsTheOnlyOneTheLocalListenerUses() {
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "studio.local") == "studio.local")
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "mac.tail1234.ts.net") == nil)
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: nil) == nil)
    }
}
