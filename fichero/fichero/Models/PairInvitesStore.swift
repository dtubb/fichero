import FicheroAPIClient
import Foundation
import Observation

/// The owner's pending invitations, listed in Settings › Sharing with a Revoke on each (`GET`/`DELETE /api/pair/invites`).
/// The list is the engine's; a revoke removes that row in place, never a reload of the whole list.
@MainActor
@Observable
final class PairInvitesStore {
    typealias Invite = Components.Schemas.PairingInviteResponse

    private(set) var invites: [Invite] = []
    private(set) var errorMessage: String?
    private let list: @MainActor () async throws -> [Invite]
    private let revokeOne: @MainActor (String) async throws -> Void

    init(list: @escaping @MainActor () async throws -> [Invite], revoke: @escaping @MainActor (String) async throws -> Void) {
        self.list = list
        self.revokeOne = revoke
    }

    convenience init(service: PairingService) {
        self.init(list: { try await service.invites() }, revoke: { try await service.revokeInvite(id: $0) })
    }

    func load() async {
        do {
            invites = try await list()
            errorMessage = nil
        } catch {
            if error.isCancellationError { return }
            errorMessage = error.localizedDescription
        }
    }

    func revoke(_ invite: Invite) async {
        do {
            try await revokeOne(invite.id)
            invites.removeAll { $0.id == invite.id }
            errorMessage = nil
        } catch {
            if error.isCancellationError { return }
            errorMessage = error.localizedDescription
        }
    }
}

/// How a pending invitation reads on its row: the role it gives and when it ends, in words.
enum PendingInviteText {
    nonisolated static func detail(role: String?, expiresAt: Date?, now: Date = Date()) -> String {
        let gives = role.map { "Gives \($0)" } ?? "Keeps the role they have"
        return "\(gives) · \(AddDeviceSheetModel.expiresText(expiresAt: expiresAt, now: now))"
    }
}
