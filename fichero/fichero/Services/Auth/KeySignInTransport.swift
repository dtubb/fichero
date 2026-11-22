import Foundation

nonisolated protocol KeySignInTransport: Sendable {
    func challenge(publicKeyPEM: String) async throws -> SignInChallenge
    /// Returns the session token. `device` names this device on the engine ("Daniel's iPhone").
    func signIn(publicKeyPEM: String, nonce: String, signature: String, deviceName: String, host: String) async throws -> String
}
