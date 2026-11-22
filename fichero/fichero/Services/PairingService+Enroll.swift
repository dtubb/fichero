import FicheroAPIClient
import Foundation

extension PairingService {
    /// `signin.own.ios-finds-it-and-connects` (#6568): the owner's other device redeems the secret the Mac synced for its OWN
    /// device token. A 401 is `SecretRefused` (the secret was retired or never was); anything else is the address failing.
    func enrollDeviceUnauthenticated(enrollmentSecret: String, deviceName: String) async throws -> PairingExchangeResponse {
        let request = Components.Schemas.EnrollmentRequest(enrollmentSecret: enrollmentSecret, deviceName: deviceName)
        let response = try await client.api.enrollDeviceApiPairEnrollPost(.init(body: .json(request)))
        switch response {
        case .ok(let okResponse):
            let record = try okResponse.body.json
            return PairingExchangeResponse(deviceId: record.deviceId, deviceToken: record.deviceToken, expiresAt: record.expiresAt)
        case .unprocessableContent:
            throw APIError.httpError(statusCode: 422, message: "Validation error")
        case .undocumented(let statusCode, let payload):
            if statusCode == 401 { throw OwnDevicesConnect.SecretRefused() }
            let detail = await EngineErrorDetail.message(from: payload)
            throw APIError.httpError(statusCode: statusCode, message: detail ?? "Unexpected response")
        }
    }
}
