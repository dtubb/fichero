@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `ai.cloud.alert-on-hand-run-paths` (#6349, #6028, #6022): the engine's fixes become the alert's buttons, in its order.
@Suite("Cloud refusal prompt")
struct CloudRefusalAlertTests {
    private func prompt(_ json: String) throws -> CloudRefusalPrompt {
        let refusal = try JSONDecoder().decode(Components.Schemas.CloudRefusal.self, from: Data(json.utf8))
        return CloudRefusalPrompt(refusal: refusal, resend: { _ in })
    }

    @Test("an images refusal offers the four ways through, in the engine's order")
    func images() throws {
        let shown = try prompt("""
        {"kind":"images","scope":"project","project":"Diaries","words":"Pages stay on this Mac.",
         "fixes":[{"kind":"allow-everywhere"},{"kind":"allow-project"},{"kind":"allow-once"},
                  {"kind":"open-settings","control":"settings.ai.cloudAllowed"}]}
        """)
        #expect(shown.choices.map(\.title) == [
            "Allow for all projects", "Allow for this project", "Allow this once", "Open Settings…"])
        #expect(shown.choices.map(\.action) == [
            .allowEverywhere, .allowProject, .runAgain(.init(allowCloud: true)), .openSettings])
    }

    @Test("a cap refusal can run past the cap once or open the caps")
    func cap() throws {
        let shown = try prompt("""
        {"kind":"cap-monthly","scope":"app","words":"US$10 a month is spent.",
         "fixes":[{"kind":"raise-to","usd":12.5},{"kind":"over-cap-once"},
                  {"kind":"open-settings","control":"settings.ai.cloudCaps"}]}
        """)
        #expect(shown.choices.map(\.action) == [.openSettings, .runAgain(.init(overCap: true)), .openSettings])
    }

    @Test("a refusal's words are the error's words")
    func words() throws {
        let shown = try prompt(#"{"kind":"images","scope":"app","words":"Nothing leaves.","fixes":[]}"#)
        #expect(WorkflowExecutionError.cloudRefused(shown.refusal).errorDescription == "Nothing leaves.")
        #expect(shown.choices.isEmpty)
    }
}
