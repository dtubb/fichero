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
    @Test func aLocalAddressIsTheOnlyOneTheLocalListenerUses() {
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "studio.local") == "studio.local")
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: "mac.tail1234.ts.net") == nil)
        #expect(RemoteAccessConfig.lanListenerHost(publicHost: nil) == nil)
    }

    /// The old Bonjour key (its own advertising toggle, perhaps a stale false) is not the choice: unset means
    /// "decide from the paired devices", which the engine does (`test_share_on_listeners_to_spec.py`).
    @Test func theChoiceIsItsOwnKeyAndUnsetUntilMade() {
        #expect(RemoteAccessConfig.thisNetworkKey != RemoteAccessConfig.bonjourEnabledKey)
        let saved = RemoteAccessConfig.defaults.object(forKey: RemoteAccessConfig.thisNetworkKey)
        defer { RemoteAccessConfig.defaults.set(saved, forKey: RemoteAccessConfig.thisNetworkKey) }
        RemoteAccessConfig.defaults.removeObject(forKey: RemoteAccessConfig.thisNetworkKey)
        #expect(RemoteAccessConfig.thisNetworkChoice == nil)
        RemoteAccessConfig.defaults.set(false, forKey: RemoteAccessConfig.thisNetworkKey)
        #expect(RemoteAccessConfig.thisNetworkChoice == false)
    }
}

extension ShareOnChoiceTests {
    @Test func turningItOffExplainsWhyAPairedDeviceCannotConnect() {
        #expect(RemoteAccessConfig.thisNetworkOffNote(thisNetwork: false, publicHost: "studio.local")?
            .contains("This network is off") == true)
        #expect(RemoteAccessConfig.thisNetworkOffNote(thisNetwork: true, publicHost: "studio.local") == nil)
    }
}
