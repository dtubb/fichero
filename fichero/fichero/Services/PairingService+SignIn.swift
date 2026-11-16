import FicheroAPIClient
import Foundation

extension PairingService {
    /// A person signs this device in with no code (`sharing.people.sign-in-without-a-code`, Step 8.9): the password goes
    /// once, over the pinned connection, and only the device token comes back.
    func signInDeviceUnauthenticated(deviceName: String, person: PairingPerson) async throws -> PairingExchangeResponse {
        let request = Components.Schemas.SignInDeviceRequest(
            deviceName: deviceName, username: person.username, password: person.password)
        let response = try await client.api.signInDeviceApiPairSignInPost(.init(body: .json(request)))
        switch response {
        case .ok(let okResponse):
            let record = try okResponse.body.json
            return PairingExchangeResponse(deviceId: record.deviceId, deviceToken: record.deviceToken, expiresAt: record.expiresAt)
        case .unprocessableContent:
            throw APIError.httpError(statusCode: 422, message: "Validation error")
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            throw APIError.httpError(statusCode: statusCode, message: detail ?? "Unexpected response")
        }
    }
}
