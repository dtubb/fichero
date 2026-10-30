import FicheroAPIClient
import Foundation

/// Changing the cloud spend caps in place, from Ready's budget row and from a refused or paused Start (#6295,
/// `ai.where.cloud-spend-cap`). One engine route, one audited action (`PUT /api/recipes/project/cloud-cap`, through
/// `project.save_setup`), registered as one undoable step on the window's UndoManager (`UndoableChange.register` reverses the
/// answer's `audit_id`) when it has a stack.
extension RecipeSetupStore {
    /// Set the monthly cap and/or the project's total cap (`clearProjectCap`: no total limit). Returns whether the engine kept it;
    /// its words are in `errorMessage` when not. The plan is read again, so it says whether Start still asks.
    @discardableResult
    func changeCloudCaps(
        monthlyUsd: Double? = nil, projectUsd: Double? = nil, clearProjectCap: Bool = false,
        undo: (any UndoSetEngine)? = nil, steps: WindowSteps? = nil
    ) async -> Bool {
        guard monthlyUsd != nil || projectUsd != nil || clearProjectCap else { return false }
        errorMessage = nil  // a field edit too: an earlier "Start is refused…" is not about the cap just set
        do {
            let body = Components.Schemas.CloudCapChange(
                capUsd: monthlyUsd, projectCapUsd: projectUsd, clearProjectCap: clearProjectCap ? true : nil)
            switch try await client.api.changeCloudCapApiRecipesProjectCloudCapPut(body: .json(body)) {
            case .ok(let success):
                let changed = try success.body.json
                await adoptSavedCaps()
                await loadStartPlan(folderId: startPlanFolderId)
                UndoableChange.register(
                    [changed.auditId], named: "Change Cloud Spending Cap", service: undo, steps: steps,
                    afterEach: { [weak self] in
                        await self?.adoptSavedCaps()
                        await self?.loadStartPlan(folderId: self?.startPlanFolderId)
                    })
                return true
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail.sentence ?? "The engine refused that cap."
            case .undocumented(let code, let payload):
                errorMessage = await EngineErrorDetail.message(from: payload) ?? "Could not change the cap (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = error.localizedDescription
        }
        return false
    }

    /// The offer "Raise the monthly cap to N" / "Raise the project cap to N": N is the engine's, as the plan names it.
    @discardableResult
    func raise(_ cap: CloudCapFix.Raise, project: Bool, undo: (any UndoSetEngine)? = nil, steps: WindowSteps? = nil) async -> Bool {
        await changeCloudCaps(
            monthlyUsd: project ? nil : cap.usd, projectUsd: project ? cap.usd : nil, undo: undo, steps: steps)
    }

    /// "Run the first N pages": the plan is read again on those pages alone, and Start runs them (nil: every page again).
    func limitRun(toFirst count: Int?) async {
        runFirstPages = count
        await loadStartPlan(folderId: nil)
    }

    /// The caps as the project now holds them (after a change or an undo), and the saved answers a later save starts from, so a
    /// cap cleared or put back is never written back by the next save.
    fileprivate func adoptSavedCaps() async {
        guard case .ok(let success)? = try? await client.api.getProjectSetupApiRecipesProjectGet(),
              let answers = try? success.body.json.answers, let data = try? JSONEncoder().encode(answers) else { return }
        savedAnswers = data
        let caps = try? JSONDecoder().decode(RecipeSetupAnswers.self, from: data)
        cloudSpendCapUsd = caps?.cloudSpendCapUsd
        cloudProjectCapUsd = caps?.cloudProjectCapUsd
    }
}
