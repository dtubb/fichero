@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `run.fail.alert-on-a-failed-run` (#6354): a served `RunFailure` becomes the generic failure alert, a button per action in the
/// engine's order; the words are the engine's, never the raw detail.
@Suite("Run failure alert")
struct RunFailureAlertTests {
    private func failure(_ json: String) throws -> Components.Schemas.RunFailure {
        try JSONDecoder().decode(Components.Schemas.RunFailure.self, from: Data(json.utf8))
    }

    private let noCredit = """
    {"kind":"no-credit","words":"OpenRouter has no credit left.","fix":"Add credit, then run it again.","detail":"HTTP 402 body",
     "actions":[{"kind":"open-settings","control":"settings.ai.providers"},{"kind":"choose-model"},{"kind":"retry"}]}
    """

    @Test("each action is a button in the engine's order, titled for what it does")
    func buttons() throws {
        let prompt = RunFailurePrompt.make(try failure(noCredit), perform: { _ in })
        #expect(prompt.fixes.map(\.label) == ["Open Settings…", "Choose a Model…", "Run It Again"])
        #expect(prompt.fixes.map(\.id) == [0, 1, 2])
    }

    @Test("an unexpected failure offers the report first when the engine says so")
    func unexpected() throws {
        let bug = try failure("""
        {"kind":"unexpected","words":"Something went wrong inside Fichero.","fix":"Send a bug report.",
         "actions":[{"kind":"report-bug"},{"kind":"retry"}]}
        """)
        #expect(RunFailurePrompt.make(bug, perform: { _ in }).fixes.map(\.label) == ["Send a Bug Report…", "Run It Again"])
    }

    @Test("the message is the engine's words and fix, never the raw detail")
    func message() throws {
        let prompt = RunFailurePrompt.make(try failure(noCredit), perform: { _ in })
        #expect(prompt.message == "OpenRouter has no credit left.\n\nAdd credit, then run it again.")
        #expect(!prompt.message.contains("HTTP 402"))
    }

    @Test("the title names the workflow, else says Fichero stopped the run")
    func title() throws {
        let served = try failure(noCredit)
        #expect(RunFailurePrompt.make(served, workflow: "Read each line", perform: { _ in }).title == "Read each line stopped")
        #expect(RunFailurePrompt.make(served, perform: { _ in }).title == "Fichero stopped this run")
    }

    @Test("a button hands its own action to perform")
    func performs() throws {
        var performed: [String] = []
        let prompt = RunFailurePrompt.make(try failure(noCredit), perform: { performed.append($0.kind.rawValue) })
        prompt.fixes[2].action()
        prompt.fixes[0].action()
        #expect(performed == ["retry", "open-settings"])
    }

    @Test("Show in Activity is the last button when it is given, and only then")
    func showInActivity() throws {
        var shown = false
        let with = RunFailurePrompt.make(try failure(noCredit), perform: { _ in }, showInActivity: { shown = true })
        #expect(with.fixes.last?.label == "Show in Activity")
        with.fixes.last?.action()
        #expect(shown)
        #expect(RunFailurePrompt.make(try failure(noCredit), perform: { _ in }).fixes.count == 3)
    }

    @Test("a cap or images refusal's actions get no button here: the cap alert answers them")
    func refusalsAreNotThisAlert() throws {
        let cap = try failure("""
        {"kind":"cap-refused","words":"The cap stopped it.","fix":"Use a button.",
         "actions":[{"kind":"raise-to","usd":10.4},{"kind":"over-cap-once"},{"kind":"resume"}]}
        """)
        #expect(RunFailurePrompt.make(cap, perform: { _ in }).fixes.map(\.label) == ["Resume"])
    }
}
