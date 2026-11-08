@testable import Fichero
import Foundation
import Testing

/// `sharing.ios-local-network-permission` (Step 5.3): a denied Local Network permission gets its sentence.
struct NearbyHostsPolicyDeniedTests {
    @Test func theBrowsersPolicyDeniedCodeIsTheDenial() {
        #expect(LocalNetworkPolicy.isDenied(errorCode: -72008))
        #expect(!LocalNetworkPolicy.isDenied(errorCode: -72004), "another browse failure is not this")
    }

    @Test func aLocalAddressThatDoesNotAnswerReadsAsTheMissingPermission() {
        let context = PairingFailure.Context(host: "macbook-air-m1.local")
        #expect(LocalNetworkPolicy.sentence(for: .noAnswer, context: context) == LocalNetworkPolicy.sentence)
        #expect(LocalNetworkPolicy.sentence(for: .offline, context: .init(host: "192.168.1.20")) == LocalNetworkPolicy.sentence)
    }

    @Test func otherFailuresAndOtherAddressesKeepTheirOwnSentence() {
        let tailnet = PairingFailure.Context(host: "air.tail1234.ts.net")
        #expect(LocalNetworkPolicy.sentence(for: .noAnswer, context: tailnet) == PairingFailure.noAnswer.sentence(tailnet))
        let local = PairingFailure.Context(host: "air.local")
        #expect(LocalNetworkPolicy.sentence(for: .refused, context: local) == PairingFailure.refused.sentence(local))
        #expect(LocalNetworkPolicy.sentence(for: .nameNotFound, context: local) == PairingFailure.nameNotFound.sentence(local))
    }

    @Test func theLocalRangesAreTheRightOnes() {
        for host in ["a.local", "10.0.0.4", "192.168.1.2", "169.254.3.4", "172.16.0.1", "172.31.255.1"] {
            #expect(LocalNetworkPolicy.isLocalAddress(host), "\(host)")
        }
        for host in ["a.tail1234.ts.net", "100.101.102.103", "172.15.0.1", "172.32.0.1", "example.com"] {
            #expect(!LocalNetworkPolicy.isLocalAddress(host), "\(host)")
        }
    }

    @Test func theSentenceNamesTheSettingsPath() {
        #expect(LocalNetworkPolicy.sentence.contains("Settings › Fichero › Local Network"))
        #expect(LocalNetworkPolicy.buttonTitle == "Open Settings")
    }
}
