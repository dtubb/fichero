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
