import FicheroAPIClient
import Foundation
import SwiftUI

// MARK: - Role Actions

extension UsersContent {
    @MainActor
    internal func assignPendingRole() async {
        guard let pendingUserId else { return }
        await updateRole(userId: pendingUserId, role: pendingRole)
    }

    @MainActor
    internal func updateRole(userId: String, role: String) async {
        guard authzSnapshot?.canManageRoles == true else { return }
        isApplyingRoleChange = true
        authzError = nil
        defer { isApplyingRoleChange = false }

        do {
            try await library.actionsService.setLibraryRole(userId: userId, role: role)
            await refreshAuthz()
            syncAddMemberDefaults()
        } catch {
            authzError = error.localizedDescription
            pendingRoleDrafts.removeValue(forKey: userId)
        }
    }

    @MainActor
    internal func revokeRole(userId: String) async {
        guard authzSnapshot?.canManageRoles == true else { return }
        isApplyingRoleChange = true
        authzError = nil
        defer { isApplyingRoleChange = false }

        do {
            try await library.actionsService.revokeLibraryRole(userId: userId)
            await refreshAuthz()
            syncAddMemberDefaults()
        } catch {
            authzError = error.localizedDescription
        }
    }

    internal func roleBinding(for role: Components.Schemas.LibraryRole) -> Binding<String> {
        Binding(
            get: { pendingRoleDrafts[role.userId] ?? role.role },
            set: { newRole in
                pendingRoleDrafts[role.userId] = newRole
                Task { await updateRole(userId: role.userId, role: newRole) }
            }
        )
    }
}
