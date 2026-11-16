//
//  PairingLinkAddressesTests.swift
//  FicheroTests
//
//  sharing.link-carries-every-address (#6431): a link made from a Mac that has both a `.local` name and a Tailscale name carries
//  both, so a joiner on another network does not stop at the name that only works on the same network.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct PairingLinkAddressesTests {
    private let pin = Data("spki".utf8).base64EncodedString()
    private let code = PairingCodeRecord(code: "ABCD-1234", expiresAt: nil)
    private let local = URL(string: "https://studio.local:8765")!
    private let tailnet = URL(string: "https://studio.tail1234.ts.net:8765")!

    private func rows(tailnetForward: String? = "ours") -> [AddressRow] {
        AddressChoiceModel.rows(
            sharingAddress: local.absoluteString, tailnetURL: "https://studio.tail1234.ts.net", tailnetForward: tailnetForward)
    }

    @Test func aLinkFromTheLocalNameAlsoCarriesTheTailscaleName() throws {
        let payload = try #require(PairingLinkAddresses.payload(
            chosen: local, rows: rows(), code: code, spkiPin: pin, libraryPath: "/L"))
        #expect(payload.apiURL == "https://studio.local:8765")
        #expect(payload.altURLs == ["https://studio.tail1234.ts.net:8765"])
        #expect(payload.spki == pin)  // the .local name serves its own certificate, so the link needs the pin
    }

    @Test func aTailscaleFirstLinkStillCarriesThePinForTheLocalName() throws {
        let payload = try #require(PairingLinkAddresses.payload(
            chosen: tailnet, rows: rows(), code: code, spkiPin: pin, libraryPath: nil))
        #expect(payload.apiURL == "https://studio.tail1234.ts.net:8765")
        #expect(payload.altURLs == ["https://studio.local:8765"])
        #expect(payload.spki == pin)
    }

    @Test func anAddressThatCannotWorkIsNotCarried() throws {
        let payload = try #require(PairingLinkAddresses.payload(
            chosen: local, rows: rows(tailnetForward: "none"), code: code, spkiPin: pin, libraryPath: nil))
        #expect(payload.altURLs == nil)
    }

    @Test func theOrderIsChosenFirstThenTailscaleThenTheRestWithNoRepeats() {
        let lan = URL(string: "https://192.0.2.10:8765")!
        let ordered = PairingLinkAddresses.order(chosen: lan, rows: rows() + [AddressRow(
            choice: .thisNetwork, url: lan, title: "x", reach: "", disabledReason: nil)])
        #expect(ordered == [lan, tailnet, local])
    }

    @Test func aChosenAddressWithNoPinYetMakesNoLink() {
        #expect(PairingLinkAddresses.payload(chosen: local, rows: rows(), code: code, spkiPin: "", libraryPath: nil) == nil)
    }
}
