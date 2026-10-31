@testable import Fichero
import Foundation
import Testing

/// `sharing.share-sheet-offers-both-addresses` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.1, #5318): the
/// pairing link and QR offer This network and Tailscale, Tailscale first when it can work, the pin following the row.
/// Written 2026-10-31, not yet built (no Xcode run on this Mac).
struct AddressChoiceModelTests {
    private let local = "https://macbook-air-m1.local:8765"
    private let tail = "https://macbook-air-m1.tail1234.ts.net"

    @Test("a .local sharer with its own tailnet forward: two rows, Tailscale (with the port) chosen by default")
    func twoRowsTailscaleFirst() throws {
        let rows = AddressChoiceModel.rows(sharingAddress: local, tailnetURL: tail, tailnetForward: "ours")
        #expect(rows.map(\.choice) == [.thisNetwork, .tailscale])
        #expect(rows.allSatisfy(\.isEnabled))
        #expect(AddressChoiceModel.defaultChoice(rows: rows) == .tailscale)
        let root = try #require(AddressChoiceModel.root(for: nil, rows: rows))
        #expect(root.absoluteString == "https://macbook-air-m1.tail1234.ts.net:8765")
        #expect(AddressChoiceModel.root(for: .thisNetwork, rows: rows)?.absoluteString == local)
    }

    @Test("no Tailscale: the Tailscale row is there, greyed with why and WITHOUT a host, and This network is the default")
    func tailscaleOffIsSaidNotHidden() {
        let rows = AddressChoiceModel.rows(sharingAddress: local, tailnetURL: nil, tailnetForward: "none")
        #expect(rows.count == 2)
        #expect(rows[1].disabledReason == AddressChoiceModel.tailscaleOff)
        #expect(rows[1].hostText == nil, "a placeholder names no host (review M2: 'tailscale.invalid' was shown)")
        #expect(AddressChoiceModel.defaultChoice(rows: rows) == .thisNetwork)
        #expect(AddressChoiceModel.root(for: .tailscale, rows: rows)?.absoluteString == local, "a disabled choice falls back to the default")
        #expect(AddressChoiceModel.shownChoice(.tailscale, rows: rows) == .thisNetwork, "the picker shows the row it really uses (review L1)")
    }

    @Test("an engine that could not ask Tailscale (unknown) offers the row as unchecked, not as 'not running', and not first")
    func unknownForwardIsUncheckedNotOff() {
        let rows = AddressChoiceModel.rows(sharingAddress: local, tailnetURL: tail, tailnetForward: "unknown")
        #expect(rows[1].isEnabled && rows[1].reach == AddressChoiceModel.tailscaleUnchecked)
        #expect(AddressChoiceModel.defaultChoice(rows: rows) == .thisNetwork)
        let noDetection = AddressChoiceModel.rows(sharingAddress: local, tailnetURL: nil, tailnetForward: "unknown")
        #expect(noDetection[1].disabledReason == AddressChoiceModel.tailscaleUnchecked, "never 'Tailscale is not running' when it was not asked")
    }

    @Test("a .ts.net sharer whose detection fails still gets its own address as the Tailscale row")
    func tailnetSharerWithoutDetection() {
        let rows = AddressChoiceModel.rows(sharingAddress: "https://m.tail1234.ts.net:8765", tailnetURL: nil, tailnetForward: "unknown")
        #expect(rows.map(\.choice) == [.tailscale] && rows[0].isEnabled)
        #expect(rows[0].url?.absoluteString == "https://m.tail1234.ts.net:8765")
    }

    @Test("a foreign forward (the M4's stale raw forward) disables the Tailscale row with the holder named")
    func foreignForward() {
        let rows = AddressChoiceModel.rows(sharingAddress: local, tailnetURL: tail, tailnetForward: "foreign")
        #expect(rows[1].disabledReason == AddressChoiceModel.tailscaleHeld)
        #expect(AddressChoiceModel.defaultChoice(rows: rows) == .thisNetwork)
    }

    @Test("an engine from before the field (nil forward) keeps the old behaviour: the tailnet row works")
    func oldEngine() {
        let rows = AddressChoiceModel.rows(sharingAddress: local, tailnetURL: tail, tailnetForward: nil)
        #expect(rows[1].isEnabled && AddressChoiceModel.defaultChoice(rows: rows) == .tailscale)
    }

    @Test("a .ts.net sharer has one row, Tailscale, with no This-network duplicate")
    func tailnetSharer() {
        let rows = AddressChoiceModel.rows(sharingAddress: "https://m.tail1234.ts.net:8765", tailnetURL: "https://m.tail1234.ts.net", tailnetForward: "ours")
        #expect(rows.map(\.choice) == [.tailscale])
        #expect(rows[0].url?.port == 8765)
    }

    @Test("the pin follows the row: none for Tailscale, the pin for This network")
    func pinFollowsTheRow() {
        let rows = AddressChoiceModel.rows(sharingAddress: local, tailnetURL: tail, tailnetForward: "ours")
        let pin = Data("spki-value".utf8).base64EncodedString()
        #expect(RemoteClientPairing.invitePin(pin, for: rows[1].url!) == .notNeeded)
        #expect(RemoteClientPairing.invitePin(pin, for: rows[0].url!) == .pin(pin))
    }

    @Test("no sharing address at all: no rows")
    func nothingShared() {
        #expect(AddressChoiceModel.rows(sharingAddress: "", tailnetURL: nil, tailnetForward: nil).isEmpty)
    }
}
