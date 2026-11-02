import FicheroAPIClient
import Foundation
import OpenAPIRuntime

/// Adding a layer after setup and the engine words for a response the client could not decode
/// (`source.onboard.add-layer`); split from `RecipeSetupStore.swift` for the file-size cap.
extension RecipeSetupStore {
    // MARK: Added later (source.onboard.add-layer)

    /// Change the project's languages after setup (from the Inspector):
    /// re-propose the recipe from the new answers and keep both on the
    /// project. Returns whether the engine kept them. Nothing runs.
    @discardableResult
    func updateLanguages(_ codes: [String]) async -> Bool {
        // Splice, so a language already there keeps its place (no wholesale reset).
        languages.removeAll { !codes.contains($0) }
        for code in codes where !languages.contains(code) { languages.append(code) }
        await assemble()
        guard recipe != nil else { return false }
        return await save()
    }

    /// Add a layer to the project, or with `remove` take an added one out
    /// (`POST /api/recipes/project/layers`, action `project.add_layer`, audited and undoable).
    /// The engine adds the layer's steps to the recipe and proposes its jobs for the material
    /// already there; the Start plan it returns shows them with the estimate. Nothing runs
    /// until Start. Afterwards the saved answers and recipe are read back, so a later save
    /// from setup or the Inspector carries the layer. Returns whether the engine kept it.
    @discardableResult
    func changeLayer(_ layer: String, remove: Bool = false) async -> Bool {
        errorMessage = nil
        do {
            switch try await client.api.changeProjectLayersApiRecipesProjectLayersPost(
                headers: .init(), body: .json(.init(layers: [layer], remove: remove))
            ) {
            case .ok(let success):
                startPlan = try success.body.json
                spliceLayer(layer, remove: remove)
                await adoptRecipeTheEngineWrote()
                return true
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description
                    ?? (remove ? "The engine would not remove the \(layer) layer" : "The engine would not add the \(layer) layer")
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not change the project's layers (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            // A refusal in words ("the recipe already has entities") arrives as a 422 whose
            // `detail` is a sentence, which the generated validation shape cannot decode: say
            // the engine's sentence, never the decoding error.
            errorMessage = await Self.engineWords(error) ?? error.localizedDescription
        }
        return false
    }

    /// The engine kept the change: the one layer joins (or leaves) the answers in place, in
    /// `layers` and in the saved answers a later save starts from.
    private func spliceLayer(_ layer: String, remove: Bool) {
        if remove { layers.removeAll { $0 == layer } } else if !layers.contains(layer) { layers.append(layer) }
        var saved = (savedAnswers.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]) ?? [:]
        saved["layers"] = layers
        savedAnswers = try? JSONSerialization.data(withJSONObject: saved)
    }

    /// The engine rewrote the recipe (the layer's steps joined it or left it, a model the person
    /// chose stayed): take that one object as the engine saved it, so a later save sends it
    /// back unchanged rather than the recipe from before the layer.
    private func adoptRecipeTheEngineWrote() async {
        do {
            guard case .ok(let success) = try await client.api.getProjectSetupApiRecipesProjectGet(),
                  let saved = try success.body.json.recipe else { return }
            rememberOverrides(from: try JSONEncoder().encode(saved))
            recipe = try Self.convert(saved, to: Components.Schemas.AssembledRecipe.self)
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the recipe the engine saved: \(error.localizedDescription)"
        }
    }

    /// The engine's own sentence from a response the generated client could not decode.
    static func engineWords(_ error: Error) async -> String? {
        guard let clientError = error as? ClientError, let body = clientError.responseBody,
              let data = try? await Data(collecting: body, upTo: 1 << 16) else { return nil }
        return EngineErrorDetail.message(from: data)
    }

    /// The layers the Inspector offers to add, as the engine's Start plan names them
    /// (`addable`: the addable layers less those the project has and those its purpose
    /// brings). The app never works the rule out (`source.onboard.add-layer`).
    var addableLayers: [String] { startPlan?.addable ?? [] }

    /// What an added layer proposes for the material already in the project, with each step's
    /// topic text, as the engine's Start plan carries it; nil when nothing is proposed.
    var proposedJobs: Components.Schemas.ProposedJobs? {
        guard let proposed = startPlan?.proposed, !proposed.steps.isEmpty else { return nil }
        return proposed
    }
}
