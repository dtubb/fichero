import FicheroAPIClient
import Foundation

/// The owner's pending invitations (`sharing.invite.*`): the list the engine keeps, and the revoke.
extension PairingService {
    /// Unused invitations to named people, with their expiry; never the codes.
    func invites() async throws -> [Components.Schemas.PairingInviteResponse] {
        switch try await client.api.listInvitesApiPairInvitesGet(.init()) {
        case .ok(let success):
            return try success.body.json
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            throw APIError.httpError(statusCode: statusCode, message: detail ?? "Unexpected response")
        }
    }

    /// Revoke one unused invitation at once, a never-expiring one too. A 404 (it was used or revoked already) says so in the
    /// engine's words.
    func revokeInvite(id: String) async throws {
        switch try await client.api.revokeInviteApiPairInvitesInviteIdDelete(path: .init(inviteId: id)) {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw APIError.httpError(
                statusCode: 422, message: (detail?.detail ?? []).map(\.msg).joined(separator: "; "))
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            throw APIError.httpError(statusCode: statusCode, message: detail ?? "Unexpected response")
        }
    }
}
