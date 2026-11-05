import FicheroAPIClient
import Foundation
import OpenAPIRuntime

/// The app-wide cloud spend caps, a monthly and a daily one (`ai.cloud.monthly-cap-in-settings`, `ai.cloud.daily-cap`, #6346,
/// #6347): the defaults of a project with no cap of its own. Read from and written to the engine (`GET`/`PUT /api/ai/cloud-caps`,
/// one audited row); nothing is kept here but what the engine last said.
@MainActor
@Observable
final class CloudCapsStore {
    /// What a project with no monthly cap of its own may spend a month, US$; the engine's 10 until set.
    private(set) var monthlyUsd: Double = CloudCapsStore.engineDefaultMonthlyUsd
    /// What it may spend a day; nil: no daily cap.
    private(set) var dailyUsd: Double?
    var errorMessage: String?

    /// The engine's monthly cap when nothing is set (`llm/spend.py` `DEFAULT_CAP_USD`); shown as the field's prompt only.
    nonisolated static let engineDefaultMonthlyUsd: Double = 10

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    func load() async {
        do {
            switch try await client.api.getCloudCapsApiAiCloudCapsGet() {
            case .ok(let success):
                let caps = try success.body.json
                monthlyUsd = caps.monthlyCapUsd
                dailyUsd = caps.dailyCapUsd
            case .undocumented(let code, _): errorMessage = "Could not read the cloud spending caps (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the cloud spending caps: \(error.localizedDescription)"
        }
    }

    /// Set one cap (`nil` clears it: the monthly returns to the engine's default, the daily to none). False, said, if the engine refused.
    @discardableResult
    func set(_ which: Components.Schemas.CloudCapSetting.WhichPayload, usd: Double?) async -> Bool {
        errorMessage = nil
        do {
            let body = Components.Schemas.CloudCapSetting(which: which, capUsd: usd)
            switch try await client.api.putCloudCapApiAiCloudCapsPut(body: .json(body)) {
            case .ok(let success):
                let caps = try success.body.json
                monthlyUsd = caps.monthlyCapUsd
                dailyUsd = caps.dailyCapUsd
                return true
            case .unprocessableContent:
                errorMessage = "A cap is a number of dollars, 0 or more."
            case .undocumented(let code, let payload):
                errorMessage = await EngineErrorDetail.message(from: payload) ?? "Could not change the cap (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = await Self.engineWords(error) ?? error.localizedDescription
        }
        return false
    }

    /// The engine's own sentence from a response the generated client could not decode (a cap below 0 answers FastAPI's field errors).
    private static func engineWords(_ error: Error) async -> String? {
        guard let clientError = error as? ClientError, let body = clientError.responseBody,
              let data = try? await Data(collecting: body, upTo: 1 << 16) else { return nil }
        return EngineErrorDetail.message(from: data)
    }
}
