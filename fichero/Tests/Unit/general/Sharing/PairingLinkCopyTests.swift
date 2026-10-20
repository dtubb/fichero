//
//  PairingLinkCopyTests.swift
//  FicheroTests
//
//  sharing.pairing.copy-link-says-why (#5891): "Copy Pairing Link" did nothing on the owner's Pro. With a one-time code but
//  no derived pin there was no link, no button and no reason (the blocker was hidden behind the code). Copy now copies and
//  reads the clipboard back, or says in words why nothing was copied. See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

struct PairingLinkCopyTests {
    @Test func withNoLinkTheCardSaysWhyInWords() {
        let outcome = PairingLinkCopy.attempt(link: nil, blocker: .pinNotDerived,
                                              write: { _ in Issue.record("nothing to write") }, read: { nil })
        guard case .notCopied(let reason) = outcome else { Issue.record("expected a reason"); return }
        #expect(reason.contains("Preparing the security certificate"))
        #expect(reason.contains("Turning sharing off and on"), "the cure is named")
    }

    @Test func withNoLinkAndNoBlockerTheGeneralReasonIsGiven() {
        let outcome = PairingLinkCopy.attempt(link: nil, blocker: nil, write: { _ in }, read: { nil })
        #expect(outcome == .notCopied(PairingLinkCopy.noLinkReason(blocker: nil)))
        #expect(PairingLinkCopy.noLinkReason(blocker: nil).contains("isn't ready"))
    }

    @Test func aLinkIsCopiedAndReadBack() {
        var clipboard: String?
        let outcome = PairingLinkCopy.attempt(link: "fichero://pair?x=1", blocker: nil,
                                              write: { clipboard = $0 }, read: { clipboard })
        #expect(outcome == .copied)
        #expect(clipboard == "fichero://pair?x=1")
    }

    @Test func aClipboardThatDoesNotTakeTheLinkIsSaidInWords() {
        let outcome = PairingLinkCopy.attempt(link: "fichero://pair?x=1", blocker: nil, write: { _ in }, read: { "something else" })
        guard case .notCopied(let reason) = outcome else { Issue.record("expected a reason"); return }
        #expect(reason.contains("couldn't copy the link"))
    }
}

/// The pin an invite carries (#5891): a publicly-trusted host needs none, and used to be read as "no pin derived" because
/// `try?` flattens the optional; and the pane derives a missing pin itself, once.
struct PairingInvitePinTests {
    private let ownCert = URL(string: "https://macbook-pro.local:8765")!
    private let tailnet = URL(string: "https://macbook-pro.tail1234.ts.net")!
    private let validPin = Data(repeating: 7, count: 32).base64EncodedString()

    @Test func aHostServingItsOwnCertificateNeedsItsPin() {
        #expect(RemoteClientPairing.invitePin("", for: ownCert) == .missing)
        #expect(RemoteClientPairing.invitePin(validPin, for: ownCert) == .pin(validPin))
    }

    @Test func aPubliclyTrustedHostGetsAnUnpinnedLinkThatSystemTLSValidates() throws {
        #expect(RemoteClientPairing.invitePin("", for: tailnet) == .notNeeded)
        // The guest holds no pin for it and checks the host with normal TLS (system trust + hostname).
        #expect(try RemoteClientPairing.resolvedSPKIPin(nil, for: tailnet) == nil)
    }

    @Test func plainHttpGetsNoLinkWhateverTheHost() {
        for url in [URL(string: "http://macbook-pro.tail1234.ts.net")!, URL(string: "http://macbook-pro.local:8765")!] {
            #expect(RemoteClientPairing.invitePin(validPin, for: url) == .missing)
            #expect(RemoteClientPairing.invitePin("", for: url) == .missing)
        }
        #expect(throws: (any Error).self) { try validatedHostedRemoteURL(from: "http://macbook-pro.tail1234.ts.net") }
    }

    @Test func theMissingPinIsDerivedOnceAndOnlyForAnEngineThisAppStarted() {
        func needed(external: Bool = false, tried: Bool = false, url: URL? = nil, pin: String = "") -> Bool {
            PairingPinRepair.needed(hostingEnabled: true, backendRunning: true, externalEngine: external,
                                    address: url ?? ownCert, pin: pin, alreadyTried: tried)
        }
        #expect(needed())
        #expect(!needed(tried: true), "once per opening of the pane: no loop")
        #expect(!needed(external: true), "an engine this app did not start cannot be restarted")
        #expect(!needed(url: tailnet), "a publicly-trusted host has no pin to derive")
        #expect(!needed(pin: validPin), "a pin that is filed needs nothing")
        #expect(!PairingPinRepair.needed(hostingEnabled: false, backendRunning: true, externalEngine: false,
                                         address: ownCert, pin: "", alreadyTried: false), "sharing is off")
    }
}
