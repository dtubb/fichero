//
//  ShareOnChoiceTests.swift
//  FicheroTests
//
//  sharing.listener (#5897): Sharing on listens on this network; the app names a `.local` or IPv4 address for it.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

struct ShareOnChoiceTests {
    @Test func aLocalAddressNamesTheLocalListener() {
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "studio.local") == "studio.local")
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "mac.tail1234.ts.net") == nil)
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: nil) == nil)
    }

    /// A saved sharing address that is this Mac's IP (the Thunderbolt bridge's) names the listener too: naming only
    /// `.local` left the engine on loopback, and it refused every pairing code, so Sharing never came on.
    @Test func anIPv4SharingAddressNamesTheLocalListener() {
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "10.10.10.1") == "10.10.10.1")
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "131.202.228.96") == "131.202.228.96")
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "127.0.0.1") == nil)
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "10.10.10") == nil)
    }

    /// #5897: the old "This network" choice is gone from the app. A source scan: no Swift file passes the engine
    /// `FICHERO_THIS_NETWORK`, or carries a `thisNetworkChoice`; the app names only `FICHERO_LAN_HOST`, while Sharing is on.
    @Test func noSwiftFileStillPassesOrStoresTheThisNetworkChoice() throws {
        let root = try AppSource.root()
        let files = try #require(FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil))
        // the names are split so this file does not match itself (the scan covers the app's sources, not the tests)
        let names = ["FICHERO_THIS_" + "NETWORK", "thisNetwork" + "Choice"]
        var offenders: [String] = []
        for case let url as URL in files where url.pathExtension == "swift" {
            let text = try String(contentsOf: url, encoding: .utf8)
            if names.contains(where: text.contains) { offenders.append(url.lastPathComponent) }
        }
        #expect(offenders.isEmpty, "the 'This network' choice is back in: \(offenders)")
    }
}
