@testable import Fichero
import Foundation
import Testing

/// signin.own.mac-writes-the-keychain-item (the shape) and signin.own.ios-finds-it-and-connects (the dial), #6568.
struct OwnDevicesConnectTests {
    private let tailnet = OwnDevicesItem.Address(url: "https://air.tail1234.ts.net:8765", spki: nil)
    private let local = OwnDevicesItem.Address(url: "https://air.local:8765", spki: "PIN")
    private func item(_ addresses: [OwnDevicesItem.Address]) -> OwnDevicesItem {
        OwnDevicesItem(engineID: "eng-1", macName: "Air", addresses: addresses, enrollmentSecret: "secret")
    }

    @Test func thePayloadHasTheFourFieldsAndNothingElse() throws {
        let data = try item([tailnet]).encoded()
        let object = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(Set(object.keys) == ["engine_id", "mac_name", "addresses", "enrollment_secret"])
        #expect(try OwnDevicesItem.decode(data) == item([tailnet]))
    }

    @Test func tailnetFirstThenLocalWithBlanksAndRepeatsDropped() {
        let ordered = OwnDevicesItem.ordered([local, .init(url: "", spki: nil), tailnet, local])
        #expect(ordered == [tailnet, local])
    }

    @Test func dialsEachAddressInTurnAndStopsAtTheFirstThatEnrols() async throws {
        var dialed: [String] = []
        let result = try await OwnDevicesConnect.connect(item([local, tailnet]), deviceName: "Daniel's iPhone") { address, secret, name in
            dialed.append(address.url)
            #expect(secret == "secret" && name == "Daniel's iPhone")
            if address == tailnet { throw URLError(.cannotConnectToHost) }
            return ("token", Date(timeIntervalSince1970: 1))
        }
        #expect(dialed == [tailnet.url, local.url])
        #expect(result.address == local && result.deviceToken == "token")
    }

    @Test func aRefusedSecretStopsWithoutTryingTheOtherAddress() async {
        var dialed = 0
        await #expect(throws: OwnDevicesConnect.Failure.refused("Air")) {
            _ = try await OwnDevicesConnect.connect(item([tailnet, local]), deviceName: "iPhone") { _, _, _ in
                dialed += 1
                throw OwnDevicesConnect.SecretRefused()
            }
        }
        #expect(dialed == 1)
    }

    @Test func noAnswerAnywhereNamesTheMac() async {
        await #expect(throws: OwnDevicesConnect.Failure.noAnswer("Air")) {
            _ = try await OwnDevicesConnect.connect(item([tailnet, local]), deviceName: "iPhone") { _, _, _ in
                throw URLError(.timedOut)
            }
        }
    }

    @Test func aDeviceWithATokenNeverEnrolsAgain() {
        #expect(!OwnDevicesConnect.needsEnrolment(engineID: "eng-1", hasToken: { $0 == "eng-1" }))
        #expect(OwnDevicesConnect.needsEnrolment(engineID: "eng-2", hasToken: { $0 == "eng-1" }))
    }
}
