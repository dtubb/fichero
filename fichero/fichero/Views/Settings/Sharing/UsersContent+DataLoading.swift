import Foundation

// MARK: - Data Loading

extension UsersContent {
    @MainActor
    internal func loadData() async {
        await store.load()
        await refreshAuthz()
        // Pending invites are owner-only; a non-owner probe just returns empty.
        if store.currentUser?.isOwner == true {
            await store.loadInvites()
            await store.loadAccessMatrix()
        }
        syncAddMemberDefaults()
    }

    @MainActor
    internal func refreshAuthz() async {
        do {
            authzSnapshot = try await library.actionsService.loadLibraryAuthzSnapshot()
            pendingRoleDrafts.removeAll()
        } catch {
            authzSnapshot = nil  // ponytail: a load that fails hides the roles section; an alert on every open would nag
        }
    }

    @MainActor
    internal func syncAddMemberDefaults() {
        guard !unassignedUsers.isEmpty else {
            pendingUserId = nil
            return
        }
        if let pendingUserId, unassignedUsers.contains(where: { $0.id == pendingUserId }) {
            return
        }
        pendingUserId = unassignedUsers.first?.id
    }
}
