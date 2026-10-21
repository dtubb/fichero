import FicheroAPIClient
import Foundation
import Observation

/// A project's two audited yeses to the cloud: pages may leave this Mac (`POST /api/recipes/project/allow-cloud`, the one click on
/// a refused cloud call, `ai.where.one-egress-gate`), and a cloud model with no listed price may run, counted at an assumed price
/// (`POST /api/recipes/cloud/accept-unpriced`, `ai.where.accept-unpriced-cloud-model`). Neither is an Edit › Undo step: each is
/// reversed where it was given (Set Up's cloud answer; the same route with `withdraw`).
@MainActor
@Observable
final class CloudPermissionStore {
    private(set) var cloudAllowed = false
    /// Every `provider/model` the project accepts running without a listed price, as the engine last said.
    private(set) var accepted: [String] = []
    private(set) var errorMessage: String?
    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// Say yes to cloud models for this project. True when the engine recorded it.
    @discardableResult
    func allowCloud() async -> Bool {
        do {
            switch try await client.api.allowCloudApiRecipesProjectAllowCloudPost() {
            case .ok(let success):
                cloudAllowed = try success.body.json.cloudAllowed
                errorMessage = nil
                return cloudAllowed
            case .unprocessableContent:
                errorMessage = "The engine would not allow cloud models for this project."
            case .undocumented(let code, let payload):
                errorMessage = await EngineErrorDetail.message(from: payload) ?? "Could not allow cloud models (HTTP \(code))."
            }
        } catch {
            if !error.isCancellationError { errorMessage = error.localizedDescription }
        }
        return false
    }

    /// Accept (or, with `withdraw`, take back) one cloud model with no listed price. True when the engine recorded it.
    @discardableResult
    func acceptUnpriced(provider: String, model: String, withdraw: Bool = false) async -> Bool {
        do {
            switch try await client.api.acceptUnpricedCloudModelApiRecipesCloudAcceptUnpricedPost(
                body: .json(.init(provider: provider, model: model, withdraw: withdraw))
            ) {
            case .ok(let success):
                // The engine's list is the whole project's; this row is spliced in place, never the list reloaded.
                _ = try success.body.json
                let key = "\(provider)/\(model)"
                if withdraw {
                    accepted.removeAll { $0 == key }
                } else if !accepted.contains(key) {
                    accepted.append(key)
                }
                errorMessage = nil
                return true
            case .unprocessableContent:
                errorMessage = "The engine would not record that for \(provider)/\(model)."
            case .undocumented(let code, let payload):
                errorMessage = await EngineErrorDetail.message(from: payload) ?? "Could not record that (HTTP \(code))."
            }
        } catch {
            if !error.isCancellationError { errorMessage = error.localizedDescription }
        }
        return false
    }
}
