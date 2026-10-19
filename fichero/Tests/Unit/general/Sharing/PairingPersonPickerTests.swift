//
//  PairingPersonPickerTests.swift
//  FicheroTests
//
//  sharing.device-chooses-person (#2403): a Multi-user host asks who this Mac is.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

struct PairingPersonPickerTests {
    @Test func aPersonNeedsBothFieldsAndTrimsTheName() {
        #expect(PairingPerson(username: "  alice ", password: "pw")?.username == "alice")
        #expect(PairingPerson(username: "", password: "pw") == nil)
        #expect(PairingPerson(username: "alice", password: "") == nil)
    }

    @Test func onlyTheHostsPersonRequiredAnswerOpensThePicker() {
        let words = "person required: this library uses Multi-user, sign in as a person"
        #expect(PairingPerson.isRequiredRefusal(status: 401, detail: words))
        #expect(!PairingPerson.isRequiredRefusal(status: 401, detail: "invalid or expired pairing code"))
        #expect(!PairingPerson.isRequiredRefusal(status: 401, detail: "invalid username or password"))
        #expect(!PairingPerson.isRequiredRefusal(status: 422, detail: words))
        #expect(!PairingPerson.isRequiredRefusal(status: 401, detail: nil))
    }

    @Test func theRefusalReadsAsAnInstructionToSignIn() {
        #expect(RemoteClientPairingError.personRequired.errorDescription?.contains("username and password") == true)
    }
}
