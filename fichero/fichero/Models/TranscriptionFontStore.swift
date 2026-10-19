import FicheroAPIClient
import Foundation
import Observation

/// The family this library's transcription text is drawn in (`layers.text.font-from-script-and-period`, #5438):
/// what setup derived from its script and period, or what a pane chose. One store per library, owned by the
/// library reference and handed to its windows through the environment, so two windows on libraries with
/// different scripts each keep their own face. The engine owns the derivation; this only asks and remembers.
@MainActor
@Observable
final class TranscriptionFontStore {
    private(set) var family: String?
    /// The script the family was asked for (the first of the saved answers), so a pane's choice names it.
    private(set) var script: String?
    @ObservationIgnored private let client: FicheroClient
    /// The project's service, so a pane's choice is one Edit > Undo step (`undo.window.*`, #5777).
    @ObservationIgnored private let undo: (any UndoSetEngine)?

    init(client: FicheroClient, undo: (any UndoSetEngine)? = nil) {
        self.client = client
        self.undo = undo
    }

    /// Ask the engine: the saved script, then its font (the engine reads the saved period and any stored choice).
    func load() async {
        guard case .ok(let saved)? = try? await client.api.getProjectSetupApiRecipesProjectGet(),
              let answers = try? saved.body.json.answers,
              let data = try? JSONEncoder().encode(answers),
              let first = Self.firstScript(inAnswers: data),
              case .ok(let derived)? = try? await client.api.derivedFactsApiRecipesDerivedGet(
                query: .init(scripts: first)),
              let facts = try? derived.body.json.scripts.first else {
            family = nil
            script = nil
            return
        }
        script = first
        family = facts.font
    }

    /// Remember a pane's choice with the library (nil returns to the derived font), as one step in the
    /// window's undo stack when it has one.
    func choose(_ chosen: String?, steps: WindowSteps? = nil) async {
        guard let script,
              case .ok(let done)? = try? await client.api.chooseFontApiRecipesFontPut(
                body: .json(.init(script: script, font: chosen))),
              let facts = try? done.body.json else { return }
        family = facts.font
        registerUndo(facts.auditId, steps: steps)
    }

    /// The choice is one step: Edit > Undo takes the audit row back and the font is read again.
    private func registerUndo(_ auditId: String?, steps: WindowSteps?) {
        UndoableChange.register(
            [auditId].compactMap { $0 }, named: "Change Font", service: undo, steps: steps,
            afterEach: { [weak self] in await self?.load() })
    }

    nonisolated static func firstScript(inAnswers data: Data) -> String? {
        let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        return (object?["scripts"] as? [String])?.first
    }
}
