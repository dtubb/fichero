//
//  ConnectSheetModelTests.swift
//  FicheroTests
//
//  `sharing.settings.connect-sheet` (#5928): the Connect sheet's words and when Connect is on.
//

@testable import Fichero
import Testing

@Suite("Settings › Connect sheet")
struct ConnectSheetModelTests {
    typealias Model = ConnectSheetModel

    @Test("Searching… shows only while looking with nothing found")
    func nearby() {
        #expect(Model.nearbyStatus(searching: true, found: 0) == "Searching…")
        #expect(Model.nearbyStatus(searching: true, found: 2) == nil)
        #expect(Model.nearbyStatus(searching: false, found: 0) == nil)
    }

    @Test("a pending invite link opens the sheet; none, or an empty one, does not")
    func opensForAnInvite() {
        #expect(Model.opensFor(pendingInvite: "fichero://pair?x=1"))
        #expect(!Model.opensFor(pendingInvite: nil))
        #expect(!Model.opensFor(pendingInvite: ""))
    }

    @Test("where it connects is said once: the picked Mac, else the pasted link's host")
    func connectsTo() {
        #expect(Model.connectsTo(pickedAddress: "https://studio.local:8765", pastedHost: "other.local") == "Connects to https://studio.local:8765")
        #expect(Model.connectsTo(pickedAddress: nil, pastedHost: "pro.local") == "Connects to pro.local")
        #expect(Model.connectsTo(pickedAddress: nil, pastedHost: nil) == nil)
    }

    @Test("Connect needs the route's field, is off while connecting, and needs Name and Password only when asked")
    func canConnect() {
        #expect(!Model.canConnect(codeRoute: true, code: " ", link: "fichero://pair?x", isConnecting: false))
        #expect(Model.canConnect(codeRoute: true, code: "482913", link: "", isConnecting: false))
        #expect(Model.canConnect(codeRoute: false, code: "", link: "fichero://pair?x", isConnecting: false))
        #expect(!Model.canConnect(codeRoute: false, code: "", link: "fichero://pair?x", isConnecting: true))
        #expect(!Model.canConnect(codeRoute: false, code: "", link: "fichero://pair?x", isConnecting: false, needsPerson: true))
        #expect(Model.canConnect(codeRoute: false, code: "", link: "fichero://pair?x", isConnecting: false,
                                 needsPerson: true, name: "ana", password: "pw"))
        #expect(Model.connectTitle(isConnecting: true) == "Connecting…" && Model.connectTitle(isConnecting: false) == "Connect")
    }
}
