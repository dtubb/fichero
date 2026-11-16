@testable import Fichero
import Foundation
import Testing

/// `sharing.multiuser-off-says-so`, `sharing.multiuser-needs-sharing-for-anyone-else` (Step 3.3): the order the engine
/// requires (password, then the switch, then a reload), and the two sentences.
@MainActor
struct AccountsOnSequenceTests {
    final class FakeHost: AccountsOnSequence.Host {
        var gap: String?
        var switchRefusal: AccountsOnSequence.Refusal?
        var calls: [String] = []
        func blocker() async throws -> String? { calls.append("blocker"); return gap }
        func setOwnerPassword(_ password: String) async throws { calls.append("password"); gap = nil }
        func setMultiuser(_ enabled: Bool) async throws {
            calls.append("switch")
            if let switchRefusal { throw switchRefusal }
        }
        func reload() async { calls.append("reload") }
    }

    @Test func withAPasswordAlreadyChosenItTurnsOnThenReloads() async {
        let host = FakeHost()
        #expect(await AccountsOnSequence.run(host: host, password: nil) == .turnedOn)
        #expect(host.calls == ["blocker", "switch", "reload"])
    }

    @Test func aPasswordGapAsksForAPasswordInsteadOfFailing() async {
        let host = FakeHost()
        host.gap = "owner_password_gap"
        #expect(await AccountsOnSequence.run(host: host, password: nil) == .needsPassword)
        #expect(host.calls == ["blocker"], "nothing is sent before the password is chosen")
        #expect(await AccountsOnSequence.run(host: host, password: "short") == .needsPassword, "the 8-character rule")
        #expect(await AccountsOnSequence.run(host: host, password: "a chosen one") == .turnedOn)
        #expect(host.calls.suffix(4) == ["blocker", "password", "switch", "reload"], "password, then the switch, then reload")
    }

    @Test func aPasswordGapThe409ReportsLateIsAlsoThePasswordPrompt() async {
        let host = FakeHost()
        host.switchRefusal = .init(status: 409, detail: "Choose a password for the owner first")
        #expect(await AccountsOnSequence.run(host: host, password: nil) == .needsPassword)
    }

    @Test func aPasswordRefusalAfterTypingOneIsWordsNotAnotherPrompt() async {
        let host = FakeHost()
        host.gap = "owner_password_gap"
        host.switchRefusal = .init(status: 409, detail: "Multi-user needs the owner's account to have a password first")
        let result = await AccountsOnSequence.run(host: host, password: "a chosen one")
        guard case .failed(let text) = result else { Issue.record("expected failed, got \(result)"); return }
        #expect(text.contains("password"), "the engine's words reach the person")
    }

    @Test func thePromptDecisionIsPureAndA403KeepsTheEnginesReason() {
        #expect(AccountsOnSequence.needsPasswordPrompt(blocker: "Multi-user needs a Password first", typed: nil))
        #expect(!AccountsOnSequence.needsPasswordPrompt(blocker: "Multi-user needs a Password first", typed: "x"))
        #expect(!AccountsOnSequence.needsPasswordPrompt(blocker: nil, typed: nil))
        let said = AccountsOnSequence.sentence(for: .init(status: 403, detail: "sign in as the owner to change Multi-user"))
        #expect(said == "sign in as the owner to change Multi-user")
    }

    @Test func otherRefusalsBecomeASentenceNeverACode() async {
        let host = FakeHost()
        host.switchRefusal = .init(status: 403, detail: nil)
        let result = await AccountsOnSequence.run(host: host, password: nil)
        guard case .failed(let text) = result else { Issue.record("expected failed"); return }
        #expect(!text.contains("403") && !text.contains("undocumented"))
    }

    @Test func theSentencesAreTheSpecs() {
        #expect(AccountsOnSequence.offSentence == "Accounts are off. Turn on accounts so other people can have their own sign-in.")
        #expect(AccountsOnSequence.sharingNote(accountsOn: true, sharingOn: false) == AccountsOnSequence.anyoneElseNote)
        #expect(AccountsOnSequence.sharingNote(accountsOn: true, sharingOn: true) == nil)
        #expect(AccountsOnSequence.sharingNote(accountsOn: false, sharingOn: false) == nil)
    }
}
