import FicheroAPIClient
import Foundation

/// The generated client behind `KeySignInTransport`. A refusal keeps its status: 401 is the engine refusing the key.
nonisolated struct GeneratedKeySignInTransport: KeySignInTransport, @unchecked Sendable {
    let client: FicheroClient

    func challenge(publicKeyPEM: String) async throws -> SignInChallenge {
        let response = try await client.api.keyChallengeApiAuthKeyChallengePost(body: .json(.init(publicKeyPem: publicKeyPEM)))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return SignInChallenge(nonce: body.nonce, expiresAt: body.expiresAt, engineID: body.engineId)
        case .unprocessableContent:
            throw SignInRefusal.refused(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw SignInRefusal.refused(statusCode: statusCode)
        }
    }

    func signIn(publicKeyPEM: String, nonce: String, signature: String, deviceName: String, host: String) async throws -> String {
        let request = Components.Schemas.KeySignInRequest(
            publicKeyPem: publicKeyPEM, nonce: nonce, signature: signature, client: .init(name: deviceName, host: host))
        let response = try await client.api.signInByKeyApiAuthSignInByKeyPost(body: .json(request))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.sessionToken
        case .unprocessableContent:
            throw SignInRefusal.refused(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw SignInRefusal.refused(statusCode: statusCode)
        }
    }
}
