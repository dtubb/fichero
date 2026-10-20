//
//  AccountsPaneModelTests.swift
//  FicheroTests
//
//  `sharing.settings.three-panes` (the people list) and `sharing.settings.accounts-add-sheet` (#5928).
//

@testable import Fichero
import Testing

@Suite("Settings › Accounts")
struct AccountsPaneModelTests {
    typealias Pane = AccountsPaneModel
    typealias Sheet = AccountsAddSheetModel

    private func person(_ id: String, _ name: String, owner: Bool = false, active: Bool = true) -> Pane.Person {
        .init(id: id, name: name, username: id, isOwner: owner, isActive: active)
    }

    @Test("you first with the You mark, then owners, then by name; invites last and grey")
    func rows() {
        let rows = Pane.rows(
            people: [person("zed", "Zed"), person("amy", "Amy"), person("boss", "Boss", owner: true), person("me", "Me")],
            currentID: "me", invitations: [.init(id: "i1", name: "", username: "newbie")])
        #expect(rows.map(\.id) == ["me", "boss", "amy", "zed", "invite:i1"])
        #expect(rows[0].isYou && !rows[1].isYou)
        #expect(rows[1].role == "Owner" && rows[2].role.isEmpty)
        #expect(rows.last?.kind == .invited && rows.last?.role == "Invited" && rows.last?.title == "newbie")
    }

    @Test("− revokes an invite, disables or enables a person, and never acts on you")
    func removeAction() {
        let rows = Pane.rows(people: [person("me", "Me"), person("a", "A"), person("b", "B", active: false)], currentID: "me",
                             invitations: [.init(id: "i", name: "I", username: "i")])
        let byID = Dictionary(uniqueKeysWithValues: rows.map { ($0.id, $0) })
        #expect(byID["me"]?.removeAction == nil)
        #expect(byID["a"]?.removeAction == "Disable")
        #expect(byID["b"]?.removeAction == "Enable")
        #expect(byID["invite:i"]?.removeAction == "Revoke")
    }

    @Test("the invite choice is there only while Multi-user is on, and Owner only with a password")
    func choices() {
        #expect(Sheet.offersInvite(multiUserOn: true) && !Sheet.offersInvite(multiUserOn: false))
        #expect(Sheet.asksOwner(way: .password) && !Sheet.asksOwner(way: .invite))
    }

    @Test("the button names its act: no ellipsis, since it acts when pressed")
    func buttonTitle() {
        #expect(Sheet.buttonTitle(way: .password, isWorking: false) == "Create Account")
        #expect(Sheet.buttonTitle(way: .invite, isWorking: false) == "Send Invite Link")
        #expect(Sheet.buttonTitle(way: .invite, isWorking: true) == "Sending…")
    }

    @Test("a password needs 8 characters, an invite needs none; name and username always")
    func canSubmit() {
        #expect(!Sheet.canSubmit(name: "A", username: "a", way: .password, password: "1234567", isWorking: false))
        #expect(Sheet.canSubmit(name: "A", username: "a", way: .password, password: "12345678", isWorking: false))
        #expect(Sheet.canSubmit(name: "A", username: "a", way: .invite, password: "", isWorking: false))
        #expect(!Sheet.canSubmit(name: "", username: "a", way: .invite, password: "", isWorking: false))
        #expect(!Sheet.canSubmit(name: "A", username: "a", way: .invite, password: "", isWorking: true))
    }

    @Test("the one line under the fields says what is missing, and nothing before anything is typed")
    func problem() {
        #expect(Sheet.problem(name: "", username: "", way: .password, password: "") == nil)
        #expect(Sheet.problem(name: "A", username: "", way: .password, password: "") == "Enter a name and a username")
        #expect(Sheet.problem(name: "A", username: "a", way: .password, password: "short") == "Use at least 8 characters for the password")
        #expect(Sheet.problem(name: "A", username: "a", way: .invite, password: "short") == nil)
    }

    @Test("the engine's words, one line; a taken username is said plainly")
    func failureWords() {
        #expect(Sheet.failureWords("username already exists") == "That username is taken")
        #expect(Sheet.failureWords("Open a project first: a new person needs one to join") == "Open a project first: a new person needs one to join")
        #expect(Sheet.failureWords("  ") == "Couldn't add the account")
    }
}
