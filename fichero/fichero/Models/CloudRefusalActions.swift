import FicheroAPIClient
import Foundation

/// What the refusal alert's buttons ask of the engine (`ai.cloud.alert-on-hand-run-paths`, #6349):
/// each one audited action.
enum CloudRefusalActions {
    /// Raise the cap a refusal names, by the audited action for its scope: the app's monthly or
    /// daily cap, or the project's own. False when the engine refused it.
    static func raise(
        _ kind: Components.Schemas.CloudRefusal.KindPayload, scope: Components.Schemas.CloudRefusal.ScopePayload,
        usd: Double, client: FicheroClient
    ) async -> Bool {
        do {
            if scope == .app, kind == .capMonthly || kind == .capDaily {
                let which: Components.Schemas.CloudCapSetting.WhichPayload = kind == .capMonthly ? .monthly : .daily
                let body = Components.Schemas.CloudCapSetting(which: which, capUsd: usd)
                if case .ok = try await client.api.putCloudCapApiAiCloudCapsPut(body: .json(body)) { return true }
                return false
            }
            let change = Components.Schemas.CloudCapChange(
                capUsd: kind == .capMonthly ? usd : nil, projectCapUsd: kind == .capProject ? usd : nil,
                dailyCapUsd: kind == .capDaily ? usd : nil, runCapUsd: kind == .capRun ? usd : nil)
            let sent = try await client.api.changeCloudCapApiRecipesProjectCloudCapPut(body: .json(change))
            if case .ok = sent { return true }
        } catch {
            return false
        }
        return false
    }

    /// Say yes to pages leaving for the open project (`POST /api/recipes/project/allow-cloud`, audited).
    static func allowProject(client: FicheroClient) async {
        let body = Components.Schemas.AllowCloudRequest(allowed: true)
        _ = try? await client.api.allowCloudApiRecipesProjectAllowCloudPost(body: .json(body))
    }
}
