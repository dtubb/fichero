import FicheroAPIClient
import Foundation

extension PairingService {
    /// `PUT /api/pair/own-devices` (this Mac's own app, over its socket): on mints a NEW enrollment secret and retires the
    /// earlier ones, off retires them all. The secret comes back once, only when on.
    func setOwnDevices(enabled: Bool) async throws -> (engineID: String, secret: String?) {
        let response = try await client.api.setOwnDevicesApiPairOwnDevicesPut(body: .json(.init(enabled: enabled)))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return (body.engineId, body.enrollmentSecret)
        case .unprocessableContent:
            throw APIError.httpError(statusCode: 422, message: "Validation error")
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            throw APIError.httpError(statusCode: statusCode, message: detail ?? "Unexpected response")
        }
    }
}
