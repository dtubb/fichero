@testable import Fichero
import Foundation
import Testing

/// The generic failure alert's prompt (`run.fail.alert-on-a-failed-run`, #6354): a title, one message, buttons; nothing about a run.
@Suite("Failure alert prompt")
struct FailureAlertPromptTests {
    @Test("the message is the why, then the fix, each its own paragraph; an empty fix is left out")
    func message() {
        #expect(FailureAlertPrompt.message(why: "It stopped.", fix: "Try again.") == "It stopped.\n\nTry again.")
        #expect(FailureAlertPrompt.message(why: "It stopped.", fix: nil) == "It stopped.")
        #expect(FailureAlertPrompt.message(why: "It stopped.", fix: "") == "It stopped.")
    }

    @Test("a prompt keeps its title, fixes in order and a default dismiss label")
    func shape() {
        let prompt = FailureAlertPrompt(title: "Could not pair", message: "m", fixes: [
            .init(id: 0, label: "Try Again", action: {}), .init(id: 1, label: "Open Settings…", action: {})])
        #expect(prompt.title == "Could not pair")
        #expect(prompt.fixes.map(\.label) == ["Try Again", "Open Settings…"])
        #expect(prompt.dismissLabel == "Not Now")
        #expect(FailureAlertPrompt(title: "t", message: "m").fixes.isEmpty)
    }

    @Test("a fix runs its own action")
    func fixActs() {
        var did: [String] = []
        let prompt = FailureAlertPrompt(title: "t", message: "m", fixes: [
            .init(id: 0, label: "A", action: { did.append("a") }), .init(id: 1, label: "B", action: { did.append("b") })])
        prompt.fixes[1].action()
        #expect(did == ["b"])
    }
}
