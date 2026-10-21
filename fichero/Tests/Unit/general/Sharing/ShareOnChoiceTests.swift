//
//  ShareOnChoiceTests.swift
//  FicheroTests
//
//  sharing.listener (#5897): Sharing on listens on this network; the app names only a `.local` address for it.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

struct ShareOnChoiceTests {
    @Test func aLocalAddressIsTheOnlyOneTheLocalListenerUses() {
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "studio.local") == "studio.local")
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "mac.tail1234.ts.net") == nil)
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: nil) == nil)
    }

    /// #5897: the old "This network" choice is gone from the app. A source scan: no Swift file passes the engine
    /// `FICHERO_THIS_NETWORK`, or carries a `thisNetworkChoice`; the app names only `FICHERO_LAN_HOST`, while Sharing is on.
    @Test func noSwiftFileStillPassesOrStoresTheThisNetworkChoice() throws {
        let root = try AppSource.root()
        let files = try #require(FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil))
        var offenders: [String] = []
        for case let url as URL in files where url.pathExtension == "swift" {
            let text = try String(contentsOf: url, encoding: .utf8)
            if text.contains("FICHERO_THIS_NETWORK") || text.contains("thisNetworkChoice") { offenders.append(url.lastPathComponent) }
        }
        #expect(offenders.isEmpty, "the 'This network' choice is back in: \(offenders)")
    }
}
